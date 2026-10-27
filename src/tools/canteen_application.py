"""Single and batched canteen sea-cucumber reward use cases.

The service owns the use-case control flow, compensation order and response
shape only.  ``LocalOddsState`` remains the single owner of runtime state,
locks, save/manager binding and live target resolution; all domain, wallet and
native-effect collaborators are supplied through the frozen :class:`CanteenIO`
callables so importing this module never imports the HTTP entrypoint or the
native FM core.

The batch keeps one short-lived memory session but gives every player an
independent effect transaction; it is deliberately not a team-wide atomic
transaction.  The existing canteen plan/CA Hook, bottom-level memory-session
implementation and ``commit_player_effect`` remain the owners of those
concerns.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class CanteenIO:
    """Explicit collaborators used by the canteen sea-cucumber use cases."""

    read_game_clock: Callable[[], Any]
    local_purchase_price: Callable[[float], float]
    base_price: float
    charge_combined_funds: Callable[..., dict[str, Any]]
    refund_combined_funds: Callable[..., Any]
    commit_player_effect: Callable[..., Any]
    apply_effect: Callable[..., dict[str, Any]]
    apply_intimacy: Callable[..., dict[str, Any]]
    restore_effect: Callable[..., Any]
    memory_session_factory: Callable[[], Any]
    describe_error: Callable[..., dict[str, Any]]
    public_economy: Callable[[], dict[str, Any]]


class CanteenRuntime(Protocol):
    """State, locks and callbacks consumed from the owning runtime.

    The implementation documents what the use cases read or mutate; it does
    not store state and is never constructed by the service.
    """

    output: dict[str, Any]
    lock: Any
    memory_lock: Any

    def _bind_current_save(self) -> Any: ...

    def _live_player_effect_target(
        self, player_id: int, requested_team_id: int, **kwargs: Any,
    ) -> Any: ...

    def _canteen_sea_cucumber_context(
        self,
    ) -> tuple[dict[str, Any], int, str]: ...

    def _canteen_sea_cucumber_one(
        self, player_id: int, requested_team_id: int, *,
        manager: dict[str, Any], manager_id: int, game_date: str,
        memory_session: Any = None,
    ) -> dict[str, Any]: ...


class CanteenApplicationService:
    def __init__(self, runtime: CanteenRuntime, io: CanteenIO) -> None:
        self._runtime = runtime
        self._io = io

    def reward_one(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self._runtime
        player_id = int(payload.get("player_id") or 0)
        requested_team_id = int(payload.get("team_id") or 0)
        if player_id <= 0:
            raise ValueError("请选择球员")
        with runtime.memory_lock:
            manager, manager_id, game_date = (
                runtime._canteen_sea_cucumber_context()
            )
            result = runtime._canteen_sea_cucumber_one(
                player_id, requested_team_id, manager=manager,
                manager_id=manager_id, game_date=game_date,
            )
        result["economy"] = self._io.public_economy()
        return result

    def reward_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        raw_player_ids = payload.get("player_ids")
        if not isinstance(raw_player_ids, list):
            raise ValueError("请选择球员")
        player_ids = list(
            dict.fromkeys(int(value or 0) for value in raw_player_ids)
        )
        if not player_ids or any(player_id <= 0 for player_id in player_ids):
            raise ValueError("请选择有效球员")
        if len(player_ids) > 200:
            raise ValueError("单次最多奖励 200 名球员")
        requested_team_id = int(payload.get("team_id") or 0)
        results: list[dict[str, Any]] = []
        failure: dict[str, Any] | None = None
        with runtime.memory_lock:
            manager, manager_id, game_date = (
                runtime._canteen_sea_cucumber_context()
            )
            with io.memory_session_factory() as memory_session:
                for player_id in player_ids:
                    try:
                        results.append(runtime._canteen_sea_cucumber_one(
                            player_id, requested_team_id, manager=manager,
                            manager_id=manager_id, game_date=game_date,
                            memory_session=memory_session,
                        ))
                    except Exception as error:
                        failure = {
                            "player_id": player_id,
                            **io.describe_error(
                                error, operation="sea_cucumber_batch",
                            ),
                        }
                        break
        return {
            "requested": len(player_ids), "completed": len(results),
            "results": results, "failure": failure,
            "economy": io.public_economy(),
        }

    def context(self) -> tuple[dict[str, Any], int, str]:
        runtime = self._runtime
        io = self._io
        with runtime.lock:
            runtime._bind_current_save()
            manager = dict(runtime.output.get("manager") or {})
            manager_id = int(
                runtime.output.get("selected_manager_id")
                or manager.get("id") or 0
            )
            fallback_date = str(runtime.output.get("game_date") or "")
        game_date = str((io.read_game_clock() or {}).get("date") or fallback_date)
        return manager, manager_id, game_date

    def reward_player(
        self, player_id: int, requested_team_id: int, *,
        manager: dict[str, Any], manager_id: int, game_date: str,
        memory_session: Any = None,
    ) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        price = io.local_purchase_price(io.base_price)
        profile_kwargs = (
            {"memory_session": memory_session}
            if callable(getattr(memory_session, "resolve_roster_player", None))
            else {}
        )
        target = runtime._live_player_effect_target(
            player_id, requested_team_id, **profile_kwargs,
            missing_message="所选球员不属于当前执教俱乐部，请先刷新队伍",
        )
        player = target.player
        team = target.team
        if str(team.get("team_type") or "club") != "club":
            raise ValueError("国家队球员不能使用球队食堂奖励")
        team_id = target.team_id
        current_intimacy = int(player.get("manager_intimacy") or 0)
        player_name = str(player.get("name") or player_id)

        payment: dict[str, Any] | None = None
        condition: dict[str, Any] | None = None
        if memory_session:
            apply_effect = lambda: memory_session.apply_effect(
                player_id, target.address,
            )
            apply_intimacy = lambda _condition: memory_session.apply_intimacy(
                player_id, target.address, manager_id, team_id,
                team_address=team.get("address"),
                manager_address=manager.get("manager_address"),
            )
            rollback_effect = memory_session.restore
        else:
            apply_effect = lambda: io.apply_effect(
                player_id, target.address,
            )
            apply_intimacy = lambda _condition: io.apply_intimacy(
                player_id, target.address, manager_id, team_id,
                team_address=team.get("address"),
                manager_address=manager.get("manager_address"), points=1,
            )
            rollback_effect = io.restore_effect
        try:
            payment = io.charge_combined_funds(
                price, "canteen_sea_cucumber",
                player_id=player_id, player_name=player_name,
                manager_id=manager_id, team_id=team_id, game_date=game_date,
            )
            transaction = io.commit_player_effect(
                apply_effect=apply_effect,
                persist_effect=apply_intimacy,
                rollback_effect=rollback_effect,
            )
            condition = transaction.native
            intimacy = transaction.persisted
        except Exception:
            try:
                if condition:
                    rollback_effect(condition)
            finally:
                if payment:
                    io.refund_combined_funds(
                        payment, "canteen_sea_cucumber_rollback",
                        player_id=player_id, player_name=player_name,
                    )
            raise

        public_condition = {
            key: value for key, value in condition.items()
            if not key.startswith("_")
        }
        with runtime.lock:
            player["fitness"] = 100.0
            player["sharpness"] = 100.0
            player["manager_intimacy"] = int(
                intimacy.get("after") or current_intimacy
            )
        return {
            "player_id": player_id, "player_name": player_name,
            "price_gbp": price, "payment": payment,
            "condition": public_condition,
            "fitness": public_condition["fitness"],
            "sharpness": public_condition["sharpness"],
            "intimacy": intimacy,
        }
