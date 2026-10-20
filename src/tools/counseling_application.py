"""Single psychological-counseling use case.

The service owns the use-case control flow, compensation order and response
shape only.  ``LocalOddsState`` remains the single owner of runtime state,
locks, save/manager binding and relationship archiving; all external domain
and wallet collaborators are supplied through the frozen :class:`CounselingIO`
callables so importing this module never imports the HTTP entrypoint or the
native FM core.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class CounselingIO:
    """Explicit collaborators used by the counseling use case."""

    read_game_clock: Callable[[], Any]
    local_purchase_price: Callable[[float], float]
    session_price: float
    available_balance: Callable[[], float]
    adjust_balance: Callable[..., Any]
    player_has_unhappiness: Callable[[int, Any], bool]
    apply_effect: Callable[[int, Any, str], dict[str, Any]]
    adjust_manager_intimacy: Callable[..., dict[str, Any]]
    restore_effect: Callable[[dict[str, Any]], Any]
    perform_counseling: Callable[..., dict[str, Any]]
    public_economy: Callable[[], dict[str, Any]]
    welfare_status: Callable[[], dict[str, Any]]


class CounselingRuntime(Protocol):
    """State, locks and callbacks consumed from the owning runtime.

    The implementation documents what the use case reads or mutates; it does
    not store state and is never constructed by the service.
    """

    output: dict[str, Any]
    lock: Any
    memory_lock: Any

    def _bind_current_save(self) -> Any: ...

    def _live_player_profile(
        self, player_id: int, requested_team_id: int,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]: ...

    def _archive_activity_relationship(self, **kwargs: Any) -> bool: ...


class CounselingApplicationService:
    def __init__(self, runtime: CounselingRuntime, io: CounselingIO) -> None:
        self._runtime = runtime
        self._io = io

    def counsel(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        player_id = int(payload.get("player_id") or 0)
        requested_team_id = int(payload.get("team_id") or 0)
        with runtime.memory_lock:
            with runtime.lock:
                runtime._bind_current_save()
                profile, player = runtime._live_player_profile(
                    player_id, requested_team_id,
                )
                if not profile or not player:
                    raise ValueError("所选球员不属于当前执教球队，请先刷新队伍")
                manager = dict(runtime.output.get("manager") or {})
                manager_id = int(
                    runtime.output.get("selected_manager_id")
                    or manager.get("id") or 0
                )
                team = dict(profile.get("team") or {})
                team_id = int(team.get("id") or 0)
                current_intimacy = int(player.get("manager_intimacy") or 0)
                game_date = str(
                    (io.read_game_clock() or {}).get("date")
                    or runtime.output.get("game_date") or ""
                )
                if not game_date:
                    raise ValueError("尚未读取当前游戏日期")
                player_name = str(player.get("name") or player_id)
                player_address = player.get("address")
            if not io.player_has_unhappiness(player_id, player_address):
                raise ValueError("该球员当前没有可清除的不满")

            price = io.local_purchase_price(io.session_price)
            if io.available_balance() < price:
                raise ValueError("钱包余额不足，心理辅导每次需要从钱包支付")
            io.adjust_balance(
                -price, "psychological_counseling_session",
                manager_id=manager_id, player_id=player_id,
                player_name=player_name, game_date=game_date,
            )
            payment = {"bank": 0.0, "wallet": price, "total": price}
            applied_effect: dict[str, Any] | None = None

            def apply_effects(outcome: str, points: int) -> dict[str, Any]:
                nonlocal applied_effect
                effect = io.apply_effect(player_id, player_address, outcome)
                applied_effect = effect
                try:
                    intimacy = io.adjust_manager_intimacy(
                        player_id, player_address, manager_id, team_id,
                        team_address=team.get("address"),
                        manager_address=manager.get("manager_address"),
                        points=points,
                    ) if points else {
                        "before": current_intimacy, "after": current_intimacy,
                        "applied": 0,
                    }
                except Exception:
                    io.restore_effect(effect)
                    applied_effect = None
                    raise
                public_effect = {
                    key: value for key, value in effect.items()
                    if not key.startswith("_")
                }
                return {**intimacy, "effect": public_effect}

            try:
                result = io.perform_counseling(
                    manager_id, player_id, player_name, game_date,
                    current_intimacy, apply_effects,
                )
            except Exception:
                if applied_effect is not None:
                    try:
                        io.restore_effect(applied_effect)
                    except Exception:
                        pass
                io.adjust_balance(
                    price, "psychological_counseling_session_rollback",
                    manager_id=manager_id, player_id=player_id,
                    player_name=player_name, game_date=game_date,
                )
                raise
            result["payment"] = payment
            result["relationship_archived"] = runtime._archive_activity_relationship(
                target=player, target_kind="player", manager=manager,
                manager_id=manager_id, result=result, game_date=game_date,
                source_key="activity:psychological_counseling",
                source_label=(
                    f"心理辅导 · {result.get('outcome_name') or '关系变化'}"
                ),
                target_role="counselee", intimacy_before=current_intimacy,
                details={
                    "event_family": "心理辅导",
                    "outcome": result.get("outcome"),
                    "outcome_name": result.get("outcome_name"),
                    "team_id": team_id,
                },
            )
            with runtime.lock:
                if int(result.get("integer_applied") or 0):
                    player["manager_intimacy"] = int(float(result["intimacy"]))
                for change in (result.get("effect") or {}).get("effects") or []:
                    if change.get("field") == "morale":
                        player["morale"] = change.get("after")
                    if (
                        change.get("field") == "unhappiness"
                        and change.get("after") is False
                    ):
                        player["has_unhappiness"] = False
            return {
                "counseling": result,
                "economy": io.public_economy(),
                "welfare": io.welfare_status(),
            }
