"""Single psychological-counseling use case.

The service owns the use-case control flow, compensation order and response
shape only.  ``LocalOddsState`` remains the single owner of runtime state,
locks and save/manager binding; all external domain
and wallet collaborators are supplied through the frozen :class:`CounselingIO`
callables so importing this module never imports the HTTP entrypoint or the
native FM core.
"""
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Protocol

from tools.domain_errors import CounselingCommitUnknownError, DomainError
from tools.player_effects import PlayerEffectRollbackError


class _CounselingCompensationError(DomainError):
    """Retain private causes while publishing only safe compensation state."""

    def __init__(
        self, operation_error: Exception, compensation_error: Exception, *,
        phase: str, native_restored: bool,
    ) -> None:
        super().__init__(
            f"{phase}_incomplete", "心理辅导补偿未完成，请勿重复操作",
            HTTPStatus.INTERNAL_SERVER_ERROR, phase, False,
            {
                "native_restored": native_restored, "wallet_debited": True,
                "refund_attempted": phase == "refund",
                "refund_state": "unknown" if phase == "refund" else "not_attempted",
            },
            "error.request_failed",
        )
        self.operation_error = operation_error
        if phase == "rollback":
            self.rollback_error = compensation_error
        else:
            self.refund_error = compensation_error


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
                # Paid counseling only clears unhappiness. Legacy relationship
                # writes do not provide an exact undo token for this use case.
                if outcome != "unlocked" or points != 0:
                    raise ValueError("心理辅导仅支持清除不满且不改变亲密度")
                effect = io.apply_effect(player_id, player_address, outcome)
                applied_effect = effect
                public_effect = {
                    key: value for key, value in effect.items()
                    if not key.startswith("_")
                }
                return {
                    "before": current_intimacy, "after": current_intimacy,
                    "applied": 0, "effect": public_effect,
                }

            try:
                result = io.perform_counseling(
                    manager_id, player_id, player_name, game_date,
                    current_intimacy, apply_effects,
                )
            except Exception as operation_error:
                if isinstance(operation_error, CounselingCommitUnknownError):
                    # Neither native state nor payment can be reversed while
                    # the session may already be durably recorded.
                    raise
                if isinstance(operation_error, PlayerEffectRollbackError):
                    raise _CounselingCompensationError(
                        operation_error.operation_error, operation_error.rollback_error,
                        phase="rollback", native_restored=False,
                    ) from operation_error.operation_error
                if applied_effect is not None:
                    try:
                        io.restore_effect(applied_effect)
                    except Exception as rollback_error:
                        raise _CounselingCompensationError(
                            operation_error, rollback_error,
                            phase="rollback", native_restored=False,
                        ) from operation_error
                try:
                    io.adjust_balance(
                        price, "psychological_counseling_session_rollback",
                        manager_id=manager_id, player_id=player_id,
                        player_name=player_name, game_date=game_date,
                    )
                except Exception as refund_error:
                    raise _CounselingCompensationError(
                        operation_error, refund_error,
                        phase="refund", native_restored=True,
                    ) from operation_error
                raise
            result["payment"] = payment
            result["relationship_archived"] = False
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
            # The session is complete. A failed view refresh cannot change
            # that outcome or send the client back through the paid operation.
            response = {"counseling": result}
            for key, project in (
                ("economy", io.public_economy), ("welfare", io.welfare_status),
            ):
                try:
                    response[key] = project()
                except Exception:
                    response["state_refresh_required"] = True
            return response
