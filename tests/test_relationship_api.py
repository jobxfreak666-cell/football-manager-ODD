import threading
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import fm_odds_web
import pytest


def state():
    value = fm_odds_web.LocalOddsState.__new__(fm_odds_web.LocalOddsState)
    value.lock = threading.RLock()
    value.memory_lock = threading.RLock()
    value.data_version = 4
    value.output = {
        "account_scope_id": "account-1", "save_instance_id": "career-1",
    }
    value.club_profiles = {10: {
        "team": {"id": 10, "name": "主队", "team_type": "club"},
        "players": [{"id": 1, "name": "A", "address": "0x1000"}],
        "staff": [], "squads": [],
    }}
    return value


def relationship_training_state():
    value = state()
    value.output["game_date"] = "2026-08-20"
    value.club_profiles[10]["players"][0].update({
        "ca": 120, "pa": 160, "age": 21, "attributes": {},
    })
    return value


def relationship_room_catalog(room_id, room_sku):
    return {
        "rooms": [{"sku": room_sku, "instances": [{"id": room_id}]}],
    }


def test_relationship_room_catalog_uses_ready_connection_scope_while_identity_is_deferred():
    value = relationship_training_state()
    value.cache_verified = False
    value.output["save_identity_discovery_deferred"] = True
    value.connection_scope_id = "connection-account"
    value.wallet_ready = True
    with (
        patch("fm_odds_web.set_active_save_id") as activate,
        patch.object(value, "_ensure_training_task_migration", return_value=False) as migrate,
        patch("fm_odds_web.relationship_training_catalog", return_value={"rooms": []}),
    ):
        result = value.relationship_training_rooms_state()
    activate.assert_called_once_with("connection-account")
    migrate.assert_called_once_with("2026-08-20")
    assert result == {"rooms": []}


def test_relationship_room_unlock_endpoint_is_retired_and_charges_nothing():
    value = relationship_training_state()
    with patch("fm_odds_web.charge_combined_funds") as charge:
        with pytest.raises(ValueError, match="无需解锁") as caught:
            value.relationship_training_room_unlock({"room_sku": "mind_room"})
    assert caught.value.message_key == "training.error.room_unlock_retired"
    charge.assert_not_called()


def operation_context(*, writable=False):
    operation = SimpleNamespace(
        reader=object(), process=object(), writable=writable,
    )
    context = Mock()
    context.__enter__ = Mock(return_value=operation)
    context.__exit__ = Mock(return_value=False)
    return context


def test_relationship_routes_are_registered():
    registered = {(method, path) for method, path, _ in fm_odds_web.API_ROUTES.describe()}
    assert ("GET", "/api/relations/scopes") in registered
    for path in ("people", "network", "pair", "timeline", "entities"):
        assert ("POST", f"/api/relations/{path}") in registered
    assert ("POST", "/api/rel3d/screenshot") in registered
    # Manual team-training settle is registered in release builds too.
    assert ("POST", "/api/training/relationship-rooms/settle") in registered
    if not fm_odds_web.FROZEN:
        assert ("POST", "/api/relations/adjust-bidirectional") not in registered


def test_relationship_timeline_uses_current_account_scope():
    value = state()
    with patch("fm_odds_web.relationship_timeline", return_value={"events": []}) as timeline:
        assert value.relations_timeline({"page": 2}) == {"events": []}
    timeline.assert_called_once_with({"page": 2}, "account-1")


def test_relationship_timeline_enriches_current_ca_pa_and_player_manager_role():
    value = state()
    value.club_profiles[10]["players"][0].update({"ca": 123, "pa": 167})
    value.output.update({
        "selected_manager_id": 99,
        "manager": {"id": 99, "name": "玩家", "ca": 144, "pa": 171},
    })
    archived = {"events": [{
        "person_a": {
            "id": 1, "name": "旧球员名", "kind": "player", "ca": 0, "pa": 0,
            "event_role": "activity_target", "event_role_label": "活动对象",
        },
        "person_b": {
            "id": 99, "name": "玩家", "kind": "staff",
            "event_role": "manager", "event_role_label": "玩家经理",
        },
    }]}
    with patch("fm_odds_web.relationship_timeline", return_value=archived):
        result = value.relations_timeline({})

    player = result["events"][0]["person_a"]
    manager = result["events"][0]["person_b"]
    assert (player["name"], player["ca"], player["pa"]) == ("A", 123, 167)
    assert player["event_role_label"] == "活动对象"
    assert manager["kind"] == "staff"
    assert manager["role"] == "玩家经理"
    assert manager["is_player_manager"] is True


def test_relationship_timeline_uses_real_player_and_staff_categories():
    value = state()
    value.club_profiles[10]["players"][0].update({
        "primary_positions": ["AML"], "ca": 123, "pa": 167,
    })
    value.club_profiles[10]["staff"] = [{
        "id": 3, "name": "队医", "job_type": 38, "role": "队医",
        "ca": 142, "pa": 155,
    }]
    archived = {"events": [{
        "person_a": {"id": 1, "name": "旧球员", "kind": "player"},
        "person_b": {"id": 3, "name": "旧职员", "kind": "staff"},
    }]}
    with patch("fm_odds_web.relationship_timeline", return_value=archived):
        result = value.relations_timeline({})

    player = result["events"][0]["person_a"]
    staff = result["events"][0]["person_b"]
    assert (player["timeline_category_key"], player["timeline_category_label"]) == ("forwards", "前场")
    assert (staff["timeline_category_key"], staff["timeline_category_label"]) == ("医疗团队", "医疗团队")
    assert player["team_name"] == staff["team_name"] == "主队"
    assert player["team_type"] == staff["team_type"] == "club"


def test_rel3d_screenshot_validates_png_and_returns_real_path(tmp_path):
    raw = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (b"\x00" * 12)
    result = fm_odds_web.save_rel3d_screenshot({
        "dir": str(tmp_path),
        "data": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
    })
    assert result["ok"] is True
    assert result["size"] == len(raw)
    assert Path(result["path"]).read_bytes() == raw


def test_rel3d_screenshot_rejects_non_png_payload():
    encoded = base64.b64encode(b"not a png payload long enough").decode("ascii")
    with pytest.raises(ValueError, match="PNG"):
        fm_odds_web.save_rel3d_screenshot({
            "data": "data:image/png;base64," + encoded,
        })


def test_scopes_do_not_load_acquired_club_detail():
    value = state()
    value.world_club_detail = Mock(side_effect=AssertionError("must stay lazy"))
    with patch("fm_odds_web.account_acquired_clubs", return_value=[{
        "team_id": 20, "team_name": "集团队", "available": True,
    }]):
        result = value.relations_scopes()
    assert result["managed"][0]["team_id"] == 10
    assert result["acquired"][0]["team_id"] == 20
    value.world_club_detail.assert_not_called()


def test_scopes_include_profiles_published_during_club_refresh():
    value = state()
    value.club_refreshing = True
    value.club_loading_profiles = {11: {
        "team": {"id": 11, "name": "分批发布队伍", "team_type": "club"},
        "players": [], "staff": [], "squads": [],
    }}
    with patch("fm_odds_web.account_acquired_clubs", return_value=[]):
        result = value.relations_scopes()

    assert [row["team_id"] for row in result["managed"]] == [10, 11]


def test_people_reject_stale_data_version():
    value = state()
    try:
        value.relations_people({"team_id": 10, "data_version": 3})
    except ValueError as error:
        assert "已刷新" in str(error)
    else:
        raise AssertionError("stale request was accepted")


def test_network_borrows_resident_reader_for_selected_page_only():
    value = state()
    operation = SimpleNamespace(reader=object())
    context = Mock()
    context.__enter__ = Mock(return_value=operation)
    context.__exit__ = Mock(return_value=False)
    enriched = {"people": [{"id": 1}]}
    with (
        patch("fm_odds_web.borrow_game_operation", return_value=context),
        patch("fm_odds_web.enrich_relationship_page", return_value=enriched) as enrich,
    ):
        result = value.relations_network({
            "team_id": 10, "data_version": 4, "page": 1, "page_size": 24,
        })
    assert result["data_version"] == 4
    enrich.assert_called_once()
    assert enrich.call_args.args[1]["total"] == 1


def test_relationship_room_preview_checks_all_pairs_but_marks_only_effect_pairs():
    value = relationship_training_state()
    value.club_profiles[10]["players"].append({
        "id": 2, "name": "B", "address": "0x2000",
    })
    value.club_profiles[10]["staff"].append({
        "id": 7, "name": "分析员", "address": "0x7000",
        "job_type": 60, "abilities": {"数据分析": 14},
    })
    positive = {
        "a_to_b": {"relation_type": 1, "level": 30, "reason": 6},
        "b_to_a": {"relation_type": 1, "level": 20, "reason": 6},
    }
    negative = {
        "a_to_b": {"relation_type": 0, "signed_score": -10, "reason": 12},
        "b_to_a": {"relation_type": 1, "level": 0, "reason": 0},
    }
    with (
        patch.object(value, "_bind_current_save"),
        patch("fm_odds_web.relationship_training_catalog", return_value=
              relationship_room_catalog("video-1", "video_analysis_room")),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=[
            0x7000, 0x1000, 0x2000,
        ]),
        patch("fm_odds_web.read_relationship_pair", side_effect=[
            positive, positive, negative,
        ]),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {},
        }),
    ):
        result = value.relationship_training_room_preview({
            "room_sku": "video_analysis_room",
            "participants": [
                {"role": "analyst", "kind": "staff", "id": 7, "team_id": 10},
                {"role": "player", "kind": "player", "id": 1, "team_id": 10},
                {"role": "player", "kind": "player", "id": 2, "team_id": 10},
            ],
        })
    assert len(result["pairs"]) == 3
    assert [pair["effect_pair"] for pair in result["pairs"]] == [True, True, False]
    assert result["pairs"][2]["negative"] is True
    assert result["negative"] is True


def test_relationship_room_preview_returns_actual_attribute_growth_and_eta():
    value = relationship_training_state()
    value.club_profiles[10]["staff"].append({
        "id": 7, "name": "教练", "address": "0x7000", "job_type": 2,
        "abilities": {"人员管理": 18, "激励": 16},
        "coaching_license": {"code": 7}, "current_reputation": 5000,
    })
    room = {
        **fm_odds_web.RELATIONSHIP_TRAINING_ROOMS["tactical_room"],
        "sku": "tactical_room", "instances": [{"id": "tactical-1"}],
    }
    relation = {
        "a_to_b": {"relation_type": 1, "level": 40, "signed_score": 40},
        "b_to_a": {"relation_type": 1, "level": 60, "signed_score": 60},
    }
    with (
        patch.object(value, "_bind_current_save"),
        patch("fm_odds_web.relationship_training_catalog", return_value={"rooms": [room]}),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=[0x7000, 0x1000]),
        patch("fm_odds_web.read_relationship_pair", return_value=relation),
        patch("fm_odds_web.read_player_training_attributes", return_value={
            "1:hidden:职业素养": 10,
        }),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {"tactical_room:player:1:hidden:职业素养": 5.0},
            "intimacy_progress": {},
        }),
    ):
        result = value.relationship_training_room_preview({
            "room_sku": "tactical_room", "attributes": ["hidden:职业素养"],
            "participants": [
                {"role": "coach", "kind": "staff", "id": 7, "team_id": 10},
                {"role": "player", "kind": "player", "id": 1, "team_id": 10},
            ],
        })
    effect = result["effects"][0]
    assert effect["current"] == 10
    assert effect["target"] == 11
    assert effect["stored_points"] == 5.0
    assert effect["daily_points"] > effect["base_daily_points"]
    assert effect["required_points"] > effect["stored_points"]
    assert effect["estimated_days"] >= 1
    assert result["pairs"][0]["a_to_b_effect"]["daily"] > 0
    assert result["pairs"][0]["b_to_a_effect"]["daily"] > 0
    options = result["target_options"]
    assert list(options) == ["until_increase", "14", "16", "18", "20"]
    assert options["until_increase"]["days"] == effect["estimated_days"]
    assert options["until_increase"]["settle_on"] == fm_odds_web._game_date_plus(
        "2026-08-20", effect["estimated_days"],
    )
    assert options["14"]["days"] > options["until_increase"]["days"]
    assert options["20"]["days"] > options["14"]["days"]
    assert result["target"] == "until_increase"


def _tactical_preview(current, target):
    value = relationship_training_state()
    value.club_profiles[10]["staff"].append({
        "id": 7, "name": "教练", "address": "0x7000", "job_type": 2,
        "abilities": {"人员管理": 18, "激励": 16},
        "coaching_license": {"code": 7}, "current_reputation": 5000,
    })
    relation = {"a_to_b": None, "b_to_a": None}
    with (
        patch.object(value, "_bind_current_save"),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=[0x7000, 0x1000]),
        patch("fm_odds_web.read_relationship_pair", return_value=relation),
        patch("fm_odds_web.read_player_training_attributes", return_value={
            "1:hidden:职业素养": current,
        }),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {},
        }),
    ):
        return value.relationship_training_room_preview({
            "room_sku": "tactical_room", "attributes": ["hidden:职业素养"],
            "target": target,
            "participants": [
                {"role": "coach", "kind": "staff", "id": 7, "team_id": 10},
                {"role": "player", "kind": "player", "id": 1, "team_id": 10},
            ],
        })


def test_preview_excludes_effects_already_at_or_above_the_target():
    result = _tactical_preview(15, "14")
    effect = result["effects"][0]
    assert effect["goal"] is None
    assert effect["excluded_reason"] == "已达到或超过训练目标"
    assert result["target_options"]["14"] is None
    assert result["target_options"]["16"]["days"] >= 1
    assert _tactical_preview(12, "16")["effects"][0]["goal"] == 16


def test_relationship_training_settlement_commits_hidden_progress_atomically():
    value = relationship_training_state()
    participant = {
        "kind": "player", "id": 1, "name": "A", "role": "player_a",
        "team_id": 10,
    }
    session = {
        "id": "focus-1", "room_sku": "mind_room",
        "participants": [participant], "attributes": ["hidden:适应性"],
    }
    plan = {
        "elapsed_days": 1, "focus_coefficient": 1.0,
        "attribute_points": 3.0, "beneficiaries": [participant],
        "attributes": [{"key": "hidden:适应性", "kind": "hidden"}],
        "pairs": [],
    }
    committed = {
        "completed": {"attribute_changes": [{"change": 3}]},
        "archive": {"created": True},
    }
    with (
        patch("fm_odds_web.FROZEN", False),
        patch.object(value, "_bind_current_save"),
        patch.object(value, "relationship_training_rooms_state", return_value={"rooms": []}),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {},
        }),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", return_value=0x1000),
        patch("fm_odds_web.read_person_public_profile", return_value={"uid": 1}),
        patch("fm_odds_web.read_player_training_attributes", return_value={
            "1:hidden:适应性": 10,
        }),
        patch("fm_odds_web.training_points_required_for_direction", return_value=1),
        patch("fm_odds_web.develop_player_hidden_attribute", side_effect=[
            {"_original_raw": index, "_updated_raw": index + 1}
            for index in range(3)
        ]) as develop,
        patch("fm_odds_web.commit_relationship_training_settlement", return_value=committed) as commit,
        patch("fm_odds_web.invalidate_club_profile_cache"),
    ):
        result = value.relationship_training_room_settle({"room_id": "room-1"})
    assert develop.call_count == 3
    assert commit.call_args.kwargs["attribute_progress"]["mind_room:player:1:hidden:适应性"] == 0
    assert result["archive"] == {"created": True}


def test_video_analysis_team_capability_multiplies_attribute_progress():
    value = relationship_training_state()
    value.club_profiles[10]["staff"].append({
        "id": 7, "name": "分析师", "address": "0x7000", "job_type": 60,
        "abilities": {
            "数据分析": 20, "判断球员能力": 20,
            "判断球员潜力": 20, "战术知识": 20,
        },
    })
    player = {
        "kind": "player", "id": 1, "name": "A", "role": "player",
        "team_id": 10,
    }
    analyst = {
        "kind": "staff", "id": 7, "name": "分析师", "role": "analyst",
        "team_id": 10,
    }
    session = {
        "id": "video-focus", "room_sku": "video_analysis_room",
        "participants": [player, analyst], "attributes": ["精神:决断"],
    }
    plan = {
        "elapsed_days": 1, "focus_coefficient": 1.0,
        "attribute_points": 1.0, "beneficiaries": [player],
        "attributes": [{"key": "精神:决断", "kind": "visible"}],
        "pairs": [],
    }
    committed = {"completed": {}, "archive": {}}
    with (
        patch("fm_odds_web.FROZEN", False),
        patch.object(value, "_bind_current_save"),
        patch.object(value, "relationship_training_rooms_state", return_value={"rooms": []}),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {}, "height_baselines": {},
        }),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=[0x1000, 0x7000]),
        patch("fm_odds_web.read_person_public_profile", side_effect=[
            {"uid": 1}, {"uid": 7},
        ]),
        patch("fm_odds_web.read_player_training_attributes", return_value={
            "1:精神:决断": 10,
        }),
        patch("fm_odds_web.training_points_required_for_direction", return_value=100),
        patch("fm_odds_web.commit_relationship_training_settlement", return_value=committed) as commit,
        patch("fm_odds_web.invalidate_club_profile_cache"),
    ):
        value.relationship_training_room_settle({"room_id": "room-1"})
    assert commit.call_args.kwargs["attribute_progress"][
        "video_analysis_room:player:1:精神:决断"
    ] == pytest.approx(1.5)


def test_sports_condition_write_rolls_back_when_account_commit_fails():
    value = relationship_training_state()
    value.club_profiles[10]["players"][0].update({
        "availability": {"injury_count": 0, "injuries": []},
        "fatigue": 3000, "sharpness": 70,
    })
    value.club_profiles[10]["staff"].append({
        "id": 8, "name": "运动科学家", "address": "0x8000", "job_type": 40,
        "abilities": {"运动科学": 15},
    })
    player = {
        "kind": "player", "id": 1, "name": "A", "role": "player",
        "team_id": 10,
    }
    scientist = {
        "kind": "staff", "id": 8, "name": "运动科学家", "role": "scientist",
        "team_id": 10,
    }
    session = {
        "id": "sports-focus", "room_sku": "sports_science_room",
        "participants": [player, scientist], "attributes": ["精神:勇敢"],
    }
    plan = {
        "elapsed_days": 0, "focus_coefficient": 1.0,
        "attribute_points": 0.0, "beneficiaries": [player],
        "attributes": [{"key": "精神:勇敢", "kind": "visible"}],
        "pairs": [],
    }
    condition = {
        "before": {"fatigue": 3000, "sharpness": 7000, "fitness": 8000},
        "after": {"fatigue": 2375, "sharpness": 7625, "fitness": 8375},
        "_original": b"original", "_updated": b"updated",
    }
    with (
        patch("fm_odds_web.FROZEN", False),
        patch.object(value, "_bind_current_save"),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {}, "height_baselines": {},
        }),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=[0x1000, 0x8000]),
        patch("fm_odds_web.read_person_public_profile", side_effect=[
            {"uid": 1}, {"uid": 8},
        ]),
        patch("fm_odds_web.read_player_training_attributes", return_value={
            "1:精神:勇敢": 10,
        }),
        patch("fm_odds_web.adjust_player_training_condition", return_value=condition),
        patch("fm_odds_web.commit_relationship_training_settlement", side_effect=RuntimeError("commit failed")),
        patch("fm_odds_web.restore_player_training_condition") as restore_condition,
        patch("fm_odds_web.restore_relationship_training_room") as restore_room,
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            value.relationship_training_room_settle({"room_id": "room-1"})
    restore_condition.assert_called_once_with(1, "0x1000", b"original", b"updated")
    restore_room.assert_called_once_with("room-1")


def test_relationship_training_commit_failure_rolls_back_native_write_and_room():
    value = relationship_training_state()
    participant = {
        "kind": "player", "id": 1, "name": "A", "role": "player_a",
        "team_id": 10,
    }
    session = {
        "id": "focus-1", "room_sku": "mind_room",
        "participants": [participant], "attributes": ["hidden:适应性"],
    }
    plan = {
        "elapsed_days": 1, "focus_coefficient": 1.0,
        "attribute_points": 1.0, "beneficiaries": [participant],
        "attributes": [{"key": "hidden:适应性", "kind": "hidden"}],
        "pairs": [],
    }
    write_result = {"_original_raw": 10, "_updated_raw": 11}
    with (
        patch("fm_odds_web.FROZEN", False),
        patch.object(value, "_bind_current_save"),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {},
        }),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", return_value=0x1000),
        patch("fm_odds_web.read_person_public_profile", return_value={"uid": 1}),
        patch("fm_odds_web.read_player_training_attributes", return_value={
            "1:hidden:适应性": 10,
        }),
        patch("fm_odds_web.training_points_required_for_direction", return_value=1),
        patch("fm_odds_web.develop_player_hidden_attribute", return_value=write_result),
        patch("fm_odds_web.commit_relationship_training_settlement", side_effect=RuntimeError("commit failed")),
        patch("fm_odds_web.restore_player_hidden_attribute") as restore_attribute,
        patch("fm_odds_web.restore_relationship_training_room") as restore_room,
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            value.relationship_training_room_settle({"room_id": "room-1"})
    restore_attribute.assert_called_once_with(
        1, "0x1000", "hidden:适应性", 10, 11,
    )
    restore_room.assert_called_once_with("room-1")


def test_relationship_training_commit_failure_rolls_back_relationship_write():
    value = relationship_training_state()
    value.club_profiles[10]["players"].append({
        "id": 2, "name": "B", "address": "0x2000",
        "ca": 110, "pa": 150, "age": 20, "attributes": {},
    })
    left = {
        "kind": "player", "id": 1, "name": "A", "role": "player_a",
        "team_id": 10,
    }
    right = {
        "kind": "player", "id": 2, "name": "B", "role": "player_b",
        "team_id": 10,
    }
    session = {
        "id": "focus-relationship", "room_sku": "mind_room",
        "participants": [left, right], "attributes": [],
    }
    plan = {
        "elapsed_days": 1, "focus_coefficient": 1.0,
        "attribute_points": 0.0, "beneficiaries": [], "attributes": [],
        "pairs": [{
            "person_a": left, "person_b": right, "base_increment": 1.0,
            "reason_a2b": 5, "reason_b2a": 5,
        }],
    }
    write_result = {
        "a_to_b": {"before": 10, "after": 11, "applied": 1, "undo": {"a": 1}},
        "b_to_a": {"before": 20, "after": 21, "applied": 1, "undo": {"b": 1}},
    }
    context = operation_context(writable=True)
    with (
        patch("fm_odds_web.FROZEN", False),
        patch.object(value, "_bind_current_save"),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {},
        }),
        patch("fm_odds_web.borrow_game_operation", return_value=context),
        patch("fm_odds_web.resolve_public_person_address", side_effect=[0x1000, 0x2000]),
        patch("fm_odds_web.read_person_public_profile", side_effect=[
            {"uid": 1}, {"uid": 2},
        ]),
        patch("fm_odds_web.read_relationship_pair", return_value={
            "a_to_b": {"level": 10, "relation_type": 1},
            "b_to_a": {"level": 20, "relation_type": 1},
        }),
        patch("fm_odds_web.read_player_training_attributes", return_value={}),
        patch("fm_odds_web.write_bidirectional_intimacy", return_value=write_result) as write,
        patch("fm_odds_web.commit_relationship_training_settlement", side_effect=RuntimeError("commit failed")),
        patch("fm_odds_web.rollback_bidirectional_intimacy") as rollback,
        patch("fm_odds_web.restore_relationship_training_room") as restore_room,
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            value.relationship_training_room_settle({"room_id": "room-1"})

    write.assert_called_once()
    rollback.assert_called_once_with(write_result)
    restore_room.assert_called_once_with("room-1")


# ---- 团队训练：不用解锁、每次训练收一次费 ----

@pytest.fixture()
def team_room_store(monkeypatch):
    from copy import deepcopy
    from tools import relationship_training as rooms

    documents = {"relationship_training_rooms": rooms._new_state()}

    def load_document(key, default):
        return deepcopy(documents.get(key, default))

    def update_document(key, default, mutator):
        document = deepcopy(documents.get(key, default))
        result = mutator(document)
        documents[key] = document
        return deepcopy(result)

    monkeypatch.setattr(rooms, "load_document", load_document)
    monkeypatch.setattr(rooms, "update_document", update_document)
    monkeypatch.setattr(rooms, "load_settings", lambda: {})
    monkeypatch.setattr(
        rooms, "local_purchase_price", lambda value, _settings=None: float(value),
    )
    return documents


def team_training_state():
    value = relationship_training_state()
    value.club_profiles[10]["players"].append({
        "id": 2, "name": "B", "address": "0x2000", "ca": 110, "pa": 150,
        "age": 20, "attributes": {},
    })
    value.club_profiles[10]["staff"].extend([
        {"id": 20, "name": "助教", "address": "0x2020", "job_type": 20,
         "coaching_license": {"code": 5}, "current_reputation": 3000},
        {"id": 21, "name": "无证教练", "address": "0x2021", "job_type": 2,
         "coaching_license": {"code": 0}},
        {"id": 60, "name": "分析师", "address": "0x6000", "job_type": 60},
        {"id": 40, "name": "运动科学", "address": "0x4000", "job_type": 40},
    ])
    return value


def _option(days, participants=()):
    return {"days": days, "settle_on": None, "participants": list(participants)}


def _fake_charge_commit(payment, calls):
    """Stand-in for the atomic economy commit: same contract, in-memory store."""
    from tools import relationship_training as rooms

    def commit(defaults, mutator, amount, kind, **details):
        (key, default), = defaults.items()

        def charge():
            calls.append(call(amount, kind, **details))
            return dict(payment) if payment else payment

        return rooms.update_document(key, default, lambda raw: mutator({key: raw}, charge))

    return commit


def _enter(value, payload, *, charge=None, payment=None, estimate=4):
    payment = payment or {
        "bank": 2_500_000.0, "wallet": 0.0, "total": 2_500_000.0,
        "transaction_id": "session-1",
    }
    with (
        patch.object(value, "_bind_current_save"),
        patch.object(value, "_ensure_training_task_migration", return_value=False),
        patch.object(value, "relationship_training_rooms_state", return_value={"rooms": []}),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=lambda _r, person, _k: int(str(person.get("address") or "0x1"), 0)),
        patch("fm_odds_web.persons_relation_negative", return_value=False),
        patch(
            "fm_odds_web.commit_documents_with_combined_charge",
            _fake_charge_commit(payment, charge if charge is not None else []),
        ),
        patch("fm_odds_web.public_economy", return_value={"bank_balance": 1.0}),
        patch.object(value, "_team_training_estimate", return_value=_option(estimate)),
    ):
        return value.relationship_training_room_enter(payload)


def _mind_payload(submission="req-1", player_id=1):
    return {
        "room_sku": "mind_room", "client_submission_id": submission,
        "attributes": ["精神:意志力"],
        "participants": [{"kind": "player", "id": player_id, "team_id": 10, "role": "player_a"}],
    }


def test_team_room_enter_needs_no_unlock_and_charges_half_price_once(team_room_store):
    value = team_training_state()
    charges = []
    result = _enter(value, _mind_payload(), charge=charges)
    assert result["room"]["status"] == "occupied"
    assert result["replayed"] is False
    assert result["session_fee_minor"] == 250_000_000
    assert len(charges) == 1
    assert charges[0].args == (2_500_000.0, "relationship_training_room_session")
    assert charges[0].kwargs == {"room_sku": "mind_room"}

    replay_charges = []
    again = _enter(value, _mind_payload(), charge=replay_charges)
    assert replay_charges == []
    assert again["replayed"] is True
    assert again["room"]["id"] == result["room"]["id"]
    assert again["payment"] == result["payment"]


def test_team_room_enter_returns_team_rooms_with_active_session(team_room_store):
    value = team_training_state()
    result = _enter(value, _mind_payload())
    rooms = {room["sku"]: room for room in result["team_rooms"]}
    active = rooms["mind_room"]["active"]
    assert active["room_id"] == result["room"]["id"]
    assert active["status"] == "occupied"
    assert active["participants"][0]["id"] == 1


def test_team_session_participant_remaining_days_counts_from_today():
    from tools.relationship_training import public_team_training_session
    room = {
        "id": "r1", "status": "occupied", "started_on": "2026-07-01",
        "estimated_settle_on": "2026-07-15", "estimated_total_days": 14,
        "participants": [
            {"id": 1, "kind": "player", "estimated_days": 14, "settle_on": "2026-07-15"},
            {"id": 2, "kind": "player", "estimated_days": 6, "settle_on": "2026-07-07"},
        ],
    }
    people = public_team_training_session(room, "2026-07-05")["active"]["participants"]
    assert [row["estimated_days"] for row in people] == [14, 6]
    assert [row["remaining_days"] for row in people] == [10, 2]
    late = public_team_training_session(room, "2026-07-10")["active"]["participants"]
    assert late[1]["remaining_days"] == 0


def test_team_room_enter_requires_request_id_before_charging(team_room_store):
    value = team_training_state()
    charges = []
    with pytest.raises(ValueError, match="刷新页面"):
        _enter(value, _mind_payload(submission=""), charge=charges)
    assert charges == []


def test_team_room_enter_rejected_participant_is_never_charged(team_room_store):
    value = team_training_state()
    _enter(value, _mind_payload("first"))
    charges = []
    # Same player again under a new request id: refused before any money moves.
    with pytest.raises(ValueError, match="其他团队训练房间"):
        _enter(value, _mind_payload("second"), charge=charges)
    assert charges == []


def test_team_room_concurrent_double_click_charges_once(team_room_store):
    value = team_training_state()
    calls = []
    barrier = threading.Barrier(2)
    results = []

    def submit():
        barrier.wait()
        results.append(value.relationship_training_room_enter(_mind_payload("dbl")))

    payment = {"bank": 1.0, "wallet": 0.0, "total": 1.0}
    with (
        patch.object(value, "_bind_current_save"),
        patch.object(value, "_ensure_training_task_migration", return_value=False),
        patch.object(value, "relationship_training_rooms_state", return_value={"rooms": []}),
        patch("fm_odds_web.borrow_game_operation", side_effect=lambda: operation_context()),
        patch("fm_odds_web.resolve_public_person_address", return_value=0x1000),
        patch("fm_odds_web.persons_relation_negative", return_value=False),
        patch("fm_odds_web.commit_documents_with_combined_charge", _fake_charge_commit(payment, calls)),
        patch("fm_odds_web.public_economy", return_value={}),
        patch.object(value, "_team_training_estimate", return_value=_option(4)),
    ):
        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert len(calls) == 1
    assert sorted(row["replayed"] for row in results) == [False, True]


def _tactical_payload(coach_id, submission):
    return {
        "room_sku": "tactical_room", "client_submission_id": submission,
        "attributes": ["精神:团队合作"],
        "participants": [
            {"kind": "staff", "id": coach_id, "team_id": 10, "role": "coach"},
            {"kind": "player", "id": 1, "team_id": 10, "role": "player"},
        ],
    }


def test_tactical_room_enter_accepts_licensed_assistant_and_rejects_unlicensed(team_room_store):
    value = team_training_state()
    entered = _enter(value, _tactical_payload(20, "tac-ok"))
    assert entered["room"]["sku"] == "tactical_room"
    charges = []
    other = team_training_state()
    with pytest.raises(ValueError, match="持证"):
        _enter(other, _tactical_payload(21, "tac-bad"), charge=charges)
    assert charges == []


def test_mentoring_room_rejects_unqualified_mentor_before_charging(team_room_store):
    value = team_training_state()
    charges = []
    with pytest.raises(ValueError, match="传习资格"):
        _enter(value, {
            "room_sku": "mentoring_room", "client_submission_id": "mentor-1",
            "attributes": ["精神:领导力"],
            "participants": [
                {"kind": "player", "id": 1, "team_id": 10, "role": "mentor"},
                {"kind": "player", "id": 2, "team_id": 10, "role": "student"},
            ],
        }, charge=charges)
    assert charges == []


def _settle_tactical(value, coach_id, *, frozen=False):
    coach = {"kind": "staff", "id": coach_id, "name": "C", "role": "coach", "team_id": 10}
    player = {"kind": "player", "id": 1, "name": "A", "role": "player", "team_id": 10}
    session = {
        "id": "tac-session", "room_sku": "tactical_room",
        "participants": [coach, player], "attributes": [],
    }
    plan = {
        "elapsed_days": 1, "focus_coefficient": 1.0, "attribute_points": 0.0,
        "beneficiaries": [player], "attributes": [], "pairs": [],
    }
    with (
        patch.object(value, "_team_training_rooms", return_value=[]),
        patch("fm_odds_web.FROZEN", frozen),
        patch.object(value, "_bind_current_save"),
        patch.object(value, "_data_scope_id", return_value="account-1"),
        patch.object(value, "_ensure_training_task_migration", return_value=False),
        patch.object(value, "relationship_training_rooms_state", return_value={"rooms": []}),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {}, "height_baselines": {},
        }),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=[0x2020, 0x1000]),
        patch("fm_odds_web.read_person_public_profile", side_effect=[
            {"uid": coach_id}, {"uid": 1},
        ]),
        patch("fm_odds_web.read_player_training_attributes", return_value={}),
        patch("fm_odds_web.commit_relationship_training_settlement",
              return_value={"completed": {}, "archive": {"created": True}}) as commit,
        patch("fm_odds_web.restore_relationship_training_room") as restore,
        patch("fm_odds_web.invalidate_club_profile_cache"),
    ):
        try:
            value.relationship_training_room_settle({"room_id": "room-1"})
        finally:
            settle_calls = (commit.call_count, restore.call_count, commit.call_args)
    return settle_calls


def test_tactical_room_settle_uses_the_same_coach_rule_as_enter():
    value = team_training_state()
    count, _restored, call = _settle_tactical(value, 20)
    assert count == 1 and "early_settlement" not in call.args[2]
    # An unlicensed coach no longer fails settle: it settles early instead.
    count, _restored, call = _settle_tactical(team_training_state(), 21)
    assert count == 1
    early = call.args[2]["early_settlement"]
    assert early["reason"] == "participant_no_longer_eligible"
    assert early["details"] == ["战术指导室导师只能选择教练团队的持证职员"]


def test_training_payload_exposes_team_rooms_with_fee_and_eligible_staff(team_room_store):
    value = team_training_state()
    with patch("fm_odds_web.public_training_ground", return_value={"catalog": []}):
        ground = value._public_training_ground("2026-08-20")
    rooms = {row["sku"]: row for row in ground["team_rooms"]}
    assert list(rooms) == [
        "mind_room", "mentoring_room", "tactical_room",
        "video_analysis_room", "sports_science_room",
    ]
    assert rooms["video_analysis_room"]["session_fee_minor"] == 1_250_000_000
    assert rooms["tactical_room"]["eligible_staff_ids"] == {"coach": [20]}
    assert rooms["video_analysis_room"]["eligible_staff_ids"] == {"analyst": [60]}
    assert rooms["sports_science_room"]["eligible_staff_ids"] == {"scientist": [40]}
    assert rooms["mind_room"]["eligible_staff_ids"] == {}
    assert rooms["mentoring_room"]["roles"] == [
        {"key": "mentor", "kind": "player", "min": 1, "max": 1},
        {"key": "student", "kind": "player", "min": 1, "max": 4},
    ]
    assert set(rooms["mind_room"]["scope_attributes"][0]) == {"key", "direction", "kind"}


def test_unlock_route_is_still_registered_but_retired():
    routes = {path for _method, path, _ in fm_odds_web.API_ROUTES.describe()}
    assert "/api/training/relationship-rooms/enter" in routes


def test_manual_team_settle_works_in_release_build():
    assert _settle_tactical(team_training_state(), 20, frozen=True)[0] == 1


def _settle_with_attribute(value, session, plan, values, *, relation=None, required=100):
    with (
        patch.object(value, "_team_training_rooms", return_value=[]),
        patch.object(value, "_bind_current_save"),
        patch.object(value, "_data_scope_id", return_value="account-1"),
        patch.object(value, "_ensure_training_task_migration", return_value=False),
        patch.object(value, "relationship_training_rooms_state", return_value={"rooms": []}),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {}, "height_baselines": {},
        }),
        patch("fm_odds_web.borrow_game_operation", side_effect=lambda **_k: operation_context()),
        patch("fm_odds_web.resolve_public_person_address", side_effect=lambda _r, person, _k: int(str(person.get("address") or "0x1"), 0)),
        patch("fm_odds_web.read_person_public_profile", side_effect=lambda _r, address: {
            "uid": {0x1000: 1, 0x2000: 2, 0x2021: 21}.get(int(address), 0),
        }),
        patch("fm_odds_web.read_relationship_pair", return_value=relation or {}),
        patch("fm_odds_web.read_player_training_attributes", return_value=values),
        patch("fm_odds_web.training_points_required_for_direction", return_value=required),
        patch("fm_odds_web.write_bidirectional_intimacy") as intimacy,
        patch("fm_odds_web.commit_relationship_training_settlement",
              return_value={"completed": {}, "archive": {"created": True}}) as commit,
        patch("fm_odds_web.restore_relationship_training_room") as restore,
        patch("fm_odds_web.invalidate_club_profile_cache"),
    ):
        result = value.relationship_training_room_settle({"room_id": "room-1"})
    assert restore.call_count == 0 and result["ok"] is True
    return commit.call_args, intimacy


def test_unlicensed_coach_settles_early_with_the_coach_multiplier_from_enter():
    value = team_training_state()
    value.club_profiles[10]["staff"][1]["abilities"] = {"人员管理": 18, "激励": 18}
    coach = {"kind": "staff", "id": 21, "name": "无证教练", "role": "coach", "team_id": 10}
    player = {"kind": "player", "id": 1, "name": "A", "role": "player", "team_id": 10}
    session = {
        "id": "early-tac", "room_sku": "tactical_room", "target": "16",
        "participants": [coach, player], "attributes": ["hidden:职业素养"],
        "captured_multipliers": {"coach": 2.5}, "estimated_settle_on": "2026-09-01",
    }
    plan = {
        "elapsed_days": 4, "focus_coefficient": 1.0, "attribute_points": 12.0,
        "beneficiaries": [player], "guiders": [coach],
        "attributes": [{"key": "hidden:职业素养", "kind": "hidden"}], "pairs": [],
    }
    call, _intimacy = _settle_with_attribute(value, session, plan, {"1:hidden:职业素养": 10})
    assert call.kwargs["attribute_progress"]["tactical_room:player:1:hidden:职业素养"] == 30.0
    early = call.args[2]["early_settlement"]
    assert early["detected_on"] == "2026-08-20"
    assert early["estimated_settle_on"] == "2026-09-01"


def test_mentor_no_longer_credible_settles_early_with_mentor_multiplier_from_enter():
    value = team_training_state()
    mentor = {"kind": "player", "id": 1, "name": "A", "role": "mentor", "team_id": 10}
    student = {"kind": "player", "id": 2, "name": "B", "role": "student", "team_id": 10}
    session = {
        "id": "early-mentor", "room_sku": "mentoring_room", "target": "until_increase",
        "participants": [mentor, student], "attributes": ["精神:领导力"],
        "captured_multipliers": {"mentor": {"2": 3.0}},
    }
    plan = {
        "elapsed_days": 2, "focus_coefficient": 1.0, "attribute_points": 6.0,
        "beneficiaries": [student], "guiders": [mentor],
        "attributes": [{"key": "精神:领导力", "kind": "visible"}], "pairs": [],
    }
    call, _intimacy = _settle_with_attribute(
        value, session, plan, {"1:精神:领导力": 18, "2:精神:领导力": 10},
    )
    assert call.kwargs["attribute_progress"]["mentoring_room:player:2:精神:领导力"] == 18.0
    assert call.args[2]["early_settlement"]["details"] == [
        fm_odds_web.MENTOR_NOT_CREDIBLE_MESSAGE,
    ]


def test_negative_relationship_settles_early_without_writing_that_pair():
    value = team_training_state()
    left = {"kind": "player", "id": 1, "name": "A", "role": "player_a", "team_id": 10}
    right = {"kind": "player", "id": 2, "name": "B", "role": "player_b", "team_id": 10}
    session = {
        "id": "early-neg", "room_sku": "mind_room", "target": "until_increase",
        "participants": [left, right], "attributes": ["精神:意志力"],
    }
    plan = {
        "elapsed_days": 3, "focus_coefficient": 1.0, "attribute_points": 9.0,
        "beneficiaries": [left, right], "guiders": [],
        "attributes": [{"key": "精神:意志力", "kind": "visible"}],
        "pairs": [{
            "person_a": left, "person_b": right, "reason_a2b": 5, "reason_b2a": 5,
            "base_increment": 0.99,
        }],
    }
    negative = {"a_to_b": {"relation_type": 2, "level": 30}, "b_to_a": None}
    call, intimacy = _settle_with_attribute(
        value, session, plan, {"1:精神:意志力": 10, "2:精神:意志力": 10},
        relation=negative,
    )
    intimacy.assert_not_called()
    assert call.kwargs["intimacy_progress"] == {}
    assert call.kwargs["attribute_progress"]["mind_room:player:1:精神:意志力"] == 9.0
    assert "负面关系" in call.args[2]["early_settlement"]["details"][0]


def test_enter_captures_guider_multipliers(team_room_store):
    value = team_training_state()
    with patch.object(value, "relationship_training_room_preview", return_value={
        "target_options": {"until_increase": _option(3)},
        "captured_multipliers": {"coach": 1.75},
    }):
        option = value._team_training_estimate({}, "tactical_room", "until_increase")
    assert option["captured_multipliers"] == {"coach": 1.75}
    with patch.object(value, "_team_training_estimate", return_value=option):
        with (
            patch.object(value, "_bind_current_save"),
            patch.object(value, "_ensure_training_task_migration", return_value=False),
            patch.object(value, "relationship_training_rooms_state", return_value={}),
            patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
            patch("fm_odds_web.resolve_public_person_address", return_value=0x1000),
            patch("fm_odds_web.persons_relation_negative", return_value=False),
            patch("fm_odds_web.commit_documents_with_combined_charge", _fake_charge_commit(None, [])),
            patch("fm_odds_web.public_economy", return_value={}),
        ):
            room = value.relationship_training_room_enter(_tactical_payload(20, "cap"))["room"]
    assert _team_room(team_room_store, room["id"])["captured_multipliers"] == {"coach": 1.75}


# ---- 团队训练：预计时间、到期自动结算、每 14 天补结算 ----

def _fake_settle(value, settled):
    """Stand-in for the native settle: real room state transitions only."""
    from tools import relationship_training as rooms

    def settle(room_id, *, completed_on=None):
        game_date = value.output["game_date"]
        session = rooms.release_relationship_training_room(
            room_id, min(game_date, completed_on) if completed_on else game_date,
        )
        settled.append((room_id, session["completed_on"]))
        completed = rooms.finalize_relationship_training_room(room_id, session["id"], {})
        return {"completed": completed, "archive": {}}

    return settle


def _advance(value, game_date, settled, settle=None, negative=False):
    value.output["game_date"] = game_date
    with (
        patch.object(
            value, "_settle_relationship_training_room",
            side_effect=settle or _fake_settle(value, settled),
        ),
        patch("fm_odds_web.borrow_game_operation", side_effect=lambda: operation_context()),
        patch("fm_odds_web.persons_relation_negative", return_value=negative),
    ):
        return value._settle_due_team_training(game_date)


def _team_room(store, room_id):
    return next(
        row for row in store["relationship_training_rooms"]["rooms"]
        if row["id"] == room_id
    )


def test_enter_stores_estimated_settle_date_and_payload_shows_it(team_room_store):
    value = team_training_state()
    payload = {**_mind_payload("eta"), "target": "16"}
    entered = _enter(value, payload, estimate=4)
    room = entered["room"]
    assert room["estimated_total_days"] == 4
    assert room["estimated_settle_on"] == "2026-08-24"
    assert room["remaining_days"] == 4
    assert room["target"] == "16"
    assert _team_room(team_room_store, room["id"])["estimated_settle_on"] == "2026-08-24"
    with patch("fm_odds_web.public_training_ground", return_value={}):
        ground = value._public_training_ground("2026-08-22")
    rooms_by_sku = {row["sku"]: row for row in ground["team_rooms"]}
    assert rooms_by_sku["tactical_room"]["active"] is None
    assert rooms_by_sku["mind_room"]["active"] == {
        "room_id": room["id"], "status": "occupied",
        "started_on": "2026-08-20", "settle_on": "2026-08-24",
        "estimated_total_days": 4, "days_used": 2, "remaining_days": 2,
        "fee_minor": 250_000_000, "attributes": ["精神:意志力"], "target": "16",
        "participants": [{
            "id": 1, "kind": "player", "role": "player_a", "name": "A",
            "estimated_days": 4, "settle_on": "2026-08-24", "remaining_days": 2,
        }],
    }
    assert ground["eligible_staff_ids"] == {"analyst": [60], "coach": [20], "scientist": [40]}


def test_enter_uses_the_chosen_target_option_and_per_person_days(team_room_store):
    value = team_training_state()
    option = _option(9, [
        {"id": 1, "kind": "player", "estimated_days": 9, "has_effect": True},
    ])
    with patch.object(value, "relationship_training_room_preview", return_value={
        "target_options": {"until_increase": _option(2), "18": option},
    }) as preview:
        assert value._team_training_estimate({"attributes": []}, "mind_room", "18") == {
            **option, "captured_multipliers": {},
        }
    assert preview.call_args.args[0]["target"] == "18"
    charges = []
    with patch.object(value, "relationship_training_room_preview", return_value={
        "target_options": {"20": None},
    }):
        with pytest.raises(ValueError, match="已达到或超过目标"):
            with (
                patch.object(value, "_bind_current_save"),
                patch.object(value, "_ensure_training_task_migration", return_value=False),
                patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
                patch("fm_odds_web.resolve_public_person_address", return_value=0x1000),
                patch("fm_odds_web.persons_relation_negative", return_value=False),
                patch("fm_odds_web.commit_documents_with_combined_charge", _fake_charge_commit(None, charges)),
            ):
                value.relationship_training_room_enter({**_mind_payload("t20"), "target": "20"})
    assert charges == []


def test_enter_rejects_unknown_target_before_charging(team_room_store):
    value = team_training_state()
    charges = []
    with pytest.raises(ValueError, match="训练目标"):
        _enter(value, {**_mind_payload("bad"), "target": "17"}, charge=charges)
    assert charges == []


def test_one_session_per_room_at_a_time(team_room_store):
    value = team_training_state()
    _enter(value, _mind_payload("first", player_id=1))
    charges = []
    with pytest.raises(ValueError, match="正在训练中"):
        _enter(value, _mind_payload("second", player_id=2), charge=charges)
    assert charges == []


def test_auto_settle_on_due_date_exactly_once(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _mind_payload("due"), estimate=4)["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    assert _advance(value, "2026-08-23", settled)["settled_room_ids"] == []
    result = _advance(value, "2026-08-24", settled)
    assert result["settled_room_ids"] == [room_id]
    assert settled == [(room_id, "2026-08-24")]
    _advance(value, "2026-08-24", settled)
    _advance(value, "2026-08-25", settled)
    assert settled == [(room_id, "2026-08-24")]
    room = _team_room(team_room_store, room_id)
    assert room["status"] == "idle"
    assert room["last_session"]["status"] == "completed"


def test_skipped_days_still_settle_as_of_the_due_date(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _mind_payload("jump"), estimate=4)["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    _advance(value, "2026-09-30", settled)
    assert settled == [(room_id, "2026-08-24")]


def test_manual_settle_before_due_prevents_later_auto_settle(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _mind_payload("manual"), estimate=4)["room"]["id"]
    settled = []
    value.output["game_date"] = "2026-08-22"
    with (
        patch.object(value, "_settle_relationship_training_room",
                     side_effect=_fake_settle(value, settled)),
        patch.object(value, "relationship_training_rooms_state", return_value={}),
    ):
        assert value.relationship_training_room_settle({"room_id": room_id})["ok"]
    assert settled == [(room_id, "2026-08-22")]
    for day in ("2026-08-24", "2026-09-10", "2026-12-31"):
        result = _advance(value, day, settled)
        assert result["settled_room_ids"] == []
    assert settled == [(room_id, "2026-08-22")]


def test_manual_settle_racing_the_auto_claim_settles_once(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _mind_payload("race"), estimate=1)["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    settle = _fake_settle(value, settled)

    def manual_wins_then_auto_runs(claimed_id, *, completed_on=None):
        settle(claimed_id)  # the manual button lands after the claim
        return settle(claimed_id, completed_on=completed_on)

    result = _advance(value, "2026-08-21", settled, settle=manual_wins_then_auto_runs)
    assert settled == [(room_id, "2026-08-21")]
    assert result["errors"] == [] and result["settled_room_ids"] == []


def test_sweep_catches_a_missed_session(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _mind_payload("miss"), estimate=4)["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    busy = Mock(side_effect=RuntimeError("游戏忙"))
    failed = _advance(value, "2026-08-24", settled, settle=busy)
    assert failed["errors"] and failed["sweep"] is False
    # Same game date again: the due check already tried today, no retry.
    assert _advance(value, "2026-08-24", settled)["settled_room_ids"] == []
    # The game date then jumps back (another save loaded) and the sweep runs.
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-10"
    swept = _advance(value, "2026-08-24", settled)
    assert swept["sweep"] is True
    assert swept["settled_room_ids"] == [room_id]
    assert settled == [(room_id, "2026-08-24")]
    assert team_room_store["relationship_training_rooms"]["last_sweep_on"] == "2026-08-24"


def test_sweep_settles_a_session_without_estimate(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _mind_payload("legacy"))["room"]["id"]
    _team_room(team_room_store, room_id)["estimated_settle_on"] = None
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    assert _advance(value, "2026-08-30", settled)["settled_room_ids"] == []
    swept = _advance(value, "2026-09-03", settled)
    assert swept["sweep"] is True and swept["settled_room_ids"] == [room_id]


def test_sweep_does_not_resettle_or_settle_early(team_room_store):
    value = team_training_state()
    from tools import relationship_training as rooms
    done_id = _enter(value, _mind_payload("done", player_id=1), estimate=2)["room"]["id"]
    later_id = rooms.enter_relationship_training_room(
        "tactical_room", [
            {"kind": "staff", "id": 20, "name": "助教", "role": "coach"},
            {"kind": "player", "id": 2, "name": "B", "role": "player"},
        ], ["精神:团队合作"], "2026-08-20", client_submission_id="later",
        estimated_days=30,
    )["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    _advance(value, "2026-08-22", settled)
    assert settled == [(done_id, "2026-08-22")]
    swept = _advance(value, "2026-09-03", settled)
    assert swept["sweep"] is True and swept["settled_room_ids"] == []
    assert settled == [(done_id, "2026-08-22")]
    assert _team_room(team_room_store, later_id)["status"] == "occupied"
    # Repeated runs on the sweep date do not sweep again.
    assert _advance(value, "2026-09-03", settled)["sweep"] is False


def test_sweep_cadence_follows_game_date():
    from tools.relationship_training import team_training_sweep_due
    assert team_training_sweep_due(None, "2026-08-20") is True
    assert team_training_sweep_due("2026-08-20", "2026-09-02") is False
    assert team_training_sweep_due("2026-08-20", "2026-09-03") is True
    assert team_training_sweep_due("2026-08-20", "2028-01-01") is True
    assert team_training_sweep_due("2026-08-20", "2026-08-01") is True
    assert team_training_sweep_due("2026-08-20", "") is False


def test_ineligible_participant_settles_early_once_on_detection_day(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _tactical_payload(20, "early"), estimate=10)["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    with patch("fm_odds_web.persons_relation_negative", return_value=False), \
            patch("fm_odds_web.borrow_game_operation", side_effect=lambda: operation_context()):
        assert _advance(value, "2026-08-22", settled)["settled_room_ids"] == []
        value.club_profiles[10]["staff"][0]["coaching_license"] = {"code": 0}
        with patch("fm_odds_web.refund_combined_funds") as refund:
            result = _advance(value, "2026-08-23", settled)
        refund.assert_not_called()
        assert result["early_settled_room_ids"] == [room_id]
        assert settled == [(room_id, "2026-08-23")]  # days actually elapsed: 3
        for day in ("2026-08-23", "2026-08-30", "2026-09-10"):
            _advance(value, day, settled)
    assert settled == [(room_id, "2026-08-23")]
    assert _team_room(team_room_store, room_id)["status"] == "idle"


def test_negative_relationship_is_detected_early_on_game_day(team_room_store):
    value = team_training_state()
    payload = _mind_payload("neg")
    payload["participants"].append({"kind": "player", "id": 2, "team_id": 10, "role": "player_b"})
    room_id = _enter(value, payload, estimate=10)["room"]["id"]
    with (
        patch("fm_odds_web.borrow_game_operation", side_effect=lambda: operation_context()),
        patch("fm_odds_web.persons_relation_negative", return_value=True),
    ):
        reasons = value._team_training_early_reasons("2026-08-21")
    assert "负面关系" in reasons[room_id]
    # Read once per game date: a second sync the same day does not reopen the game.
    with patch("fm_odds_web.borrow_game_operation") as again:
        value._team_training_early_reasons("2026-08-21")
    again.assert_not_called()
    with patch("fm_odds_web.borrow_game_operation", side_effect=RuntimeError("游戏未连接")):
        assert value._team_training_early_reasons("2026-08-22") == {}


def test_training_sync_runs_team_due_check_in_release_build():
    value = team_training_state()
    value.club_profile = None
    value.attribute_growth_hook = Mock()
    value.attribute_growth_hook.sync.return_value = {"installed": False}
    with (
        patch("fm_odds_web.FROZEN", True),
        patch.object(value, "_ensure_training_task_migration", return_value=False),
        patch.object(value, "_settle_due_team_training", return_value={
            "sweep": False, "settled_room_ids": ["r"], "early_settled_room_ids": [], "errors": [],
        }) as due,
        patch("fm_odds_web.active_training_focuses", return_value=[]),
        patch("fm_odds_web.advance_training_focuses", return_value=[]) as advance,
        patch("fm_odds_web.due_coaching_license_focuses", return_value=[]),
    ):
        result = value._sync_training_focuses("2026-08-21")
    due.assert_called_once_with("2026-08-21")
    advance.assert_called_once_with("2026-08-21")
    assert result["team_training"]["settled_room_ids"] == ["r"]


def _settle_mind(target, *, direction="inc", before=10, points=9.0):
    value = relationship_training_state()
    participant = {
        "kind": "player", "id": 1, "name": "A", "role": "player_a", "team_id": 10,
    }
    session = {
        "id": "focus-t", "room_sku": "mind_room", "target": target,
        "participants": [participant], "attributes": ["hidden:适应性"],
    }
    plan = {
        "elapsed_days": 3, "focus_coefficient": 1.0, "attribute_points": points,
        "beneficiaries": [participant],
        "attributes": [{"key": "hidden:适应性", "kind": "hidden", "direction": direction}],
        "pairs": [],
    }
    with (
        patch.object(value, "_team_training_rooms", return_value=[]),
        patch("fm_odds_web.FROZEN", True),
        patch.object(value, "_bind_current_save"),
        patch.object(value, "_ensure_training_task_migration", return_value=False),
        patch.object(value, "relationship_training_rooms_state", return_value={"rooms": []}),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {}, "height_baselines": {},
        }),
        patch("fm_odds_web.borrow_game_operation", return_value=operation_context()),
        patch("fm_odds_web.resolve_public_person_address", return_value=0x1000),
        patch("fm_odds_web.read_person_public_profile", return_value={"uid": 1}),
        patch("fm_odds_web.read_player_training_attributes", return_value={
            "1:hidden:适应性": before,
        }),
        patch("fm_odds_web.training_points_required_for_direction", return_value=1),
        patch("fm_odds_web.develop_player_hidden_attribute", side_effect=lambda *a: {
            "_original_raw": 0, "_updated_raw": 1,
        }) as develop,
        patch("fm_odds_web.commit_relationship_training_settlement",
              return_value={"completed": {}, "archive": {}}) as commit,
        patch("fm_odds_web.invalidate_club_profile_cache"),
    ):
        value.relationship_training_room_settle({"room_id": "room-1"})
    progress = commit.call_args.kwargs["attribute_progress"].get("mind_room:player:1:hidden:适应性")
    return develop.call_count, progress


def test_settle_stops_at_the_session_target_and_drops_overflow():
    assert _settle_mind("until_increase") == (1, 0)
    assert _settle_mind("14") == (4, 0)
    # Not enough points to reach the target: partial progress is kept.
    assert _settle_mind("20", points=3.0) == (3, 0)


def test_settle_lower_effect_drops_one_point_per_session():
    assert _settle_mind("18", direction="dec") == (1, 0)


def test_settle_skips_effect_already_at_target():
    assert _settle_mind("14", before=15) == (0, None)


# ---- 团队训练：参与者离队 → 当天提前结算，跳过此人 ----

def _without(value, kind, person_id):
    key = "staff" if kind == "staff" else "players"
    value.club_profiles[10][key] = [
        row for row in value.club_profiles[10][key] if int(row["id"]) != person_id
    ]


def test_left_coach_settles_early_with_captured_multiplier_and_teachable_list():
    value = team_training_state()
    _without(value, "staff", 20)
    coach = {"kind": "staff", "id": 20, "name": "助教", "role": "coach", "team_id": 10}
    player = {"kind": "player", "id": 1, "name": "A", "role": "player", "team_id": 10}
    session = {
        "id": "left-coach", "room_sku": "tactical_room", "target": "20",
        "participants": [coach, player], "attributes": ["hidden:职业素养", "hidden:雄心"],
        "captured_multipliers": {"coach": 2.0, "coach_teachable": ["hidden:职业素养"]},
    }
    plan = {
        "elapsed_days": 4, "focus_coefficient": 1.0, "attribute_points": 12.0,
        "beneficiaries": [player], "guiders": [coach],
        "attributes": [
            {"key": "hidden:职业素养", "kind": "hidden"},
            {"key": "hidden:雄心", "kind": "hidden"},
        ],
        "pairs": [{"person_a": coach, "person_b": player, "reason_a2b": 7,
                   "reason_b2a": 8, "base_increment": 1.32}],
    }
    call, intimacy = _settle_with_attribute(
        value, session, plan, {"1:hidden:职业素养": 10, "1:hidden:雄心": 10},
    )
    progress = call.kwargs["attribute_progress"]
    assert progress == {"tactical_room:player:1:hidden:职业素养": 24.0}
    intimacy.assert_not_called()
    early = call.args[2]["early_settlement"]
    assert early["reason"] == "participant_left_team"
    assert early["skipped_participant_ids"] == [20]
    assert early["details"][0].startswith("participant_left_team")


def test_left_mentor_uses_captured_values_and_multiplier():
    value = team_training_state()
    _without(value, "player", 1)
    mentor = {"kind": "player", "id": 1, "name": "A", "role": "mentor", "team_id": 10}
    student = {"kind": "player", "id": 2, "name": "B", "role": "student", "team_id": 10}
    session = {
        "id": "left-mentor", "room_sku": "mentoring_room", "target": "20",
        "participants": [mentor, student], "attributes": ["精神:领导力"],
        "captured_multipliers": {"mentor": {"2": 3.0}, "mentor_values": {"精神:领导力": 18}},
    }
    plan = {
        "elapsed_days": 2, "focus_coefficient": 1.0, "attribute_points": 6.0,
        "beneficiaries": [student], "guiders": [mentor],
        "attributes": [{"key": "精神:领导力", "kind": "visible"}], "pairs": [],
    }
    call, _intimacy = _settle_with_attribute(value, session, plan, {"2:精神:领导力": 10})
    assert call.kwargs["attribute_progress"] == {"mentoring_room:player:2:精神:领导力": 18.0}
    assert call.args[2]["early_settlement"]["skipped_participant_ids"] == [1]


def test_left_student_is_skipped_and_the_other_student_settles():
    value = team_training_state()
    value.club_profiles[10]["players"][0]["ca"] = 150  # credible mentor
    mentor = {"kind": "player", "id": 1, "name": "A", "role": "mentor", "team_id": 10}
    stays = {"kind": "player", "id": 2, "name": "B", "role": "student", "team_id": 10}
    left = {"kind": "player", "id": 3, "name": "C", "role": "student", "team_id": 10}
    session = {
        "id": "left-student", "room_sku": "mentoring_room", "target": "20",
        "participants": [mentor, stays, left], "attributes": ["精神:领导力"],
        "captured_multipliers": {"mentor": {"2": 2.0, "3": 2.0}},
    }
    plan = {
        "elapsed_days": 2, "focus_coefficient": 1.0, "attribute_points": 6.0,
        "beneficiaries": [stays, left], "guiders": [mentor],
        "attributes": [{"key": "精神:领导力", "kind": "visible"}], "pairs": [],
    }
    with patch("fm_odds_web.estimate_player_status_tier", return_value=1):
        call, _intimacy = _settle_with_attribute(
            value, session, plan, {"1:精神:领导力": 18, "2:精神:领导力": 10},
        )
    assert list(call.kwargs["attribute_progress"]) == ["mentoring_room:player:2:精神:领导力"]
    early = call.args[2]["early_settlement"]
    assert early["skipped_participant_ids"] == [3]
    assert early["reason"] == "participant_left_team"


def test_left_pair_member_gets_no_closeness_and_gives_no_bonus():
    value = team_training_state()
    _without(value, "player", 2)
    left = {"kind": "player", "id": 1, "name": "A", "role": "player_a", "team_id": 10}
    gone = {"kind": "player", "id": 2, "name": "B", "role": "player_b", "team_id": 10}
    session = {
        "id": "left-pair", "room_sku": "mind_room", "target": "20",
        "participants": [left, gone], "attributes": ["精神:意志力"],
    }
    plan = {
        "elapsed_days": 3, "focus_coefficient": 1.0, "attribute_points": 9.0,
        "beneficiaries": [left, gone], "guiders": [],
        "attributes": [{"key": "精神:意志力", "kind": "visible"}],
        "pairs": [{"person_a": left, "person_b": gone, "reason_a2b": 5,
                   "reason_b2a": 5, "base_increment": 0.99}],
    }
    friendly = {"a_to_b": {"relation_type": 1, "level": 90, "reason": 9}, "b_to_a": None}
    call, intimacy = _settle_with_attribute(
        value, session, plan, {"1:精神:意志力": 10}, relation=friendly,
    )
    intimacy.assert_not_called()
    assert call.kwargs["intimacy_progress"] == {}
    assert call.kwargs["attribute_progress"] == {"mind_room:player:1:精神:意志力": 9.0}


def test_unreadable_team_snapshot_does_not_count_as_left():
    value = team_training_state()
    value.club_profiles[10]["players"] = []  # roster not read
    player = {"kind": "player", "id": 1, "name": "A", "role": "player_a", "team_id": 10}
    session = {"id": "unread", "room_sku": "mind_room", "participants": [player],
               "attributes": ["精神:意志力"]}
    plan = {"elapsed_days": 1, "focus_coefficient": 1.0, "attribute_points": 3.0,
            "beneficiaries": [player], "guiders": [], "attributes": [], "pairs": []}
    with (
        patch.object(value, "_bind_current_save"),
        patch.object(value, "_data_scope_id", return_value="account-1"),
        patch.object(value, "_ensure_training_task_migration", return_value=False),
        patch("fm_odds_web.release_relationship_training_room", return_value=session),
        patch("fm_odds_web.relationship_training_effect_plan", return_value=plan),
        patch("fm_odds_web.relationship_training_progress", return_value={
            "attribute_progress": {}, "intimacy_progress": {}, "height_baselines": {},
        }),
        patch("fm_odds_web.borrow_game_operation", side_effect=lambda **_k: operation_context()),
        patch("fm_odds_web.commit_relationship_training_settlement") as commit,
        patch("fm_odds_web.restore_relationship_training_room") as restore,
    ):
        with pytest.raises(ValueError, match="不属于原球队"):
            value.relationship_training_room_settle({"room_id": "room-1"})
    commit.assert_not_called()
    restore.assert_called_once()
    room = {"id": "r", "sku": "mind_room", "participants": [player]}
    assert value._team_training_disqualification(room, list(value.club_profiles.values())) == ""
    assert value._team_training_disqualification(room, []) == ""


def test_left_participant_detected_on_game_day_settles_once_on_every_path(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _tactical_payload(20, "left"), estimate=10)["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    settled = []
    assert _advance(value, "2026-08-21", settled)["settled_room_ids"] == []
    # The game is unreadable for a day (no snapshot): nothing happens.
    profiles = value.club_profiles
    value.club_profiles = {}
    assert _advance(value, "2026-08-22", settled)["settled_room_ids"] == []
    value.club_profiles = profiles
    _without(value, "staff", 20)
    with patch("fm_odds_web.refund_combined_funds") as refund:
        result = _advance(value, "2026-08-23", settled)
    refund.assert_not_called()
    assert result["early_settled_room_ids"] == [room_id]
    assert settled == [(room_id, "2026-08-23")]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-01"
    assert _advance(value, "2026-08-23", settled)["sweep"] is True
    _advance(value, "2026-08-30", settled)
    assert settled == [(room_id, "2026-08-23")]
    assert _team_room(team_room_store, room_id)["status"] == "idle"


def test_left_participant_found_by_the_sweep_settles_once(team_room_store):
    value = team_training_state()
    room_id = _enter(value, _tactical_payload(20, "left-sweep"), estimate=30)["room"]["id"]
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-20"
    _without(value, "staff", 20)
    settled = []
    busy = Mock(side_effect=RuntimeError("游戏忙"))
    assert _advance(value, "2026-08-21", settled, settle=busy)["errors"]
    assert _advance(value, "2026-08-21", settled)["settled_room_ids"] == []
    team_room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-08-01"
    swept = _advance(value, "2026-08-21", settled)
    assert swept["sweep"] is True and swept["early_settled_room_ids"] == [room_id]
    assert settled == [(room_id, "2026-08-21")]


def test_preview_captures_coach_teachable_and_mentor_values():
    result = _tactical_preview(12, "16")
    assert result["captured_multipliers"]["coach_teachable"] == ["hidden:职业素养"]
    assert result["captured_multipliers"]["coach"] > 0
