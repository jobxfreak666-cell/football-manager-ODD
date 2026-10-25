from contextlib import nullcontext
from http import HTTPStatus
from threading import Event, RLock, Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

import fm_odds_web
from tools import club_economy, preview_cup_odds
from tools.domain_errors import ConflictError, UnavailableError, ValidationError


@pytest.fixture(autouse=True)
def default_betting_limit_settings():
    with patch.object(
        club_economy, "load_settings",
        return_value={"betting_limits_enabled": True, "unlimited_betting": True},
    ):
        yield


def candidate(*, tiers=None):
    return {
        "fixture_id": "2028-06-10|7|10|20",
        "fixture_date": "2028-06-10",
        "kickoff_minutes": 900,
        "kickoff_time": "15:00",
        "competition_id": 7,
        "competition_name": "测试联赛",
        "home": {"id": 10, "name": "主队", "address": "0x10"},
        "away": {"id": 20, "name": "客队", "address": "0x20"},
        "home_goals": 2,
        "away_goals": 1,
        "available_tiers": tiers or ["outcome", "total_goals", "score"],
    }


def economy_state(balance=1_000_000.0):
    return {
        "general_balance": balance,
        "general_balance_minor": int(balance * 100),
        "transactions": [],
        "owned_activity_centres": ["intelligence"],
        "owned_activity_facilities": [],
        "match_intelligence_purchases": {},
    }


def test_intelligence_prices_are_fixed_regardless_of_funds_or_date():
    state = economy_state(100_000_000.0)
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
        patch.object(club_economy, "load_wallet", return_value={}),
        patch.object(club_economy, "save_economy") as save,
    ):
        first = club_economy.open_match_intelligence_status([candidate()], "2028-06-10")
        state["general_balance"] = 200_000_000.0
        state["general_balance_minor"] = 20_000_000_000
        next_day = club_economy.open_match_intelligence_status([candidate()], "2028-06-11")
        result = club_economy.purchase_match_intelligence(
            candidate(), "outcome", "fixed-request",
        )

    for status in (first, next_day):
        assert status["pricing_basis"] == "fixed_price"
        assert [tier["price"] for tier in status["candidates"][0]["tiers"]] == [
            40_000_000, 60_000_000, 80_000_000,
        ]
    assert next_day["pricing"] == {"game_date": "2028-06-11"}
    assert result["payment"]["total"] == 40_000_000
    assert state["general_balance"] == 160_000_000
    assert "match_intelligence_price_locks" not in state
    save.assert_called_once_with(state)


def test_fixed_intelligence_prices_ignore_single_betting_limit():
    settings = {
        "betting_limits_enabled": True, "unlimited_betting": False,
        "betting_limit_single": 20_000_000.0,
    }
    with (
        patch.object(club_economy, "load_economy", return_value=economy_state()),
        patch.object(club_economy, "load_settings", return_value=settings),
        patch.object(club_economy, "available_balance", return_value=0.0),
    ):
        row = club_economy.match_intelligence_status([candidate()])["candidates"][0]

    assert [tier["specific_price"] for tier in row["tiers"]] == [
        40_000_000, 60_000_000, 80_000_000,
    ]
    assert [tier["random_price"] for tier in row["tiers"]] == [
        20_000_000, 30_000_000, 60_000_000,
    ]


def test_fixed_intelligence_prices_pass_through_local_purchase_price():
    with (
        patch.object(club_economy, "load_economy", return_value=economy_state()),
        patch.object(club_economy, "available_balance", return_value=0.0),
        patch.object(
            club_economy, "local_purchase_price", side_effect=lambda value: float(value) / 2,
        ) as convert,
    ):
        row = club_economy.match_intelligence_status([candidate()])["candidates"][0]

    assert [tier["price"] for tier in row["tiers"]] == [
        20_000_000, 30_000_000, 40_000_000,
    ]
    assert convert.call_count == 6


def test_mismatched_intelligence_payment_is_refunded_once_and_mailed():
    fixture_id = candidate()["fixture_id"]
    state = economy_state(0.0)
    state["match_intelligence_purchases"] = {
        fixture_id: {
            "fixture_id": fixture_id,
            "home": {"name": "主队"}, "away": {"name": "客队"},
            "predictions": {
                "outcome": {"reveal": {"outcome": "home"}},
            },
            "payments": [{
                "tier": "outcome", "client_submission_id": "intel-1",
                "payment": {"bank": 40.0, "wallet": 60.0,
                             "total": 100.0, "transaction_id": "charge-1"},
            }],
        },
    }
    settled = [{
        "bet_id": "bet-1", "leg_records": [{
            "fixture_date": "2028-06-10", "competition_id": 7,
            "home_id": 10, "away_id": 20,
        }],
        "settlement": [{"score": "0-1"}],
    }]
    mail_records = []
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "load_document", return_value=mail_records),
        patch.object(club_economy, "commit_documents_with_wallet_adjustments") as commit,
    ):
        first = club_economy.reconcile_match_intelligence_refunds(
            settled, "2028-06-11",
        )
        second = club_economy.reconcile_match_intelligence_refunds(
            settled, "2028-06-11",
        )

    assert len(first) == 1
    assert first[0]["total"] == 100.0
    assert first[0]["already_refunded"] is False
    assert second == []
    assert state["match_intelligence_purchases"][fixture_id]["payments"][0]["refunded"]
    commit.assert_called_once()
    adjustments = commit.call_args.args[1]
    assert adjustments[0]["amount"] == 60.0


@pytest.mark.parametrize(
    ("row", "expected_count"),
    [
        (
            {
                "available": True,
                "tiers": [
                    {"key": "outcome", "purchased": False},
                    {"key": "total_goals", "purchased": False},
                    {"key": "score", "purchased": False},
                ],
            },
            1,
        ),
        (
            {
                "available": True,
                "tiers": [
                    {"key": "outcome", "purchased": True},
                    {"key": "total_goals", "purchased": True},
                    {"key": "score", "purchased": True},
                ],
            },
            0,
        ),
        (
            {
                "available": True,
                "tiers": [
                    {"key": "outcome", "purchased": True},
                    {"key": "total_goals", "purchased": False},
                    {"key": "score", "purchased": True},
                ],
            },
            1,
        ),
        (
            {
                "available": False,
                "tiers": [{"key": "outcome", "purchased": False}],
            },
            0,
        ),
        ({"available": True}, 0),
    ],
)
def test_intelligence_notice_only_counts_current_fixtures_with_unpaid_tiers(
    row, expected_count,
):
    candidates = fm_odds_web.purchasable_match_intelligence_candidates(
        {"candidates": [row]}
    )

    assert len(candidates) == expected_count


def test_hidden_history_result_becomes_7f_candidate_only_when_fixture_is_still_open():
    matches = [{
        "fixture_date": "2028-06-10", "kickoff_minutes": 900,
        "kickoff_time": "15:00", "competition_id": 7,
        "competition_name": "测试联赛",
        "home": {"id": 10, "name": "主队"},
        "away": {"id": 20, "name": "客队"},
    }]
    future_result = {
        "date": "2028-06-10", "competition": {"id": 7, "name": "测试联赛"},
        "home_team": {"id": 10, "name": "主队"},
        "away_team": {"id": 20, "name": "客队"},
        "home_goals": 2, "away_goals": 1,
        "result_source": "basic_scoreline",
    }
    unrelated = {
        **future_result,
        "date": "2028-06-09",
    }

    rows = preview_cup_odds.hidden_future_result_candidates(
        object(), [future_result, unrelated], matches, "2028-06-10",
    )

    assert len(rows) == 1
    assert rows[0]["fixture_id"] == "2028-06-10|7|10|20"
    assert rows[0]["available_tiers"] == ["outcome", "total_goals", "score"]
    assert rows[0]["home_goals"] == 2


def test_intelligence_targets_keep_exact_kickoff_and_close_one_minute_later():
    matches = [{
        "fixture_date": "2028-06-10", "kickoff_minutes": 900,
        "kickoff_time": "15:00", "competition_id": 7,
        "fixture_address": "0x1234",
        "home": {"id": 10, "name": "Home"},
        "away": {"id": 20, "name": "Away"},
    }]

    eligible, keys, hints = preview_cup_odds.open_match_intelligence_targets(
        matches, "2028-06-10", 900,
    )
    closed, closed_keys, _closed_hints = (
        preview_cup_odds.open_match_intelligence_targets(
            matches, "2028-06-10", 901,
        )
    )

    key = ("2028-06-10", 7, 10, 20)
    assert eligible == matches
    assert keys == {key}
    assert hints == {key: 0x1234}
    assert closed == []
    assert closed_keys == set()


def test_intelligence_withholds_fixture_when_cached_evidence_has_conflicting_scores():
    matches = [{
        "fixture_date": "2028-06-10", "kickoff_minutes": 900,
        "kickoff_time": "15:00", "competition_id": 7,
        "home": {"id": 10, "name": "Home"},
        "away": {"id": 20, "name": "Away"},
    }]
    base = {
        "date": "2028-06-10",
        "competition": {"id": 7, "name": "Test League"},
        "home_team": {"id": 10, "name": "Home"},
        "away_team": {"id": 20, "name": "Away"},
        "result_source": "basic_scoreline",
    }

    rows = preview_cup_odds.hidden_future_result_candidates(
        object(),
        [
            {**base, "home_goals": 1, "away_goals": 0},
            {**base, "home_goals": 2, "away_goals": 1},
        ],
        matches,
        "2028-06-10",
    )

    assert rows == []


def test_intelligence_withholds_fixture_when_result_conflict_marker_has_no_score():
    matches = [{
        "fixture_date": "2028-06-10", "kickoff_minutes": 900,
        "competition_id": 7,
        "home": {"id": 10, "name": "Home"},
        "away": {"id": 20, "name": "Away"},
    }]
    identity = {
        "date": "2028-06-10",
        "competition": {"id": 7, "name": "Test League"},
        "home_team": {"id": 10, "name": "Home"},
        "away_team": {"id": 20, "name": "Away"},
    }

    rows = preview_cup_odds.hidden_future_result_candidates(
        object(),
        [
            {**identity, "home_goals": 1, "away_goals": 0,
             "result_source": "basic_scoreline"},
            {**identity, "result_conflict": True,
             "result_conflict_candidates": [{"home_goals": 1, "away_goals": 0}]},
        ],
        matches,
        "2028-06-10",
    )

    assert rows == []


def test_current_intelligence_candidates_exclude_every_fixture_before_now():
    previous_day = {**candidate(), "fixture_date": "2028-06-09"}
    earlier_today = {**candidate(), "kickoff_minutes": 899, "kickoff_time": "14:59"}
    exact_now = candidate()
    later_today = {
        **candidate(),
        "fixture_id": "2028-06-10|7|30|40",
        "kickoff_minutes": 901,
        "kickoff_time": "15:01",
        "home": {"id": 30, "name": "稍后主队"},
        "away": {"id": 40, "name": "稍后客队"},
    }
    next_day = {
        **candidate(),
        "fixture_id": "2028-06-11|7|10|20",
        "fixture_date": "2028-06-11",
    }
    absent_from_market = {
        **candidate(),
        "fixture_id": "2028-06-10|7|50|60",
        "home": {"id": 50, "name": "未开盘主队"},
        "away": {"id": 60, "name": "未开盘客队"},
    }
    stale_names = {
        **exact_now,
        "home": {"id": 10, "name": "旧主队名"},
        "away": {"id": 20, "name": "旧客队名"},
    }

    rows = fm_odds_web.current_match_intelligence_candidates(
        [previous_day, earlier_today, stale_names, later_today, next_day,
         absent_from_market],
        [exact_now, later_today, next_day],
        "2028-06-10",
        900,
    )

    assert rows == [exact_now, later_today, next_day]


def test_public_intelligence_projection_excludes_fixture_before_current_time():
    state = object.__new__(fm_odds_web.LocalOddsState)
    state.output = {
        "save_instance_id": "save-1",
        "game_date": "2028-06-10",
        "matches": [candidate()],
    }
    state.save_change_pending = False
    state.last_connection_clock = {
        "date": "2028-06-10",
        "minutes": 901,
    }
    state.match_intelligence_results = [candidate()]
    state.match_intelligence_public_cache_scope_id = "scope-1"
    state.match_intelligence_public_cache = {"unlocked": True}
    state._data_scope_id = lambda _output: "scope-1"

    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "open_match_intelligence_status",
            side_effect=lambda candidates, _game_date: {"candidates": candidates},
        ),
    ):
        result = state.public_match_intelligence()

    assert result["candidates"] == []


def _refreshable_intelligence_state():
    state = object.__new__(fm_odds_web.LocalOddsState)
    state.lock = RLock()
    state.memory_lock = fm_odds_web.ForegroundPriorityLock()
    state.output = {
        "save_instance_id": "save-1",
        "game_date": "2028-06-10",
        "matches": [candidate()],
    }
    state.cache_verified = True
    state.refreshing = False
    state.reconciling = False
    state.save_change_pending = False
    state.last_connection_clock = {"date": "2028-06-10", "minutes": 900}
    state.match_intelligence_results = []
    state.match_intelligence_last_probe_at = 0.0
    state.match_intelligence_last_error = None
    state.match_intelligence_probe_in_flight = False
    state.match_intelligence_public_cache_scope_id = "scope-save-1"
    state.match_intelligence_public_cache = {"unlocked": True}
    state.data_version = 1
    state._data_scope_id = lambda output: f"scope-{output['save_instance_id']}"
    return state


def test_refresh_match_intelligence_forces_probe_and_returns_fresh_projection():
    state = _refreshable_intelligence_state()
    state.match_intelligence_last_probe_at = 10**12
    projection = {"unlocked": True, "candidates": [{"fixture_id": "fresh"}]}
    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "probe_match_intelligence_candidates",
            return_value={"candidates": [candidate()]},
        ) as probe,
        patch.object(
            fm_odds_web, "open_match_intelligence_status",
            return_value=projection,
        ),
    ):
        result = state.refresh_match_intelligence({})

    assert result == {
        "intelligence": projection,
        "data_scope_id": "scope-save-1",
    }
    probe.assert_called_once_with(
        [candidate()], "2028-06-10", 900, force_bounded_rescan=True,
    )
    assert state.match_intelligence_results == [candidate()]


def test_refresh_match_intelligence_reports_busy_memory_reader():
    state = _refreshable_intelligence_state()
    assert state.memory_lock.acquire()
    try:
        with patch.object(fm_odds_web, "probe_match_intelligence_candidates") as probe:
            with pytest.raises(ConflictError, match="忙"):
                state.refresh_match_intelligence({})
    finally:
        state.memory_lock.release()

    probe.assert_not_called()


def test_refresh_match_intelligence_reports_probe_errors_instead_of_success():
    state = _refreshable_intelligence_state()
    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "probe_match_intelligence_candidates",
            side_effect=RuntimeError("reader unavailable"),
        ),
    ):
        with pytest.raises(UnavailableError, match="获取情报失败"):
            state.refresh_match_intelligence({})


def test_refresh_match_intelligence_does_not_publish_across_save_change():
    state = _refreshable_intelligence_state()
    other_candidate = {**candidate(), "fixture_id": "other-save-fixture"}

    def switch_save_during_probe(*_args, **_kwargs):
        state.output = {
            "save_instance_id": "save-2",
            "game_date": "2028-06-10",
            "matches": [other_candidate],
        }
        return {"candidates": [candidate()]}

    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "probe_match_intelligence_candidates",
            side_effect=switch_save_during_probe,
        ),
    ):
        with pytest.raises(ConflictError, match="存档"):
            state.refresh_match_intelligence({})

    assert state.match_intelligence_results == []


def test_match_intelligence_refresh_post_route_is_registered():
    route = fm_odds_web.build_api_routes().resolve(
        "POST", "/api/activity/intelligence/refresh",
    )

    assert route is not None
    assert route.name == "refresh_match_intelligence"


def test_match_intelligence_refresh_route_forwards_request_body_scope():
    projection = {"unlocked": True, "candidates": [{"fixture_id": "fresh"}]}
    refresh = Mock(return_value={
        "intelligence": projection,
        "data_scope_id": "scope-save-1",
    })
    handler = SimpleNamespace(state=SimpleNamespace(refresh_match_intelligence=refresh))

    result = fm_odds_web.build_api_routes().dispatch(
        "POST", "/api/activity/intelligence/refresh", handler,
        {"data_scope_id": "scope-save-1"}, {},
    )

    assert result is not None
    assert result.status == HTTPStatus.OK
    assert result.payload == {
        "intelligence": projection,
        "data_scope_id": "scope-save-1",
    }
    refresh.assert_called_once_with({"data_scope_id": "scope-save-1"})


def test_refresh_match_intelligence_rejects_locked_centre_before_scanning():
    state = _refreshable_intelligence_state()
    state.match_intelligence_public_cache["unlocked"] = False
    with patch.object(fm_odds_web, "probe_match_intelligence_candidates") as probe:
        with pytest.raises(ValidationError, match="尚未解锁") as error:
            state.refresh_match_intelligence({})

    assert error.value.message_key == "error.invalid_request"
    probe.assert_not_called()


def test_refresh_match_intelligence_rejects_stale_request_scope():
    state = _refreshable_intelligence_state()
    with patch.object(fm_odds_web, "probe_match_intelligence_candidates") as probe:
        with pytest.raises(ConflictError, match="存档已变化"):
            state.refresh_match_intelligence({"data_scope_id": "old-scope"})

    probe.assert_not_called()


def test_background_intelligence_probe_keeps_bounded_rescan_off():
    state = _refreshable_intelligence_state()
    state.match_intelligence_last_probe_at = 0.0
    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "probe_match_intelligence_candidates",
            return_value={"candidates": [candidate()]},
        ) as probe,
    ):
        assert state._probe_match_intelligence_if_idle() is True

    probe.assert_called_once_with(
        [candidate()], "2028-06-10", 900, force_bounded_rescan=False,
    )


def test_successful_probe_removes_old_candidate_with_conflicting_live_scores():
    state = _refreshable_intelligence_state()
    state.match_intelligence_results = [candidate()]
    match_result = {
        "date": "2028-06-10",
        "competition": {"id": 7, "name": "测试联赛"},
        "home_team": {"id": 10, "name": "主队"},
        "away_team": {"id": 20, "name": "客队"},
        "result_source": "basic_scoreline",
    }
    conflicting_candidates = preview_cup_odds.hidden_future_result_candidates(
        object(),
        [
            {**match_result, "home_goals": 2, "away_goals": 1},
            {**match_result, "home_goals": 1, "away_goals": 0},
        ],
        [candidate()],
        "2028-06-10",
    )
    assert conflicting_candidates == []

    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "probe_match_intelligence_candidates",
            return_value={"candidates": conflicting_candidates},
        ),
    ):
        assert state._probe_match_intelligence_if_idle(force=True) is True

    assert state.match_intelligence_results == []


def test_successful_probe_keeps_other_candidate_and_purchased_history():
    state = _refreshable_intelligence_state()
    conflicted = candidate()
    retained = {
        **candidate(),
        "fixture_id": "2028-06-10|7|30|40",
        "home": {"id": 30, "name": "另一主队"},
        "away": {"id": 40, "name": "另一客队"},
    }
    state.output["matches"].append(retained)
    state.match_intelligence_results = [conflicted]
    purchased_history = {
        "fixture_id": conflicted["fixture_id"],
        "fixture_date": conflicted["fixture_date"],
        "kickoff_time": conflicted["kickoff_time"],
        "competition_id": conflicted["competition_id"],
        "competition_name": conflicted["competition_name"],
        "home": conflicted["home"],
        "away": conflicted["away"],
        "tier": "outcome",
        "reveal": {"outcome": "home", "outcome_label": "主队获胜"},
    }
    economy = economy_state()
    economy["match_intelligence_purchases"] = {
        conflicted["fixture_id"]: purchased_history,
    }

    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "probe_match_intelligence_candidates",
            return_value={"candidates": [retained]},
        ),
    ):
        assert state._probe_match_intelligence_if_idle(force=True) is True

    assert state.match_intelligence_results == [retained]
    assert economy["match_intelligence_purchases"] == {
        conflicted["fixture_id"]: purchased_history,
    }
    with (
        patch.object(club_economy, "load_economy", return_value=economy),
        patch.object(club_economy, "available_balance", return_value=0.0),
    ):
        status = club_economy.match_intelligence_status([], pricing_date="2028-06-10")
    history = next(
        row for row in status["candidates"]
        if row["fixture_id"] == conflicted["fixture_id"]
    )
    assert history["available"] is False
    assert history["purchased_tiers"] == ["outcome"]


def test_concurrent_intelligence_probes_do_not_scan_twice():
    state = _refreshable_intelligence_state()
    entered_probe = Event()
    release_probe = Event()
    results = []

    def slow_probe(*_args, **_kwargs):
        entered_probe.set()
        assert release_probe.wait(timeout=3)
        return {"candidates": [candidate()]}

    with (
        patch.object(fm_odds_web, "set_active_save_id"),
        patch.object(
            fm_odds_web, "probe_match_intelligence_candidates",
            side_effect=slow_probe,
        ) as probe,
    ):
        worker = Thread(
            target=lambda: results.append(
                state._probe_match_intelligence_if_idle(force=True)
            ),
        )
        worker.start()
        try:
            assert entered_probe.wait(timeout=3)
            assert state._probe_match_intelligence_if_idle(force=True) is False
        finally:
            release_probe.set()
            worker.join(timeout=3)

    assert not worker.is_alive()
    assert results == [True]
    probe.assert_called_once()


def test_intelligence_purchase_fails_closed_when_live_clock_is_unavailable():
    state = object.__new__(fm_odds_web.LocalOddsState)
    state.memory_lock = nullcontext()
    state.lock = nullcontext()
    state.output = {"game_date": "2028-06-10"}
    state.match_intelligence_results = [candidate()]
    state._bind_current_save = lambda: None

    with patch.object(fm_odds_web, "read_game_clock", return_value=None):
        with pytest.raises(ValueError, match="无法确认当前游戏时间"):
            state.buy_match_intelligence({
                "fixture_id": candidate()["fixture_id"],
                "tier": "outcome",
                "client_submission_id": "request-clock-missing",
            })


def test_intelligence_purchase_rejects_fixture_before_live_clock():
    state = object.__new__(fm_odds_web.LocalOddsState)
    state.memory_lock = nullcontext()
    state.lock = nullcontext()
    state.output = {"game_date": "2028-06-10", "matches": [candidate()]}
    state.match_intelligence_results = [candidate()]
    state._bind_current_save = lambda: None

    with patch.object(
        fm_odds_web, "read_game_clock",
        return_value={"date": "2028-06-10", "minutes": 901},
    ):
        with pytest.raises(ValueError, match="当前没有可获取"):
            state.buy_match_intelligence({
                "fixture_id": candidate()["fixture_id"],
                "tier": "outcome",
                "client_submission_id": "request-after-kickoff",
            })


def test_intelligence_purchase_rejects_fixture_absent_from_current_market():
    state = object.__new__(fm_odds_web.LocalOddsState)
    state.memory_lock = nullcontext()
    state.lock = nullcontext()
    other_market = {
        **candidate(),
        "fixture_id": "2028-06-10|7|30|40",
        "home": {"id": 30, "name": "其他主队"},
        "away": {"id": 40, "name": "其他客队"},
    }
    state.output = {"game_date": "2028-06-10", "matches": [other_market]}
    state.match_intelligence_results = [candidate()]
    state._bind_current_save = lambda: None

    with patch.object(
        fm_odds_web, "read_game_clock",
        return_value={"date": "2028-06-10", "minutes": 900},
    ):
        with pytest.raises(ValueError, match="当前没有可获取"):
            state.buy_match_intelligence({
                "fixture_id": candidate()["fixture_id"],
                "tier": "outcome",
                "client_submission_id": "request-market-missing",
            })


def test_live_intelligence_probe_reuses_bounded_result_pool_reader():
    matches = [{
        "fixture_date": "2028-06-10", "kickoff_minutes": 900,
        "kickoff_time": "15:00", "competition_id": 7,
        "competition_name": "Test League", "fixture_address": "0x1234",
        "home": {"id": 10, "name": "Home"},
        "away": {"id": 20, "name": "Away"},
    }]
    result = {
        "date": "2028-06-10",
        "competition": {"id": 7, "name": "Test League"},
        "home_team": {"id": 10, "name": "Home"},
        "away_team": {"id": 20, "name": "Away"},
        "home_goals": 1, "away_goals": 2,
        "result_source": "basic_scoreline",
    }
    reader = object()
    with (
        patch.object(
            preview_cup_odds, "open_supported_reader",
            return_value=nullcontext(("fm.exe", object(), object(), reader)),
        ),
        patch.object(
            preview_cup_odds, "_runtime_state",
            return_value={"result_region_spans": [(0x1000, 0x1000)]},
        ),
        patch.object(
            preview_cup_odds, "probe_live_completed_results_with_reader",
            return_value={
                "results": [result], "changed_objects": 1,
                "bytes_scanned": 128, "region_count": 1,
            },
        ) as probe,
    ):
        response = preview_cup_odds.probe_match_intelligence_candidates(
            matches, "2028-06-10", 900,
        )

    probe.assert_called_once_with(
        reader,
        {("2028-06-10", 7, 10, 20)},
        allow_expensive_rescan=True,
        force_bounded_rescan=False,
        fixture_hints={("2028-06-10", 7, 10, 20): 0x1234},
    )
    assert response["candidates"][0]["fixture_id"] == "2028-06-10|7|10|20"
    assert response["candidates"][0]["away_goals"] == 2


def test_manual_match_intelligence_probe_requests_bounded_rescan():
    matches = [{
        "fixture_date": "2028-06-10", "kickoff_minutes": 900,
        "kickoff_time": "15:00", "competition_id": 7,
        "competition_name": "Test League", "fixture_address": "0x1234",
        "home": {"id": 10, "name": "Home"},
        "away": {"id": 20, "name": "Away"},
    }]
    result = {
        "date": "2028-06-10",
        "competition": {"id": 7, "name": "Test League"},
        "home_team": {"id": 10, "name": "Home"},
        "away_team": {"id": 20, "name": "Away"},
        "home_goals": 1, "away_goals": 2,
        "result_source": "basic_scoreline",
    }
    reader = object()
    with (
        patch.object(
            preview_cup_odds, "open_supported_reader",
            return_value=nullcontext(("fm.exe", object(), object(), reader)),
        ),
        patch.object(
            preview_cup_odds, "_runtime_state",
            return_value={"result_region_spans": [(0x1000, 0x1000)]},
        ),
        patch.object(
            preview_cup_odds, "probe_live_completed_results_with_reader",
            return_value={"results": [result]},
        ) as probe,
    ):
        response = preview_cup_odds.probe_match_intelligence_candidates(
            matches, "2028-06-10", 900, force_bounded_rescan=True,
        )

    probe.assert_called_once_with(
        reader,
        {("2028-06-10", 7, 10, 20)},
        allow_expensive_rescan=True,
        force_bounded_rescan=True,
        fixture_hints={("2028-06-10", 7, 10, 20): 0x1234},
    )
    assert response["candidates"][0]["fixture_id"] == "2028-06-10|7|10|20"


def test_manual_match_intelligence_probe_scans_known_slots_before_rescan_interval():
    fixture_key = ("2028-06-10", 7, 10, 20)
    known_address = 0x1100
    discovered_address = 0x1120
    spans = [(0x1000, 0x1000)]
    new_result = {"fixture_id": "2028-06-10|7|10|20"}
    state = {
        "result_region_spans": spans,
        "result_addresses": [known_address],
        "result_fingerprints": {known_address: b"unchanged"},
        "generic_results": [],
        "result_pool_rescanned_at": 95.0,
    }
    reader = object()
    with (
        patch.object(preview_cup_odds, "_runtime_state", return_value=state),
        patch.object(
            preview_cup_odds, "normalize_two_legged_results_from_fixture_hints",
            side_effect=lambda _reader, rows, _hints: list(rows),
        ),
        patch.object(
            preview_cup_odds, "enrich_halftime_results",
            side_effect=lambda _reader, rows, _keys: list(rows),
        ),
        patch.object(
            preview_cup_odds, "scan_result_fingerprints_in_spans",
            return_value=(
                {known_address: b"unchanged", discovered_address: b"new"}, 128,
            ),
        ) as scan,
        patch.object(
            preview_cup_odds, "parse_completed_result_from_raw",
            return_value=new_result,
        ),
        patch.object(preview_cup_odds, "deduplicate_results", side_effect=list),
        patch.object(
            preview_cup_odds, "result_region_spans", return_value=spans,
        ),
        patch.object(preview_cup_odds, "_result_identity", return_value=fixture_key),
        patch.object(preview_cup_odds, "monotonic", return_value=100.0),
    ):
        response = preview_cup_odds.probe_live_completed_results_with_reader(
            reader, {fixture_key}, allow_expensive_rescan=True,
            force_bounded_rescan=True,
        )

    scan.assert_called_once_with(reader, spans)
    assert response["results"] == [new_result]
    assert response["changed_objects"] == 1
    assert discovered_address in state["result_addresses"]


def test_manual_match_intelligence_probe_with_empty_spans_avoids_heap_scan():
    state = {
        "result_region_spans": [],
        "result_addresses": [],
        "result_fingerprints": {},
        "generic_results": [],
        "result_pool_rescanned_at": 95.0,
    }
    reader = object()
    with (
        patch.object(preview_cup_odds, "_runtime_state", return_value=state),
        patch.object(
            preview_cup_odds, "normalize_two_legged_results_from_fixture_hints",
            side_effect=lambda _reader, rows, _hints: list(rows),
        ),
        patch.object(
            preview_cup_odds, "enrich_halftime_results",
            side_effect=lambda _reader, rows, _keys: list(rows),
        ),
        patch.object(
            preview_cup_odds, "read_fixture_pool_addresses",
            return_value=(None, [], 64),
        ) as read_pool,
        patch.object(preview_cup_odds, "scan_result_addresses") as heap_scan,
        patch.object(preview_cup_odds, "monotonic", return_value=100.0),
    ):
        response = preview_cup_odds.probe_live_completed_results_with_reader(
            reader, {("2028-06-10", 7, 10, 20)},
            allow_expensive_rescan=True, force_bounded_rescan=True,
        )

    read_pool.assert_called_once_with(reader)
    heap_scan.assert_not_called()
    assert response["results"] == []
    assert response["region_count"] == 0


def test_public_status_withholds_every_unpaid_result_field():
    state = economy_state()
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
    ):
        result = club_economy.match_intelligence_status([candidate()])

    row = result["candidates"][0]
    assert row["reveal"] == {}
    assert "home_goals" not in row
    assert "away_goals" not in row
    assert [tier["key"] for tier in row["tiers"]] == [
        "outcome", "total_goals", "score",
    ]
    assert [tier["price"] for tier in row["tiers"]] == [
        40_000_000, 60_000_000, 80_000_000,
    ]
    assert [tier["random_price"] for tier in row["tiers"]] == [
        20_000_000, 30_000_000, 60_000_000,
    ]
    assert all("percentage" not in key for tier in row["tiers"] for key in tier)


def test_random_intelligence_excludes_fixtures_with_that_tier_purchased():
    first = candidate()
    second = {**candidate(), "fixture_id": "2028-06-10|7|30|40"}
    status = {
        "candidates": [
            {"fixture_id": first["fixture_id"], "tiers": [
                {"key": "outcome", "purchased": True},
            ]},
            {"fixture_id": second["fixture_id"], "tiers": [
                {"key": "outcome", "purchased": False},
            ]},
        ],
    }

    selected = fm_odds_web.random_match_intelligence_candidate(
        [first, second], status, "outcome",
    )

    assert selected["fixture_id"] == second["fixture_id"]


def test_purchased_intelligence_unlocks_fixture_for_betting_engine_guards():
    state = economy_state()
    fixture = candidate()
    state["match_intelligence_purchases"] = {
        fixture["fixture_id"]: {
            **fixture,
            "predictions": {
                "outcome": {
                    "reveal": {"outcome": "home", "outcome_label": "主队获胜"},
                },
            },
        },
        "malformed": {"predictions": {"outcome": {"reveal": {}}}},
        "2028-06-11|7|30|40": {},
    }

    assert club_economy.match_intelligence_betting_unlocked_fixture_keys(
        payload=state,
    ) == {("2028-06-10", 7, 10, 20)}


def test_welfare_status_reuses_loaded_economy_for_intelligence_snapshot():
    state = economy_state()
    with (
        patch.object(club_economy, "load_economy", return_value=state) as load,
        patch.object(club_economy, "load_settings", return_value={}),
        patch.object(club_economy, "available_balance", return_value=0.0),
    ):
        result = club_economy.welfare_status([candidate()])

    load.assert_called_once()
    assert len(result["_match_intelligence"]["candidates"]) == 1


def test_welfare_pricing_cache_is_bounded_keyed_and_returns_isolated_maps():
    club_economy._welfare_pricing_cached.cache_clear()
    state = economy_state()
    settings = {
        "money_currency": "GBP", "money_rate": 1.0,
        "purchase_money_scale": 1.0,
    }
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "load_settings", return_value=settings),
        patch.object(
            club_economy, "local_purchase_price",
            wraps=club_economy.local_purchase_price,
        ) as convert,
    ):
        first = club_economy.welfare_status()
        first_conversion_count = convert.call_count
        second = club_economy.welfare_status()

        assert first_conversion_count > 0
        assert convert.call_count == first_conversion_count
        first["language_learning"]["instant_prices"]["0"] = -1
        assert second["language_learning"]["instant_prices"]["0"] >= 0

        settings["money_rate"] = 2.0
        club_economy.welfare_status()
        assert convert.call_count > first_conversion_count

    assert club_economy._welfare_pricing_cached.cache_info().maxsize == 16


def test_match_intelligence_prices_each_tier_once_per_status_projection():
    state = economy_state()
    candidates = []
    for index in range(50):
        row = candidate()
        row.update({
            "fixture_id": f"2028-06-10|7|{100 + index}|{200 + index}",
            "home": {"id": 100 + index, "name": f"主队{index}"},
            "away": {"id": 200 + index, "name": f"客队{index}"},
        })
        candidates.append(row)
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
        patch.object(
            club_economy, "_match_intelligence_quote_minor",
            wraps=club_economy._match_intelligence_quote_minor,
        ) as quote,
    ):
        result = club_economy.match_intelligence_status(candidates)

    assert len(result["candidates"]) == 50
    assert quote.call_count == len(club_economy.MATCH_INTELLIGENCE_TIER_ORDER) * 2
    assert result["candidates"][0]["tiers"] is not result["candidates"][1]["tiers"]
    assert result["candidates"][0]["tiers"][0] is not result["candidates"][1]["tiers"][0]


def test_purchased_intelligence_remains_as_previous_history_after_window_closes():
    state = economy_state()
    state["match_intelligence_purchases"] = {
        "2028-06-10|7|10|20": {
            "fixture_id": "2028-06-10|7|10|20",
            "fixture_date": "2028-06-10",
            "kickoff_time": "15:00",
            "competition_id": 7,
            "competition_name": "测试联赛",
            "home": {"id": 10, "name": "主队"},
            "away": {"id": 20, "name": "客队"},
            "tier": "score",
            "reveal": {
                "outcome_label": "主队获胜",
                "home_goals": 2,
                "away_goals": 1,
            },
        },
    }
    with patch.object(club_economy, "load_economy", return_value=state):
        result = club_economy.match_intelligence_status([])

    assert len(result["candidates"]) == 1
    row = result["candidates"][0]
    assert row["available"] is False
    assert row["purchased_today"] is False
    assert row["purchased_tiers"] == ["outcome", "total_goals", "score"]


def test_legacy_score_purchase_maps_to_three_result_columns_without_events():
    state = economy_state()
    state["match_intelligence_purchases"] = {
        "2028-06-10|7|10|20": {
            "tier": "full_report",
            "reveal": {
                "outcome": "home", "outcome_label": "主队获胜",
                "home_goals": 2, "away_goals": 1,
                "goal_events": [{"scorer": {"name": "不应公开"}}],
            },
        },
    }
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
    ):
        row = club_economy.match_intelligence_status([candidate()])["candidates"][0]

    assert row["purchased_tiers"] == ["outcome", "total_goals", "score"]
    assert row["reveal"] == {
        "outcome": "home", "outcome_label": "主队获胜",
        "total_goals": 3, "home_goals": 2, "away_goals": 1,
    }


def test_purchasing_one_candidate_keeps_other_candidates_available():
    state = economy_state()
    state["match_intelligence_purchases"] = {
        "2028-06-10|7|10|20": {
            "tier": "outcome",
            "reveal": {"outcome": "home", "outcome_label": "主队获胜"},
        },
    }
    other = {
        **candidate(),
        "fixture_id": "2028-06-10|7|30|40",
        "home": {"id": 30, "name": "另一主队"},
        "away": {"id": 40, "name": "另一客队"},
    }
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
    ):
        result = club_economy.match_intelligence_status([candidate(), other])

    rows = {row["fixture_id"]: row for row in result["candidates"]}
    assert len(rows) == 2
    assert rows["2028-06-10|7|10|20"]["purchased_tiers"] == ["outcome"]
    assert rows["2028-06-10|7|30|40"]["purchased_tiers"] == []
    assert any(not tier["purchased"] for tier in rows["2028-06-10|7|30|40"]["tiers"])


def test_specific_score_prediction_charges_fixed_price_and_unlocks_all_columns():
    state = economy_state(1_000_000_000.0)
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
        patch.object(club_economy, "load_wallet", return_value={}),
        patch.object(club_economy, "save_economy") as save,
    ):
        result = club_economy.purchase_match_intelligence(
            candidate(), "score", "request-1",
        )
        included = club_economy.purchase_match_intelligence(
            candidate(), "outcome", "request-2",
        )

    assert result["payment"]["total"] == 80_000_000
    assert state["general_balance"] == 920_000_000
    assert list(result["purchase"]["predictions"]) == [
        "outcome", "total_goals", "score",
    ]
    assert result["purchase"]["predictions"]["outcome"]["reveal"] == {
        "outcome": "home", "outcome_label": "主队获胜",
    }
    assert result["purchase"]["predictions"]["total_goals"]["reveal"] == {
        "total_goals": 3,
    }
    assert result["purchase"]["predictions"]["score"]["reveal"] == {
        "home_goals": 2, "away_goals": 1,
    }
    assert result["purchase"]["purchased_game_date"] == "2028-06-10"
    assert {
        record["purchased_game_date"]
        for record in result["purchase"]["predictions"].values()
    } == {"2028-06-10"}
    assert included["already_purchased"] is True
    assert included["payment"]["total"] == 0.0
    save.assert_called_once_with(state)


def test_random_prediction_charges_random_mode_fixed_price():
    state = economy_state(1_000_000_000.0)
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
        patch.object(club_economy, "load_wallet", return_value={}),
        patch.object(club_economy, "save_economy"),
    ):
        result = club_economy.purchase_match_intelligence(
            candidate(), "outcome", "random-request-1",
            purchase_mode="random",
        )

    assert result["payment"]["total"] == 20_000_000
    assert state["general_balance"] == 980_000_000


def test_prediction_tier_descriptions_use_fixed_price_wording():
    tiers = club_economy.MATCH_INTELLIGENCE_TIERS
    for tier in ("outcome", "total_goals"):
        assert tiers[tier]["description"] == "固定价格"
        assert tiers[tier]["random_description"] == "固定价格"
    assert tiers["score"]["description"] == "固定价格 · 并包含前两项"
    assert tiers["score"]["random_description"] == "固定价格 · 并包含前两项"
    assert {
        tier: (row["price"], row["random_price"]) for tier, row in tiers.items()
    } == {
        "outcome": (40_000_000.0, 20_000_000.0),
        "total_goals": (60_000_000.0, 30_000_000.0),
        "score": (80_000_000.0, 60_000_000.0),
    }


def test_existing_score_only_purchase_is_read_as_all_columns_unlocked():
    state = economy_state()
    state["match_intelligence_purchases"] = {
        "2028-06-10|7|10|20": {
            "fixture_id": "2028-06-10|7|10|20",
            "home": {"id": 10, "name": "主队"},
            "away": {"id": 20, "name": "客队"},
            "predictions": {
                "score": {
                    "tier": "score",
                    "reveal": {"home_goals": 2, "away_goals": 1},
                    "purchased_at": "2028-06-10T15:00:00",
                    "purchased_game_date": "2028-06-10",
                },
            },
        },
    }
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
    ):
        row = club_economy.match_intelligence_status([candidate()])["candidates"][0]

    assert row["purchased_tiers"] == ["outcome", "total_goals", "score"]
    assert row["purchased_today"] is True
    assert row["reveal"] == {
        "outcome": "home", "outcome_label": "主队获胜",
        "total_goals": 3, "home_goals": 2, "away_goals": 1,
    }


def test_prediction_columns_are_independent_and_submission_is_idempotent():
    state = economy_state(1_000_000_000.0)
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
        patch.object(club_economy, "load_wallet", return_value={}),
        patch.object(club_economy, "save_economy") as save,
    ):
        first = club_economy.purchase_match_intelligence(
            candidate(), "outcome", "request-1",
        )
        repeated = club_economy.purchase_match_intelligence(
            candidate(), "outcome", "request-1",
        )
        total_goals = club_economy.purchase_match_intelligence(
            candidate(), "total_goals", "request-2",
        )

    assert first["payment"]["total"] == 40_000_000
    assert repeated["already_purchased"] is True
    assert repeated["payment"]["total"] == 40_000_000
    assert total_goals["payment"]["total"] == 60_000_000
    assert total_goals["purchase"]["predictions"]["outcome"]["reveal"] == {
        "outcome": "home", "outcome_label": "主队获胜",
    }
    assert total_goals["purchase"]["predictions"]["total_goals"]["reveal"] == {
        "total_goals": 3,
    }
    assert state["general_balance"] == 900_000_000
    assert save.call_count == 2


def test_unavailable_detail_tier_never_charges():
    state = economy_state()
    with (
        patch.object(club_economy, "load_economy", return_value=state),
        patch.object(club_economy, "available_balance", return_value=0.0),
        patch.object(club_economy, "save_economy") as save,
    ):
        with pytest.raises(ValueError, match="情报项目无效"):
            club_economy.purchase_match_intelligence(
                candidate(), "full_report", "request-1",
            )

    assert state["general_balance"] == 1_000_000
    save.assert_not_called()
