"""Match-intelligence probe, public projection and purchase use cases.

The application service owns the use-case control flow only.  The runtime
remains the single owner of state, locks and lifecycle facts; every external
collaborator is supplied through the explicit :class:`MatchIntelligenceIO`
callables so the HTTP entrypoint is neither imported nor proxied here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class MatchIntelligenceIO:
    """Explicit collaborators used by the match-intelligence use cases."""

    monotonic: Callable[[], float]
    set_active_save_id: Callable[[str], None]
    probe_candidates: Callable[..., Any]
    current_candidates: Callable[..., Any]
    read_game_clock: Callable[[], Any]
    open_status: Callable[..., Any]
    status: Callable[..., Any]
    load_economy: Callable[[], Any]
    random_candidate: Callable[..., Any]
    purchase: Callable[..., Any]
    public_economy: Callable[[], Any]
    welfare_status: Callable[[], Any]


class MatchIntelligenceRuntime(Protocol):
    """State, locks and callbacks consumed from the owning runtime.

    The implementation only documents what the use cases read or mutate; it
    does not store state and is never constructed by the service.
    """

    output: dict[str, Any]
    last_connection_clock: dict[str, Any] | None
    refreshing: bool
    reconciling: bool
    save_change_pending: bool
    lock: Any
    memory_lock: Any
    match_intelligence_last_probe_at: float
    match_intelligence_last_error: str | None
    match_intelligence_public_cache_scope_id: str
    match_intelligence_public_cache: dict[str, Any]
    match_intelligence_results: list[dict[str, Any]]
    data_version: int

    def _has_verified_save(self) -> bool: ...

    def _data_scope_id(self, output: dict[str, Any]) -> str: ...

    def _bind_current_save(self) -> Any: ...


class MatchIntelligenceApplicationService:
    def __init__(
        self,
        runtime: MatchIntelligenceRuntime,
        io: MatchIntelligenceIO,
        *,
        poll_seconds: float,
    ) -> None:
        self._runtime = runtime
        self._io = io
        self._poll_seconds = poll_seconds

    def probe_if_idle(self, *, force: bool = False) -> bool:
        runtime = self._runtime
        io = self._io
        now = io.monotonic()
        with runtime.lock:
            if (
                not runtime._has_verified_save()
                or runtime.refreshing
                or runtime.reconciling
                or runtime.save_change_pending
            ):
                return False
            if (
                not force
                and now - float(runtime.match_intelligence_last_probe_at or 0.0)
                < self._poll_seconds
            ):
                return False
            output = dict(runtime.output)
            output["matches"] = [
                dict(match) for match in runtime.output.get("matches", [])
            ]
            clock = dict(runtime.last_connection_clock or {})
            scope_id = runtime._data_scope_id(runtime.output)
            runtime.match_intelligence_last_probe_at = now
        game_date = str(clock.get("date") or output.get("game_date") or "")
        try:
            game_minutes = int(clock.get("minutes"))
        except (TypeError, ValueError):
            return False
        if not game_date or not scope_id:
            return False
        io.set_active_save_id(scope_id)
        with runtime.lock:
            intelligence_unlocked = bool(
                runtime.match_intelligence_public_cache_scope_id == scope_id
                and runtime.match_intelligence_public_cache.get("unlocked")
            )
        if not intelligence_unlocked:
            return False
        if not runtime.memory_lock.acquire(blocking=False):
            return False
        try:
            probe = io.probe_candidates(
                output.get("matches", []), game_date, game_minutes,
            )
        except Exception as error:
            with runtime.lock:
                runtime.match_intelligence_last_error = (
                    str(error).strip() or type(error).__name__
                )
            return False
        finally:
            runtime.memory_lock.release()
        discovered = {
            str(item.get("fixture_id") or ""): dict(item)
            for item in (probe.get("candidates") or [])
            if item.get("fixture_id")
        }
        with runtime.lock:
            merged = {
                str(item.get("fixture_id") or ""): dict(item)
                for item in runtime.match_intelligence_results
                if item.get("fixture_id")
            }
            merged.update(discovered)
            current_candidates = io.current_candidates(
                list(merged.values()), output.get("matches", []),
                game_date, game_minutes,
            )
            candidates = sorted(current_candidates, key=lambda item: (
                str(item.get("fixture_date") or ""),
                int(item.get("kickoff_minutes") or 24 * 60),
                str(item.get("competition_name") or ""),
                str((item.get("home") or {}).get("name") or ""),
            ))
            before = json.dumps(
                runtime.match_intelligence_results,
                ensure_ascii=False, sort_keys=True, default=str,
            )
            after = json.dumps(
                candidates,
                ensure_ascii=False, sort_keys=True, default=str,
            )
            runtime.match_intelligence_results = candidates
            runtime.match_intelligence_last_error = None
            if before != after:
                runtime.data_version += 1
        return True

    def public_status(self) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        output = dict(runtime.output)
        if output.get("save_identity_discovery_deferred") or runtime.save_change_pending:
            raise ValueError("正在确认存档身份，请稍后重试")
        if not output.get("save_instance_id"):
            raise ValueError("尚未识别当前存档")
        scope_id = runtime._data_scope_id(output)
        if not scope_id:
            raise ValueError("尚未识别当前存档账户")
        io.set_active_save_id(scope_id)
        if runtime.match_intelligence_public_cache_scope_id != scope_id:
            return {
                "unlocked": False,
                "floor": "5F",
                "pricing_basis": "fixed_price",
                "pricing": {"game_date": ""},
                "candidates": [],
                "refreshing": True,
            }
        clock = dict(runtime.last_connection_clock or {})
        game_date = str(clock.get("date") or output.get("game_date") or "")
        try:
            game_minutes = int(clock["minutes"])
        except (KeyError, TypeError, ValueError):
            current_candidates = []
        else:
            current_candidates = io.current_candidates(
                [dict(item) for item in runtime.match_intelligence_results],
                [dict(item) for item in output.get("matches", [])],
                game_date,
                game_minutes,
            )
        intelligence = io.open_status(
            current_candidates, game_date,
        )
        runtime.match_intelligence_public_cache = deepcopy(intelligence)
        return intelligence

    def purchase(self, payload: dict[str, Any]) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        fixture_id = str(payload.get("fixture_id") or "")
        tier = str(payload.get("tier") or "")
        random_purchase = bool(payload.get("random"))
        submission_id = str(payload.get("client_submission_id") or "").strip()
        with runtime.memory_lock:
            clock = io.read_game_clock()
        with runtime.lock:
            runtime._bind_current_save()
            current_date = str((clock or {}).get("date") or "")
            try:
                current_minutes = int((clock or {})["minutes"])
            except (KeyError, TypeError, ValueError):
                raise ValueError("无法确认当前游戏时间，请稍后重试") from None
            if not current_date:
                raise ValueError("无法确认当前游戏时间，请稍后重试")
            open_candidates = io.current_candidates(
                [dict(item) for item in runtime.match_intelligence_results],
                [dict(item) for item in runtime.output.get("matches", [])],
                current_date,
                current_minutes,
            )
            existing_purchase = None
            if random_purchase:
                existing_purchase = next((
                    dict(purchase)
                    for purchase in dict(
                        io.load_economy().get("match_intelligence_purchases") or {}
                    ).values()
                    if any(
                        str(payment.get("client_submission_id") or "") == submission_id
                        for payment in purchase.get("payments") or []
                    )
                ), None)
                if existing_purchase:
                    fixture_id = str(existing_purchase.get("fixture_id") or "")
                    candidate = next((
                        dict(item) for item in runtime.match_intelligence_results
                        if str(item.get("fixture_id") or "") == fixture_id
                    ), existing_purchase)
                else:
                    current_status = io.status(
                        open_candidates, pricing_date=current_date,
                    )
                    candidate = io.random_candidate(
                        open_candidates, current_status, tier,
                    )
                    if not candidate:
                        raise ValueError("当前没有尚未获取的随机比赛情报")
                    fixture_id = str(candidate.get("fixture_id") or "")
            else:
                candidate = next((
                    dict(item) for item in open_candidates
                    if str(item.get("fixture_id") or "") == fixture_id
                ), None)
            if not candidate:
                raise ValueError("这场比赛当前没有可获取的比赛情报")
            fixture_date = str(candidate.get("fixture_date") or "")
            kickoff = candidate.get("kickoff_minutes")
            if not (random_purchase and existing_purchase) and (
                not current_date
                or fixture_date < current_date
                or (
                    fixture_date == current_date
                    and (kickoff is None or int(kickoff) < current_minutes)
                )
            ):
                raise ValueError("该场比赛的情报获取窗口已经结束")
            result = io.purchase(
                candidate, tier, submission_id, game_date=current_date,
                purchase_mode="random" if random_purchase else "specific",
            )
            intelligence = io.status(
                open_candidates,
                pricing_date=current_date,
            )
            runtime.match_intelligence_public_cache = deepcopy(intelligence)
            runtime.match_intelligence_public_cache_scope_id = str(
                runtime._data_scope_id(runtime.output) or ""
            )
            return {
                **result,
                "intelligence": intelligence,
                "economy": io.public_economy(),
                "welfare": io.welfare_status(),
            }
