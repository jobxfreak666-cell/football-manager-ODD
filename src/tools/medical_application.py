"""Manual, default and scheduled medical-treatment use cases.

The service owns the four use-case control flows and response shape only.
``LocalOddsState`` remains the single owner of runtime state, locks, save
binding, club profiles and ``club_medical_auto_result``; all domain and native
collaborators are supplied through the frozen :class:`MedicalIO` callables so
importing this module never imports the HTTP entrypoint or the native FM core.

Scheduled progression still runs from the existing game-day flow; this module
does not add a scheduler, cache injury truth, or replace treatment storage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class MedicalIO:
    """Explicit collaborators used by the medical use cases."""

    read_game_clock: Callable[[], Any]
    welfare_status: Callable[[], dict[str, Any]]
    public_economy: Callable[[], dict[str, Any]]
    update_player_injury_treatment: Callable[..., dict[str, Any]]
    set_medical_treatment: Callable[..., dict[str, Any]]
    set_default_medical_treatment: Callable[[str], dict[str, Any]]
    process_medical_treatments: Callable[..., dict[str, Any]]
    complete_player_medical_treatment: Callable[..., Any]
    apply_default_medical_treatments: Callable[..., dict[str, Any]]


class MedicalRuntime(Protocol):
    """State, locks and callbacks consumed from the owning runtime.

    The implementation documents what the use cases read or mutate; it does
    not store state and is never constructed by the service.
    """

    output: dict[str, Any]
    lock: Any
    memory_lock: Any
    club_profiles: dict[str, Any]
    club_profile: dict[str, Any] | None
    club_medical_auto_result: dict[str, Any] | None

    def _bind_current_save(self) -> Any: ...

    def _live_player_profile(
        self, player_id: int, requested_team_id: int,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]: ...

    def _apply_default_medical_treatments(
        self, game_date: str, profiles: list[dict[str, Any]],
        *, status: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class MedicalApplicationService:
    def __init__(self, runtime: MedicalRuntime, io: MedicalIO) -> None:
        self._runtime = runtime
        self._io = io

    def update_treatment(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        player_id = int(payload.get("player_id") or 0)
        requested_team_id = int(payload.get("team_id") or 0)
        mode = str(payload.get("mode") or "none")
        with runtime.memory_lock:
            with runtime.lock:
                runtime._bind_current_save()
                profile, player = runtime._live_player_profile(
                    player_id, requested_team_id,
                )
                if not profile or not player:
                    raise ValueError("所选球员不属于当前执教球队，请先刷新队伍")
                game_date = str(
                    (io.read_game_clock() or {}).get("date")
                    or runtime.output.get("game_date") or ""
                )
                team_id = int((profile.get("team") or {}).get("id") or 0)
                player_address = str(player.get("address") or "")
                if not game_date:
                    raise ValueError("尚未读取当前游戏日期")

            # The current turnover reads and records the previous factor even
            # though ``set_medical_treatment`` derives the old factor itself.
            previous = dict(
                (io.welfare_status().get("treatments") or {}).get(str(player_id)) or {}
            )
            old_factor = float(previous.get("factor") or 1.0)

            def transform(from_factor: float, to_factor: float) -> dict[str, Any]:
                return io.update_player_injury_treatment(
                    player_id, player_address, game_date, from_factor, to_factor,
                )

            result = io.set_medical_treatment(
                player_id, str(player.get("name") or player_id), team_id,
                player_address, mode, game_date, transform,
            )
            with runtime.lock:
                if result.get("injuries") is not None:
                    availability = dict(player.get("availability") or {})
                    availability["injuries"] = list(result.get("injuries") or [])
                    availability["injury_count"] = len(availability["injuries"])
                    player["availability"] = availability
            return {
                "treatment": result,
                "economy": io.public_economy(),
                "welfare": io.welfare_status(),
            }

    def update_default(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        mode = str(payload.get("mode") or "manual")
        with runtime.memory_lock:
            with runtime.lock:
                runtime._bind_current_save()
                profiles = list(runtime.club_profiles.values()) or (
                    [runtime.club_profile] if runtime.club_profile else []
                )
                game_date = str(
                    (io.read_game_clock() or {}).get("date")
                    or runtime.output.get("game_date") or ""
                )
            medical_snapshot = io.set_default_medical_treatment(mode)
            # Keep the legacy replacement point: callers/tests may replace
            # ``_apply_default_medical_treatments`` on the facade.
            auto_result = (
                runtime._apply_default_medical_treatments(
                    game_date, profiles, status=medical_snapshot,
                )
                if game_date and profiles else None
            )
            with runtime.lock:
                runtime.club_medical_auto_result = auto_result
        return {
            "economy": io.public_economy(), "welfare": io.welfare_status(),
            "auto_treatment": auto_result,
        }

    def process_due(
        self, game_date: str, profiles: list[dict[str, Any]],
    ) -> dict[str, Any]:
        io = self._io
        players = {
            int(player.get("id") or 0): player
            for profile in profiles for player in (profile.get("players") or [])
            if int(player.get("id") or 0) > 0
        }
        injured_ids = {
            player_id for player_id, player in players.items()
            if int((player.get("availability") or {}).get("injury_count") or 0) > 0
        }

        def cancel(state: dict[str, Any]) -> None:
            player_id = int(state.get("player_id") or 0)
            player = players.get(player_id)
            address = (player or {}).get("address") or state.get("player_address")
            result = io.update_player_injury_treatment(
                player_id, address, game_date,
                float(state.get("factor") or 1.0), 1.0,
            )
            if player is not None:
                availability = dict(player.get("availability") or {})
                availability["injuries"] = list(result.get("injuries") or [])
                availability["injury_count"] = len(availability["injuries"])
                player["availability"] = availability

        def complete(state: dict[str, Any]) -> None:
            player_id = int(state.get("player_id") or 0)
            player = players.get(player_id)
            address = (player or {}).get("address") or state.get("player_address")
            io.complete_player_medical_treatment(
                player_id, address, game_date,
                list(state.get("injury_start_dates") or []),
            )

        return io.process_medical_treatments(
            game_date, injured_ids, cancel, complete,
            resolved_player_ids=set(players),
        )

    def apply_default(
        self, game_date: str, profiles: list[dict[str, Any]],
        *, status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        io = self._io
        candidates = []
        for profile in profiles:
            team_id = int((profile.get("team") or {}).get("id") or 0)
            for player in profile.get("players") or []:
                candidate = dict(player)
                candidate["team_id"] = team_id
                candidate["_profile_player"] = player
                candidates.append(candidate)

        def transform(
            candidate: dict[str, Any], from_factor: float, to_factor: float,
        ) -> dict[str, Any]:
            player_id = int(candidate.get("id") or 0)
            result = io.update_player_injury_treatment(
                player_id, candidate.get("address"), game_date,
                from_factor, to_factor,
            )
            player = candidate.get("_profile_player")
            if isinstance(player, dict):
                availability = dict(player.get("availability") or {})
                availability["injuries"] = list(result.get("injuries") or [])
                availability["injury_count"] = len(availability["injuries"])
                player["availability"] = availability
            return result

        return io.apply_default_medical_treatments(
            game_date, candidates, transform, status=status,
        )
