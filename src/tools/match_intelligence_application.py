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

from tools.domain_errors import ConflictError, DomainError, UnavailableError, ValidationError


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
    match_intelligence_probe_in_flight: bool
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
        try:
            completed, _response = self._probe(force=force)
            return completed
        except DomainError:
            return False

    def refresh(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Search the bounded result cache for an explicitly scoped request."""
        requested_scope_id = str(payload.get("data_scope_id") or "").strip()
        if not requested_scope_id:
            raise ValidationError(
                "缺少当前存档账户，请刷新后重试",
                code="match_intelligence_scope_required", phase="validate_context",
            )
        _completed, response = self._probe(
            force=True,
            requested_scope_id=requested_scope_id,
            project=True,
        )
        assert response is not None
        return response

    def _validate_context(self, requested_scope_id: str = "") -> tuple[str, str]:
        """Read identity and availability only while the runtime lock is held."""
        runtime = self._runtime
        output = runtime.output
        if output.get("save_identity_discovery_deferred") or runtime.save_change_pending:
            raise ConflictError(
                "正在确认存档身份，请稍后重试",
                code="match_intelligence_save_pending", phase="validate_context",
            )
        save_id = str(output.get("save_instance_id") or "")
        if not runtime._has_verified_save() or not save_id:
            raise ValidationError(
                "尚未识别当前存档", code="match_intelligence_save_required",
                phase="validate_context",
            )
        scope_id = str(runtime._data_scope_id(output) or "")
        if not scope_id:
            raise ValidationError(
                "尚未识别当前存档账户", code="match_intelligence_scope_required",
                phase="validate_context",
            )
        if requested_scope_id and requested_scope_id != scope_id:
            raise ConflictError(
                "当前存档已变化，请刷新后重试",
                code="match_intelligence_scope_changed", phase="validate_context",
            )
        if runtime.refreshing or runtime.reconciling or getattr(
            runtime, "match_intelligence_probe_in_flight", False,
        ):
            raise self._busy_error()
        return scope_id, save_id

    @staticmethod
    def _busy_error() -> ConflictError:
        return ConflictError(
            "情报中心当前正忙，请稍后重试",
            code="match_intelligence_busy", phase="read",
        )

    def _clock(self) -> tuple[str, int]:
        runtime = self._runtime
        clock = dict(runtime.last_connection_clock or {})
        game_date = str(clock.get("date") or runtime.output.get("game_date") or "")
        try:
            game_minutes = int(clock["minutes"])
        except (KeyError, TypeError, ValueError):
            game_minutes = -1
        if not game_date or not 0 <= game_minutes < 24 * 60:
            raise UnavailableError(
                "无法确认当前游戏时间，请稍后重试",
                code="match_intelligence_clock_unavailable", phase="read",
            )
        return game_date, game_minutes

    def _check_probe_context(
        self, scope_id: str, save_id: str, clock: tuple[str, int],
    ) -> None:
        runtime = self._runtime
        try:
            current_clock = self._clock()
        except UnavailableError:
            current_clock = None
        if (
            not runtime._has_verified_save()
            or runtime.refreshing or runtime.reconciling or runtime.save_change_pending
            or runtime.output.get("save_identity_discovery_deferred")
            or str(runtime.output.get("save_instance_id") or "") != save_id
            or str(runtime._data_scope_id(runtime.output) or "") != scope_id
            or runtime.match_intelligence_public_cache_scope_id != scope_id
            or not runtime.match_intelligence_public_cache.get("unlocked")
            or current_clock != clock
        ):
            raise ConflictError(
                "存档、游戏时间或情报中心状态已变化，请重新尝试",
                code="match_intelligence_context_changed", phase="read",
            )

    def _probe(
        self, *, force: bool, requested_scope_id: str = "", project: bool = False,
    ) -> tuple[bool, dict[str, Any] | None]:
        runtime = self._runtime
        io = self._io
        now = io.monotonic()
        with runtime.lock:
            scope_id, save_id = self._validate_context(requested_scope_id)
            if (
                not force
                and now - float(runtime.match_intelligence_last_probe_at or 0.0)
                < self._poll_seconds
            ):
                return False, None
            runtime.match_intelligence_last_probe_at = now
            game_date, game_minutes = self._clock()
            if (
                runtime.match_intelligence_public_cache_scope_id != scope_id
                or not runtime.match_intelligence_public_cache.get("unlocked")
            ):
                raise ValidationError(
                    "情报中心尚未解锁", code="activity_centre_locked",
                    phase="validate_context",
                )
            matches = deepcopy(runtime.output.get("matches", []))
            runtime.match_intelligence_probe_in_flight = True
            runtime.match_intelligence_last_error = None
        try:
            io.set_active_save_id(scope_id)
            if not runtime.memory_lock.acquire(blocking=False):
                raise self._busy_error()
            try:
                try:
                    probe = io.probe_candidates(
                        matches, game_date, game_minutes,
                        force_bounded_rescan=force,
                    )
                except Exception as error:
                    raise UnavailableError(
                        "获取情报失败，请稍后重试",
                        code="match_intelligence_probe_failed", phase="read",
                    ) from error
            finally:
                runtime.memory_lock.release()
            with runtime.lock:
                self._check_probe_context(scope_id, save_id, (game_date, game_minutes))
                try:
                    # A completed scan is authoritative: retaining old rows can
                    # resurrect evidence that the reader has just rejected.
                    current_candidates = io.current_candidates(
                        [dict(item) for item in (probe.get("candidates") or [])
                         if item.get("fixture_id")],
                        deepcopy(runtime.output.get("matches", [])),
                        game_date, game_minutes,
                    )
                    candidates = sorted(current_candidates, key=lambda item: (
                        str(item.get("fixture_date") or ""),
                        int(item.get("kickoff_minutes") or 24 * 60),
                        str(item.get("competition_name") or ""),
                        str((item.get("home") or {}).get("name") or ""),
                    ))
                    intelligence = io.open_status(candidates, game_date) if project else None
                    before = json.dumps(
                        runtime.match_intelligence_results,
                        ensure_ascii=False, sort_keys=True, default=str,
                    )
                    after = json.dumps(
                        candidates, ensure_ascii=False, sort_keys=True, default=str,
                    )
                    cached = deepcopy(intelligence) if project else None
                except Exception as error:
                    raise UnavailableError(
                        "无法生成最新情报状态，请稍后重试",
                        code="match_intelligence_projection_failed", phase="read",
                    ) from error
                self._check_probe_context(scope_id, save_id, (game_date, game_minutes))
                runtime.match_intelligence_results = candidates
                runtime.match_intelligence_last_error = None
                if project:
                    runtime.match_intelligence_public_cache = cached
                    runtime.match_intelligence_public_cache_scope_id = scope_id
                if before != after:
                    runtime.data_version += 1
                return True, (
                    {"intelligence": intelligence, "data_scope_id": scope_id}
                    if project else None
                )
        except DomainError as error:
            with runtime.lock:
                if (
                    str(runtime._data_scope_id(runtime.output) or "") == scope_id
                    and str(runtime.output.get("save_instance_id") or "") == save_id
                ):
                    runtime.match_intelligence_last_error = str(error.__cause__ or error)
            raise
        finally:
            with runtime.lock:
                runtime.match_intelligence_probe_in_flight = False

    def public_status(self) -> dict[str, Any]:
        runtime = self._runtime
        io = self._io
        # Scope, candidate snapshot and cache publication share the same owner
        # lock as refresh and account switches, including projection I/O.
        with runtime.lock:
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
