"""Characterize the application boundary without loading native DLLs or FM.

The facade slice executes the actual method bodies, not a substitute runtime
module. Full HTTP/native import regression remains a separate integration check.
"""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import secrets
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1] / "src"
FACADE_METHODS = {
    "_match_intelligence_application", "_probe_match_intelligence_if_idle",
    "watch_match_intelligence", "public_match_intelligence", "buy_match_intelligence",
}
HELPERS = {
    "random_match_intelligence_candidate", "current_match_intelligence_candidates",
    "purchasable_match_intelligence_candidates",
}


class RecordingLock:
    def __init__(self, name, events):
        self.name, self.events = name, events
        self.depth = 0
        self.available = True

    def acquire(self, blocking=True):
        self.events.append((self.name, "acquire", blocking))
        if not self.available:
            return False
        self.depth += 1
        return True

    def release(self):
        assert self.depth > 0
        self.depth -= 1
        self.events.append((self.name, "release"))

    def __enter__(self):
        assert self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


def fixture_row(home_id=10, *, kickoff=900):
    return {
        "fixture_id": f"2028-06-10|7|{home_id}|20",
        "fixture_date": "2028-06-10", "kickoff_minutes": kickoff,
        "kickoff_time": "15:00", "competition_id": 7,
        "competition_name": "League", "home": {"id": home_id, "name": "Home"},
        "away": {"id": 20, "name": "Away"}, "home_goals": 2, "away_goals": 1,
    }


@pytest.fixture(scope="module")
def facade_code():
    """Load only the application seam; never suppress native import failures."""
    tree = ast.parse((ROOT / "fm_odds_web.py").read_text(encoding="utf-8"))
    body = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module in {
            "__future__", "tools.match_intelligence_application",
        }:
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in HELPERS:
            body.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == "LocalOddsState":
            node.body = [method for method in node.body
                         if isinstance(method, ast.FunctionDef)
                         and method.name in FACADE_METHODS]
            body.append(node)
    targets = ast.parse(
        (ROOT / "tools" / "preview_cup_odds.py").read_text(encoding="utf-8")
    )
    body.extend(node for node in targets.body if isinstance(node, ast.FunctionDef)
                and node.name == "open_match_intelligence_targets")
    return compile(ast.Module(body=body, type_ignores=[]), "<intelligence facade>", "exec")


@pytest.fixture
def harness(facade_code):
    events = []
    scope = {"id": "account-a"}
    namespace = {
        "Any": Any, "deepcopy": deepcopy, "json": json, "secrets": secrets,
        "MATCH_INTELLIGENCE_POLL_SECONDS": 5.0, "monotonic": lambda: 100.0,
        "set_active_save_id": lambda value: events.append(("bind_scope", value)),
        "probe_match_intelligence_candidates": lambda *args, **kwargs: {"candidates": [fixture_row()]},
        "open_match_intelligence_status": lambda rows, day: {"unlocked": True, "candidates": rows},
        "match_intelligence_status": lambda rows, **kwargs: {"unlocked": True, "candidates": rows},
        "read_game_clock": lambda: {"date": "2028-06-10", "minutes": 900},
        "load_economy": lambda: {"match_intelligence_purchases": {}},
        "public_economy": lambda: {"bank_balance": 25},
        "welfare_status": lambda: {"enabled": False},
    }
    exec(facade_code, namespace)
    state = namespace["LocalOddsState"]()
    state.lock = RecordingLock("state", events)
    state.memory_lock = RecordingLock("memory", events)
    state.output = {"save_instance_id": "career-a", "game_date": "2028-06-10",
                    "matches": [fixture_row()]}
    state.last_connection_clock = {"date": "2028-06-10", "minutes": 900}
    state.refreshing = state.reconciling = state.save_change_pending = False
    state.match_intelligence_last_probe_at = 0.0
    state.match_intelligence_last_error = "old error"
    state.match_intelligence_public_cache_scope_id = "account-a"
    state.match_intelligence_public_cache = {"unlocked": True, "candidates": []}
    state.match_intelligence_results = []
    state.data_version = 7
    state._has_verified_save = lambda: True
    state._data_scope_id = lambda output: scope["id"]
    state._bind_current_save = lambda: events.append(("bind_current", scope["id"]))

    def purchase(row, tier, submission_id, **kwargs):
        assert state.lock.depth == 1 and state.memory_lock.depth == 0
        events.append(("purchase", row["fixture_id"], tier, submission_id, kwargs))
        return {"purchase": {"fixture_id": row["fixture_id"], "tier": tier}}

    namespace["purchase_match_intelligence"] = purchase
    return SimpleNamespace(state=state, globals=namespace, events=events, scope=scope)


@pytest.mark.parametrize("gate", ["unverified", "refreshing", "reconciling", "save_change_pending"])
def test_probe_gates_do_not_touch_memory_or_advance_throttle(harness, gate):
    state = harness.state
    if gate == "unverified":
        state._has_verified_save = lambda: False
    else:
        setattr(state, gate, True)
    assert state._probe_match_intelligence_if_idle(force=True) is False
    assert state.match_intelligence_last_probe_at == 0
    assert not any(event[0] == "memory" for event in harness.events)


def test_probe_throttle_and_forced_probe_keep_nonblocking_memory_acquisition(harness):
    state = harness.state
    state.match_intelligence_last_probe_at = 98.0
    assert state._probe_match_intelligence_if_idle() is False
    assert state.match_intelligence_last_probe_at == 98
    assert state._probe_match_intelligence_if_idle(force=True) is True
    assert state.match_intelligence_last_probe_at == 100
    assert ("memory", "acquire", False) in harness.events
    assert state.match_intelligence_results == [fixture_row()]


@pytest.mark.parametrize("mode", ["wrong_scope", "locked", "missing_minutes", "missing_scope"])
def test_probe_requires_valid_clock_and_scope_bound_unlock(harness, mode):
    state = harness.state
    if mode == "wrong_scope":
        state.match_intelligence_public_cache_scope_id = "account-b"
    elif mode == "locked":
        state.match_intelligence_public_cache["unlocked"] = False
    elif mode == "missing_minutes":
        state.last_connection_clock.pop("minutes")
    else:
        harness.scope["id"] = ""
    assert state._probe_match_intelligence_if_idle() is False
    assert state.match_intelligence_last_probe_at == 100
    assert not any(event[0] == "memory" for event in harness.events)


def test_probe_memory_contention_returns_without_reading_or_releasing_unowned_lock(harness):
    state = harness.state
    state.memory_lock.available = False
    assert state._probe_match_intelligence_if_idle() is False
    assert state.match_intelligence_results == []
    assert [event for event in harness.events if event[0] == "memory"] == [
        ("memory", "acquire", False),
    ]


def test_probe_failure_releases_memory_and_records_error_without_publishing(harness):
    def fail(*args, **kwargs):
        raise RuntimeError("probe failed")

    harness.globals["probe_match_intelligence_candidates"] = fail
    state = harness.state
    assert state._probe_match_intelligence_if_idle() is False
    assert state.match_intelligence_last_error == "probe failed"
    assert state.memory_lock.depth == state.lock.depth == 0
    assert state.data_version == 7


def test_probe_merges_filters_and_only_versions_changed_candidates(harness):
    state = harness.state
    stale = fixture_row(30)
    state.match_intelligence_results = [stale]
    assert state._probe_match_intelligence_if_idle() is True
    assert state.match_intelligence_results == [fixture_row()]
    assert state.data_version == 8
    assert state.match_intelligence_last_error is None
    assert state._probe_match_intelligence_if_idle(force=True) is True
    assert state.data_version == 8


@pytest.mark.parametrize("field,value,reason", [
    ("save_change_pending", True, "正在确认"),
    ("save_instance_id", "", "尚未识别当前存档"),
    ("save_identity_discovery_deferred", True, "正在确认"),
    ("scope", "", "尚未识别当前存档账户"),
])
def test_public_status_rejects_unknown_account_identity(harness, field, value, reason):
    if field == "save_change_pending":
        harness.state.save_change_pending = value
    elif field == "scope":
        harness.scope["id"] = value
    else:
        harness.state.output[field] = value
    with pytest.raises(ValueError, match=reason):
        harness.state.public_match_intelligence()
    assert harness.events == []


def test_public_status_cross_scope_fallback_does_not_reveal_old_candidates(harness):
    state = harness.state
    state.match_intelligence_results = [fixture_row()]
    harness.scope["id"] = "account-b"
    result = state.public_match_intelligence()
    assert result["candidates"] == [] and result["refreshing"] is True
    assert result["unlocked"] is False
    assert result["pricing_basis"] == "fixed_price"
    assert result["pricing"] == {"game_date": ""}
    assert harness.events == [("bind_scope", "account-b")]


@pytest.mark.parametrize("minutes,expected", [(900, 1), (901, 0), (None, 0)])
def test_public_status_filters_by_clock_and_isolates_cached_response(harness, minutes, expected):
    state = harness.state
    state.last_connection_clock["minutes"] = minutes
    state.match_intelligence_results = [fixture_row()]
    result = state.public_match_intelligence()
    assert len(result["candidates"]) == expected
    result["candidates"].append({"caller": "changed"})
    assert len(state.match_intelligence_public_cache["candidates"]) == expected
    assert harness.events == [("bind_scope", "account-a")]


def purchase_payload(**extra):
    return {"fixture_id": "2028-06-10|7|10|20", "tier": "outcome",
            "client_submission_id": "request-a", **extra}


def test_purchase_keeps_clock_lock_order_scope_and_guarded_response_projection(harness):
    state = harness.state
    state.match_intelligence_results = [fixture_row()]

    def clock():
        assert state.memory_lock.depth == 1 and state.lock.depth == 0
        return {"date": "2028-06-10", "minutes": 900}

    def economy():
        assert state.memory_lock.depth == 0 and state.lock.depth == 1
        return {"bank_balance": 25}

    harness.globals["read_game_clock"] = clock
    harness.globals["public_economy"] = economy
    result = state.buy_match_intelligence(purchase_payload())
    assert harness.events[:4] == [
        ("memory", "acquire", True), ("memory", "release"),
        ("state", "acquire", True), ("bind_current", "account-a"),
    ]
    assert result == {
        "purchase": {"fixture_id": "2028-06-10|7|10|20", "tier": "outcome"},
        "intelligence": {"unlocked": True, "candidates": [fixture_row()]},
        "economy": {"bank_balance": 25}, "welfare": {"enabled": False},
    }
    assert state.match_intelligence_public_cache_scope_id == "account-a"
    result["intelligence"]["candidates"].clear()
    assert state.match_intelligence_public_cache["candidates"] == [fixture_row()]
    assert state.lock.depth == state.memory_lock.depth == 0


@pytest.mark.parametrize("clock", [None, {}, {"date": "2028-06-10"}, {"minutes": 900}])
def test_purchase_unknown_clock_cannot_charge(harness, clock):
    harness.globals["read_game_clock"] = lambda: clock
    with pytest.raises(ValueError, match="无法确认当前游戏时间"):
        harness.state.buy_match_intelligence(purchase_payload())
    assert not any(event[0] == "purchase" for event in harness.events)
    assert harness.state.lock.depth == harness.state.memory_lock.depth == 0


def test_random_retry_uses_existing_expired_purchase_without_reselection(harness):
    state = harness.state
    existing = {"fixture_id": "2028-06-10|7|10|20", "fixture_date": "2028-06-10",
                "payments": [{"client_submission_id": "request-a"}]}
    harness.globals["load_economy"] = lambda: {"match_intelligence_purchases": {"old": existing}}
    harness.globals["read_game_clock"] = lambda: {"date": "2028-06-10", "minutes": 901}

    def unexpected_random(*args):
        pytest.fail("a repeated submission must not select a different fixture")

    harness.globals["random_match_intelligence_candidate"] = unexpected_random
    result = state.buy_match_intelligence(purchase_payload(random=True))
    assert result["purchase"]["fixture_id"] == "2028-06-10|7|10|20"
    assert result["intelligence"]["candidates"] == []
    payment = next(event for event in harness.events if event[0] == "purchase")
    assert payment[3:] == ("request-a", {"game_date": "2028-06-10", "purchase_mode": "random"})


def test_random_purchase_does_not_offer_already_purchased_tier(harness):
    state = harness.state
    state.match_intelligence_results = [fixture_row()]
    harness.globals["match_intelligence_status"] = lambda *args, **kwargs: {
        "candidates": [{"fixture_id": "2028-06-10|7|10|20",
                        "tiers": [{"key": "outcome", "purchased": True}]}],
    }
    with pytest.raises(ValueError, match="当前没有尚未获取的随机比赛情报"):
        state.buy_match_intelligence(purchase_payload(random=True))
    assert not any(event[0] == "purchase" for event in harness.events)


def test_failed_purchase_does_not_replace_public_cache(harness):
    state = harness.state
    state.match_intelligence_results = [fixture_row()]
    before = deepcopy(state.match_intelligence_public_cache)

    def reject(*args, **kwargs):
        raise ValueError("insufficient funds")

    harness.globals["purchase_match_intelligence"] = reject
    with pytest.raises(ValueError, match="insufficient funds"):
        state.buy_match_intelligence(purchase_payload())
    assert state.match_intelligence_public_cache == before
    assert state.lock.depth == state.memory_lock.depth == 0


def test_later_facade_call_uses_current_dependency_replacements(harness):
    state = harness.state
    state.match_intelligence_results = [fixture_row()]
    assert len(state.public_match_intelligence()["candidates"]) == 1
    harness.globals["open_match_intelligence_status"] = lambda *args: {"candidates": []}
    assert state.public_match_intelligence() == {"candidates": []}


def test_service_can_publish_with_explicit_dependencies_without_http_runtime():
    from tools.match_intelligence_application import (
        MatchIntelligenceApplicationService, MatchIntelligenceIO,
    )

    def unexpected(*args, **kwargs):
        pytest.fail("public status must not probe, charge, or read native memory")

    runtime = SimpleNamespace(
        output={"save_instance_id": "career-a", "game_date": "2028-06-10", "matches": []},
        save_change_pending=False,
        last_connection_clock={"date": "2028-06-10", "minutes": 900},
        match_intelligence_public_cache_scope_id="account-a",
        match_intelligence_results=[],
        _data_scope_id=lambda output: "account-a",
    )
    bound = []
    io = MatchIntelligenceIO(
        monotonic=unexpected, set_active_save_id=bound.append,
        probe_candidates=unexpected, current_candidates=lambda *args: [],
        read_game_clock=unexpected, open_status=lambda rows, day: {"candidates": rows},
        status=unexpected, load_economy=unexpected, random_candidate=unexpected,
        purchase=unexpected, public_economy=unexpected, welfare_status=unexpected,
    )
    service = MatchIntelligenceApplicationService(runtime, io, poll_seconds=5.0)
    assert service.public_status() == {"candidates": []}
    assert bound == ["account-a"]
    assert runtime.match_intelligence_public_cache == {"candidates": []}
