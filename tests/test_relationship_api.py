import threading
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
    if not fm_odds_web.FROZEN:
        assert ("POST", "/api/relations/adjust-bidirectional") not in registered
        assert ("POST", "/api/training/relationship-rooms/settle") in registered


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


def _enter(value, payload, *, charge=None, refund=None, payment=None):
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
        patch("fm_odds_web.charge_combined_funds", return_value=payment) as charged,
        patch("fm_odds_web.refund_combined_funds") as refunded,
        patch("fm_odds_web.public_economy", return_value={"bank_balance": 1.0}),
    ):
        try:
            return value.relationship_training_room_enter(payload)
        finally:
            if charge is not None:
                charge.extend(charged.call_args_list)
            if refund is not None:
                refund.extend(refunded.call_args_list)


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


def test_team_room_enter_requires_request_id_before_charging(team_room_store):
    value = team_training_state()
    charges = []
    with pytest.raises(ValueError, match="刷新页面"):
        _enter(value, _mind_payload(submission=""), charge=charges)
    assert charges == []


def test_team_room_enter_refunds_when_room_write_fails(team_room_store):
    value = team_training_state()
    _enter(value, _mind_payload("first"))
    charges, refunds = [], []
    # Same player again under a new request id: rejected after the charge.
    with pytest.raises(ValueError, match="其他团队训练房间"):
        _enter(value, _mind_payload("second"), charge=charges, refund=refunds)
    assert len(charges) == 1 and len(refunds) == 1
    assert refunds[0].args[1] == "relationship_training_room_session_rollback"


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
        patch("fm_odds_web.charge_combined_funds", side_effect=lambda *a, **k: calls.append(a) or payment),
        patch("fm_odds_web.refund_combined_funds"),
        patch("fm_odds_web.public_economy", return_value={}),
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


def _settle_tactical(value, coach_id):
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
        patch("fm_odds_web.FROZEN", False),
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
            settle_calls = (commit.call_count, restore.call_count)
    return settle_calls


def test_tactical_room_settle_uses_the_same_coach_rule_as_enter():
    value = team_training_state()
    assert _settle_tactical(value, 20)[0] == 1
    with pytest.raises(ValueError, match="持证"):
        _settle_tactical(team_training_state(), 21)


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
