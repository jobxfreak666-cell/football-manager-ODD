from __future__ import annotations

from copy import deepcopy

import pytest

from tools import relationship_training as rooms


@pytest.fixture()
def room_store(monkeypatch):
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
    monkeypatch.setattr(rooms, "local_purchase_price", lambda value, _settings: value)
    return documents


def _player(identifier: int, role: str) -> dict:
    return {
        "kind": "player", "id": identifier, "name": f"P{identifier}",
        "role": role, "person_key": hex(0x1000 + identifier),
        "address": hex(0x2000 + identifier), "team_id": 10,
    }


def test_catalog_is_the_team_training_module_without_floor_or_unlock(room_store):
    catalog = rooms.relationship_training_catalog()
    assert catalog["module"] == "team_training"
    assert "scene" not in catalog and "floor_limit" not in catalog
    assert {row["sku"] for row in catalog["rooms"]} == set(rooms.ROOMS)
    assert "facilities" not in room_store["relationship_training_rooms"]
    for row in catalog["rooms"]:
        assert "unlock_cost" not in row and "scene" not in row


def test_session_fee_is_half_of_the_old_unlock_price(room_store):
    fees = {
        row["sku"]: row["session_fee_minor"]
        for row in rooms.relationship_training_catalog()["rooms"]
    }
    assert fees == {
        "mind_room": 250_000_000, "mentoring_room": 1_000_000_000,
        "tactical_room": 750_000_000, "video_analysis_room": 1_250_000_000,
        "sports_science_room": 1_500_000_000,
    }


def test_old_save_unlock_records_are_ignored_and_reused(room_store):
    room_store["relationship_training_rooms"] = {
        "schema_version": 2, "scene": "relationship_8f", "rooms": [{
            "id": "old-unlocked", "sku": "mind_room", "scene": "relationship_8f",
            "status": "idle", "unlocked_at": "2026-01-01T00:00:00", "participants": [],
        }],
    }
    entered = rooms.enter_relationship_training_room(
        "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20",
        client_submission_id="old-1",
    )
    assert entered["room"]["id"] == "old-unlocked"
    stored = room_store["relationship_training_rooms"]
    assert "scene" not in stored and stored["module"] == "team_training"


def test_catalog_uses_professional_room_descriptions():
    descriptions = {sku: row["description"] for sku, row in rooms.ROOMS.items()}
    assert descriptions["mind_room"] == "通过专注训练与心理调适，系统提升球员的心理素质与职业心态。"
    assert descriptions["mentoring_room"] == "由资深球员担任导师，面向同队学员开展能力传承与职业经验指导。"
    assert descriptions["tactical_room"] == "由教练团队开展专项战术辅导，提升球员的比赛理解、适应能力与稳定表现。"
    assert descriptions["video_analysis_room"] == "由分析团队结合比赛录像开展针对性复盘，强化球员的决策、预判与空间理解。"
    assert descriptions["sports_science_room"] == "由运动科学团队制定个体化体能方案，改善身体素质、负荷管理与伤病风险。"


def test_new_relationship_categories_follow_each_room_contract():
    expected = {
        "mentoring_room": (5, 5),
        "tactical_room": (7, 8),
        "video_analysis_room": (10, 10),
        "sports_science_room": (10, 10),
    }
    assert {
        sku: (rooms.ROOMS[sku]["reason_a2b"], rooms.ROOMS[sku]["reason_b2a"])
        for sku in expected
    } == expected


def test_rooms_need_no_unlock_to_enter(room_store):
    assert not hasattr(rooms, "unlock_relationship_training_room")
    entered = rooms.enter_relationship_training_room(
        "sports_science_room",
        [{**_player(1, "player"), "kind": "player"}, {
            "kind": "staff", "id": 9, "name": "S9", "role": "scientist", "team_id": 10,
        }],
        ["身体:体质"], "2026-08-20", client_submission_id="no-unlock",
    )
    assert entered["room"]["status"] == "occupied"
    assert entered["room"]["sku"] == "sports_science_room"


def test_room_entry_is_idempotent_and_prevents_cross_room_occupancy(room_store):
    participant = _player(1, "player_a")
    entered = rooms.enter_relationship_training_room(
        "mind_room", [participant], ["精神:意志力"], "2026-08-20",
        client_submission_id="submission-1",
    )
    repeated = rooms.enter_relationship_training_room(
        "mind_room", [participant], ["精神:意志力"], "2026-08-20",
        client_submission_id="submission-1",
    )
    assert repeated["replayed"] is True
    assert repeated["room"]["id"] == entered["room"]["id"]
    with pytest.raises(ValueError, match="其他团队训练房间"):
        rooms.enter_relationship_training_room(
            "mind_room", [participant], ["精神:意志力"], "2026-08-20",
        )
    # One session per room at a time (the room shows as 训练中 until settled).
    with pytest.raises(ValueError, match="正在训练中"):
        rooms.enter_relationship_training_room(
            "mind_room", [_player(2, "player_a")], ["精神:意志力"], "2026-08-20",
        )


def _commit_charging(charge):
    """Commit stub honouring the contract: one write, ``charge`` only on demand."""
    def commit(key, default, mutator):
        return rooms.update_document(key, default, lambda raw: mutator(raw, charge))
    return commit


def test_session_is_charged_once_and_replay_is_not_charged_again(room_store):
    charges: list[int] = []

    def charge():
        charges.append(1)
        return {"total": 2_500_000.0, "bank": 2_500_000.0, "wallet": 0.0, "transaction_id": "t1"}

    args = ("mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20")
    first = rooms.enter_relationship_training_room(
        *args, client_submission_id="pay-1", session_fee_minor=250_000_000,
        commit=_commit_charging(charge),
    )
    again = rooms.enter_relationship_training_room(
        *args, client_submission_id="pay-1", session_fee_minor=250_000_000,
        commit=_commit_charging(charge),
    )
    assert len(charges) == 1
    assert first["replayed"] is False and again["replayed"] is True
    assert again["payment"] == first["payment"]
    assert first["room"]["session_fee_minor"] == 250_000_000
    # The receipt survives settlement, so a late retry is still not charged.
    pending = rooms.release_relationship_training_room(first["room"]["id"], "2026-08-25")
    rooms.finalize_relationship_training_room(first["room"]["id"], pending["id"], {})
    late = rooms.enter_relationship_training_room(
        *args, client_submission_id="pay-1", session_fee_minor=250_000_000,
        commit=_commit_charging(charge),
    )
    assert late["replayed"] is True and len(charges) == 1


def test_charged_session_requires_a_submission_id(room_store):
    with pytest.raises(ValueError, match="刷新页面"):
        rooms.enter_relationship_training_room(
            "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20",
            commit=_commit_charging(lambda: {"total": 1.0}),
        )


def test_submission_id_reused_for_another_room_is_rejected_without_charge(room_store):
    rooms.enter_relationship_training_room(
        "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20",
        client_submission_id="same",
    )
    charges = []
    with pytest.raises(ValueError, match="其他安排"):
        rooms.enter_relationship_training_room(
            "mentoring_room", [_player(2, "mentor"), _player(3, "student")],
            ["精神:领导力"], "2026-08-20", client_submission_id="same",
            commit=_commit_charging(lambda: charges.append(1) or {"total": 1.0}),
            session_fee_minor=100,
        )
    assert charges == []


def test_invalid_entry_is_never_charged_and_stores_nothing(room_store):
    charges = []
    with pytest.raises(ValueError, match="至少选择一项训练属性"):
        rooms.enter_relationship_training_room(
            "mind_room", [_player(1, "player_a")], ["not-in-scope"], "2026-08-20",
            client_submission_id="refund-1", session_fee_minor=250_000_000,
            commit=_commit_charging(lambda: charges.append(1) or {"total": 1.0}),
        )
    assert charges == []
    assert room_store["relationship_training_rooms"]["rooms"] == []


def test_concurrent_double_click_charges_once(room_store):
    import threading

    charges = []
    start = threading.Barrier(2)

    def charge():
        charges.append(1)
        return {"total": 1.0, "bank": 1.0, "wallet": 0.0}

    results = []

    def submit():
        start.wait()
        results.append(rooms.enter_relationship_training_room(
            "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20",
            client_submission_id="double-click", session_fee_minor=100,
            commit=_commit_charging(charge),
        ))

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(charges) == 1
    assert sorted(row["replayed"] for row in results) == [False, True]
    assert len({row["room"]["id"] for row in results}) == 1


def test_tactical_coach_rule_accepts_licensed_assistant_and_rejects_unlicensed():
    assistant = {"job_type": 20, "coaching_license": {"code": 5}}
    unlicensed = {"job_type": 2, "coaching_license": {"code": 0}}
    job_one = {"job_type": 1, "coaching_license": {"code": 5}}
    assert rooms.tactical_coach_eligible(assistant)
    assert not rooms.tactical_coach_eligible(unlicensed)
    assert not rooms.tactical_coach_eligible(job_one)
    rooms.validate_relationship_training_staff("tactical_room", "coach", assistant)
    with pytest.raises(ValueError, match="持证"):
        rooms.validate_relationship_training_staff("tactical_room", "coach", unlicensed)


def test_release_creates_relationship_training_focus_then_finalize(room_store):
    room = rooms.enter_relationship_training_room(
        "mentoring_room", [_player(1, "mentor"), _player(2, "student")],
        ["精神:领导力"], "2026-08-01", client_submission_id="settle-1",
    )["room"]
    pending = rooms.release_relationship_training_room(room["id"], "2026-08-20")
    assert pending["focus_type"] == "relationship_training"
    assert pending["module"] == "team_training"
    assert "scene" not in pending
    assert pending["status"] == "pending_settlement"
    assert pending["facility_name"] == "传习室"
    assert pending["training_content"] == "精神:领导力"
    completed = rooms.finalize_relationship_training_room(
        room["id"], pending["id"],
        {"attribute_changes": [], "relationship_changes": []},
    )
    assert completed["status"] == "completed"
    stored = room_store["relationship_training_rooms"]["rooms"][0]
    assert stored["status"] == "idle"
    assert stored["participants"] == []


def test_effect_plan_uses_elapsed_days_focus_decay_and_expected_pairs():
    session = {
        "room_sku": "mentoring_room", "started_on": "2026-08-01",
        "completed_on": "2026-08-20",
        "attributes": ["精神:领导力", "hidden:职业素养"],
        "participants": [
            _player(1, "mentor"), _player(2, "student"), _player(3, "student"),
        ],
    }
    plan = rooms.relationship_training_effect_plan(session)
    assert plan["elapsed_days"] == 19
    assert 0.5 <= plan["focus_coefficient"] < 1
    assert [row["id"] for row in plan["beneficiaries"]] == [2, 3]
    assert len(plan["pairs"]) == 2
    assert all(row["base_increment"] == pytest.approx(6.27) for row in plan["pairs"])


def test_effect_plan_single_mind_room_has_no_relationship_pair():
    plan = rooms.relationship_training_effect_plan({
        "room_sku": "mind_room", "started_on": "2026-08-20",
        "completed_on": "2026-08-20", "attributes": ["精神:意志力"],
        "participants": [_player(1, "player_a")],
    })
    assert plan["elapsed_days"] == 0
    assert plan["pairs"] == []
    assert plan["attribute_points"] == 0


def test_directional_bonus_and_progress_keys_are_asymmetric():
    assert rooms.relationship_intimacy_bonus({
        "level": 70, "reason": 5, "relation_type": 1,
    }) == pytest.approx(0.7)
    assert rooms.relationship_intimacy_bonus({
        "level": 85, "reason": 9, "relation_type": 1,
    }) == pytest.approx(1.7)
    left = _player(1, "mentor")
    right = _player(2, "student")
    assert rooms.directed_progress_key(left, right) != rooms.directed_progress_key(right, left)


def test_authoritative_room_scopes_and_coach_multiplier():
    mind = rooms.ROOMS["mind_room"]["scope_attributes"]
    mentoring = rooms.ROOMS["mentoring_room"]["scope_attributes"]
    tactical = rooms.ROOMS["tactical_room"]["scope_attributes"]
    assert len(mind) == 7
    assert len(mentoring) == 12
    assert len(tactical) == 8
    assert [row["key"] for row in mentoring] == [
        "hidden:适应性", "hidden:雄心", "hidden:忠诚", "hidden:抗压能力",
        "hidden:职业素养", "hidden:体育精神", "hidden:情绪控制",
        "精神:领导力", "精神:意志力", "hidden:争论", "hidden:肮脏动作",
        "hidden:受伤倾向",
    ]
    assert tactical[-1]["key"] == "精神:团队合作"
    assert rooms.coach_composite_multiplier(1, 8_500) == pytest.approx(2.1)


def test_progress_document_video_and_sports_scopes():
    video = rooms.ROOMS["video_analysis_room"]["scope_attributes"]
    sports = rooms.ROOMS["sports_science_room"]["scope_attributes"]
    assert [row["key"] for row in video] == [
        "精神:集中", "精神:决断", "精神:预判", "精神:视野", "精神:镇定",
        "精神:防守站位", "精神:无球跑动", "精神:团队合作",
        "hidden:稳定性", "hidden:大赛发挥",
    ]
    assert [row["key"] for row in sports] == [
        "精神:勇敢", "身体:体质", "physical:height", "hidden:受伤倾向",
    ]


@pytest.mark.parametrize(
    ("room_sku", "role", "valid_job", "invalid_job"),
    [
        ("tactical_room", "coach", 2, 60),
        ("video_analysis_room", "analyst", 60, 40),
        ("sports_science_room", "scientist", 40, 60),
    ],
)
def test_relationship_training_staff_roles_are_strictly_scoped(
    room_sku, role, valid_job, invalid_job,
):
    valid = {"job_type": valid_job, "coaching_license": {"code": 1}}
    rooms.validate_relationship_training_staff(room_sku, role, valid)
    with pytest.raises(ValueError):
        rooms.validate_relationship_training_staff(
            room_sku, role,
            {"job_type": invalid_job, "coaching_license": {"code": 1}},
        )


def test_tactical_room_rejects_unlicensed_coaching_staff():
    with pytest.raises(ValueError, match="持证"):
        rooms.validate_relationship_training_staff(
            "tactical_room", "coach",
            {"job_type": 2, "coaching_license": {"code": 0}},
        )


def _guidance_person(
    name, role, team_id=679, team_type="club", squad_team_id=679,
    squad_type_code=0, squad_label="一线队",
):
    return {
        "name": name, "role": role, "team_id": team_id,
        "team_type": team_type, "squad_team_id": squad_team_id,
        "squad_type_code": squad_type_code, "squad_label": squad_label,
    }


def test_guidance_allows_same_squad_and_senior_to_youth():
    senior = _guidance_person("一线导师", "mentor")
    senior_student = _guidance_person("一线学员", "student")
    youth = _guidance_person(
        "U18 学员", "student", squad_team_id=2000340006,
        squad_type_code=12, squad_label="U18",
    )
    assert rooms.relationship_training_guidance_allowed(senior, senior_student)
    assert rooms.relationship_training_guidance_allowed(senior, youth)
    rooms.validate_relationship_training_guidance(
        "mentoring_room", [senior, senior_student, youth],
    )


@pytest.mark.parametrize("mentor,student", [
    (
        _guidance_person(
            "U18 导师", "mentor", squad_team_id=2000340006,
            squad_type_code=12, squad_label="U18",
        ),
        _guidance_person("一线学员", "student"),
    ),
    (
        _guidance_person("俱乐部导师", "mentor"),
        _guidance_person("国家队学员", "student", team_id=110, team_type="national"),
    ),
    (
        _guidance_person("A 队导师", "mentor"),
        _guidance_person("B 队学员", "student", team_id=680),
    ),
])
def test_guidance_rejects_upward_and_cross_parent_team(mentor, student):
    assert not rooms.relationship_training_guidance_allowed(mentor, student)
    with pytest.raises(ValueError, match="同一主体队伍"):
        rooms.validate_relationship_training_guidance(
            "mentoring_room", [mentor, student],
        )


def test_joint_training_rooms_do_not_apply_guidance_scope():
    participants = [
        _guidance_person("俱乐部球员", "player_a"),
        _guidance_person("国家队球员", "player_b", team_id=110, team_type="national"),
    ]
    rooms.validate_relationship_training_guidance("mind_room", participants)


@pytest.mark.parametrize(("room_sku", "guide_role"), [
    ("tactical_room", "coach"),
    ("video_analysis_room", "analyst"),
    ("sports_science_room", "scientist"),
])
def test_staff_guidance_rooms_reject_cross_parent_team(room_sku, guide_role):
    guide = _guidance_person("俱乐部职员", guide_role)
    player = _guidance_person(
        "国家队球员", "player", team_id=110, team_type="national",
    )
    with pytest.raises(ValueError, match="同一主体队伍"):
        rooms.validate_relationship_training_guidance(room_sku, [guide, player])


def test_team_capabilities_use_progress_document_jobs_and_weights():
    result = rooms.compute_team_capabilities([
        {"job_type": 40, "abilities": {"运动科学": 16}},
        {"job_type": 48, "abilities": {"运动科学": 12}},
        {"job_type": 60, "abilities": {
            "数据分析": 18, "判断球员能力": 16,
            "判断球员潜力": 14, "战术知识": 12,
        }},
    ])
    assert result["sports_science"] == {"cap": 14.0, "bonus": 0.2, "members": 2}
    assert result["analysis"]["cap"] == pytest.approx(16.1)
    assert result["analysis"]["bonus"] == pytest.approx(0.305)


def test_sports_science_height_formula_limits_and_retry_roll_are_deterministic():
    assert rooms.sports_science_height_limit(170) == 195
    assert rooms.sports_science_height_limit(180) == 200
    assert rooms.sports_science_height_limit(190) == 200
    assert rooms.sports_science_height_limit(205) == 210
    assert rooms.sports_science_height_probability(25, 180, 0.2, 0.5) == 0
    assert rooms.sports_science_height_probability(15, 160, 0.0, 0.0) == pytest.approx(0.6)
    first = rooms.deterministic_settlement_roll("focus-1", 7, "height")
    assert first == rooms.deterministic_settlement_roll("focus-1", 7, "height")
    assert first != rooms.deterministic_settlement_roll("focus-2", 7, "height")


def test_atomic_completion_updates_room_and_archive_together(room_store, monkeypatch):
    room = rooms.enter_relationship_training_room(
        "mind_room", [_player(1, "player_a")], ["精神:意志力"],
        "2026-08-01", client_submission_id="atomic-1",
    )["room"]
    pending = rooms.release_relationship_training_room(room["id"], "2026-08-20")
    documents = {
        **room_store,
        "training_archive": rooms._new_archive(),
    }

    def update_documents(_defaults, mutator, _scope_id):
        result = mutator(documents)
        room_store.update(documents)
        return deepcopy(result)

    monkeypatch.setattr(rooms, "update_documents", update_documents)
    result = rooms.commit_relationship_training_settlement(
        room["id"], pending["id"], {
            "attribute_changes": [], "relationship_changes": [],
        }, scope_id="account-1", height_baselines={"1": 178},
    )
    assert result["archive"]["created"] is True
    assert documents["relationship_training_rooms"]["rooms"][0]["status"] == "idle"
    assert documents["training_archive"]["totals"]["comprehensive"] == 1
    assert documents["relationship_training_rooms"]["height_baselines"] == {"1": 178}


def test_enter_stores_estimate_and_catalog_shows_remaining_days(room_store):
    entered = rooms.enter_relationship_training_room(
        "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-07-19",
        client_submission_id="eta", estimated_days=6, target="until_16",
        participant_estimates={("player", 1): 6},
    )
    room = entered["room"]
    assert (room["estimated_total_days"], room["estimated_settle_on"]) == (6, "2026-07-25")
    instance = rooms.relationship_training_catalog("2026-07-21")["rooms"][0]["instances"][0]
    assert (instance["days_used"], instance["remaining_days"]) == (2, 4)
    assert instance["active"]["target"] == "16"
    assert instance["active"]["participants"][0]["settle_on"] == "2026-07-25"
    session = rooms.release_relationship_training_room(room["id"], "2026-07-25")
    assert (session["estimated_settle_on"], session["target"]) == ("2026-07-25", "16")


def _effect(person_id, current, *, direction=1, daily=3.0, stored=0.0, mentor=None):
    return {
        "participant": {"id": person_id, "kind": "player"}, "attribute_kind": "visible",
        "base_eligible": True, "direction": direction, "current": current,
        "daily_points": daily, "stored_points": stored, "mentor_value": mentor,
    }


def test_target_goal_matches_equipment_semantics():
    assert rooms.normalize_team_training_target(None) == "until_increase"
    assert rooms.normalize_team_training_target("until_16") == "16"
    assert rooms.normalize_team_training_target(18) == "18"
    with pytest.raises(ValueError):
        rooms.normalize_team_training_target("until_10")
    assert rooms.team_training_goal("until_increase", 12, 1) == 13
    assert rooms.team_training_goal("16", 12, 1) == 16
    assert rooms.team_training_goal("14", 14, 1) is None  # at target: excluded
    assert rooms.team_training_goal("14", 15, 1) is None  # above target: excluded
    assert rooms.team_training_goal("18", 12, 1, mentor_value=15) == 15
    assert rooms.team_training_goal("20", 9, -1) == 8  # lower: always one point
    assert rooms.team_training_goal("20", 1, -1) is None


def test_target_options_use_equipment_formula_for_the_slowest_participant():
    from tools.training_ground import training_points_required_for_direction as need
    effects = [_effect(1, 12), _effect(2, 10), _effect(2, 9, direction=-1)]
    people = [{"id": 1, "kind": "player", "role": "a", "name": "A"},
              {"id": 2, "kind": "player", "role": "b", "name": "B"},
              {"id": 7, "kind": "staff", "role": "coach", "name": "C"}]
    options = rooms.team_training_target_options(effects, people, [], "2026-07-19")
    import math
    a_days = math.ceil(need(12, 1) / 3)
    b_days = max(math.ceil(need(10, 1) / 3), math.ceil(need(9, -1) / 3))
    increase = options["until_increase"]
    assert increase["days"] == max(a_days, b_days)
    person_days = {row["id"]: row["estimated_days"] for row in increase["participants"]}
    assert person_days == {1: a_days, 2: b_days, 7: increase["days"]}
    to16 = options["16"]
    expected_a = math.ceil(sum(need(v, 1) for v in range(12, 16)) / 3)
    expected_b = math.ceil(sum(need(v, 1) for v in range(10, 16)) / 3)
    assert to16["days"] == max(expected_a, expected_b)
    assert to16["settle_on"] == (
        __import__("datetime").date(2026, 7, 19)
        + __import__("datetime").timedelta(days=to16["days"])
    ).isoformat()
    # Everyone already at/above 14 on raise effects, no lower effect: invalid.
    high = rooms.team_training_target_options([_effect(1, 15)], people[:1], [], "2026-07-19")
    assert high["14"] is None and high["16"]["days"] >= 1


def test_target_options_fall_back_to_intimacy_for_height_only():
    options = rooms.team_training_target_options(
        [{"participant": {"id": 1, "kind": "player"}, "attribute_kind": "height"}],
        [{"id": 1, "kind": "player"}],
        [{"effect_pair": True, "a_to_b_effect": {"estimated_days_to_next": 3},
          "b_to_a_effect": {"estimated_days_to_next": 5}}],
        "2026-07-19",
    )
    assert options["20"]["days"] == 5


def test_claim_returns_a_due_room_until_it_is_settled(room_store):
    entered = rooms.enter_relationship_training_room(
        "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-07-19",
        client_submission_id="claim", estimated_days=2,
    )
    room_id = entered["room"]["id"]
    room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-07-19"
    assert rooms.claim_due_team_training_rooms("2026-07-20")["rooms"] == []
    expected = [{
        "room_id": room_id, "room_sku": "mind_room",
        "completed_on": "2026-07-21", "early_reason": "",
    }]
    assert rooms.claim_due_team_training_rooms("2026-07-25")["rooms"] == expected
    # A claim whose settle failed is not burned: the same date claims it again.
    assert rooms.claim_due_team_training_rooms("2026-07-25")["rooms"] == expected
    stored = room_store["relationship_training_rooms"]["rooms"][0]
    assert stored["status"] == "occupied" and not stored.get("auto_settle_attempted_on")
    session = rooms.release_relationship_training_room(room_id, "2026-07-21")
    rooms.finalize_relationship_training_room(room_id, session["id"], {})
    assert rooms.claim_due_team_training_rooms("2026-07-25")["rooms"] == []


def test_claim_settles_an_early_room_today_once(room_store):
    entered = rooms.enter_relationship_training_room(
        "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-07-19",
        client_submission_id="early", estimated_days=20,
        captured_multipliers={"coach": 1.5},
    )
    room_id = entered["room"]["id"]
    assert room_store["relationship_training_rooms"]["rooms"][0]["captured_multipliers"] == {"coach": 1.5}
    room_store["relationship_training_rooms"]["last_sweep_on"] = "2026-07-19"
    claim = rooms.claim_due_team_training_rooms("2026-07-22", {room_id: "x"})
    assert claim["rooms"] == [{
        "room_id": room_id, "room_sku": "mind_room",
        "completed_on": "2026-07-22", "early_reason": "x",
    }]
    session = rooms.release_relationship_training_room(room_id, "2026-07-22")
    assert session["captured_multipliers"] == {"coach": 1.5}
    # Settling: a repeated claim the same day finds nothing to release twice.
    assert rooms.claim_due_team_training_rooms("2026-07-22", {room_id: "x"})["rooms"] == []


# ---- 断电/被杀进程后重试：扣钱、房间、提交编号必须一起落盘 ----

@pytest.fixture()
def disk_account(tmp_path, monkeypatch):
    from unittest.mock import patch

    from tools import club_economy
    from tools.money import to_minor, write_minor

    monkeypatch.setattr(rooms, "load_settings", lambda: {})
    monkeypatch.setattr(rooms, "local_purchase_price", lambda value, _settings: value)
    with (
        patch("tools.club_economy.save_data_root", return_value=tmp_path),
        patch("tools.betting_account.save_data_root", return_value=tmp_path),
    ):
        economy = club_economy.load_economy()
        write_minor(economy, "general_balance", to_minor(10_000_000.0))
        club_economy.save_economy(economy)
        yield tmp_path


def _disk_state():
    from tools import account_store, club_economy

    account_store._CONTAINER_CACHE.clear()  # read back from disk like a fresh process
    documents = account_store.load_container(
        key="economy", legacy_path=club_economy.economy_path(),
    )["documents"]
    economy = documents.get("economy") or {}
    rooms_doc = rooms._normalize_state(documents.get("relationship_training_rooms"))
    occupied = [room for room in rooms_doc["rooms"] if room.get("status") == "occupied"]
    session_charges = [
        row for row in economy.get("transactions") or []
        if row.get("type") == "relationship_training_room_session"
    ]
    return club_economy._bank_balance_minor(economy), occupied, session_charges, rooms_doc


def _enter_paid(submission_id="crash-1"):
    from tools.club_economy import commit_documents_with_combined_charge
    from tools.money import from_minor

    fee_minor = 250_000_000

    def commit(key, default, mutator):
        return commit_documents_with_combined_charge(
            {key: default}, lambda documents, charge: mutator(documents[key], charge),
            from_minor(fee_minor), "relationship_training_room_session",
            room_sku="mind_room",
        )

    return rooms.enter_relationship_training_room(
        "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20",
        client_submission_id=submission_id, session_fee_minor=fee_minor,
        commit=commit,
    )


def test_kill_after_charge_before_room_saved_then_retry_charges_once(disk_account):
    from unittest.mock import patch

    from tools import club_economy

    bank_before, occupied, charges, _ = _disk_state()
    assert (len(occupied), len(charges)) == (0, 0)
    original = club_economy._collect_combined_funds

    def charge_then_die(*args, **kwargs):
        original(*args, **kwargs)
        raise SystemExit("process killed after charging")

    with patch.object(club_economy, "_collect_combined_funds", charge_then_die):
        with pytest.raises(SystemExit):
            _enter_paid()
    bank, occupied, charges, _ = _disk_state()
    assert (bank, len(occupied), len(charges)) == (bank_before, 0, 0)

    first = _enter_paid()
    again = _enter_paid()
    bank, occupied, charges, rooms_doc = _disk_state()
    assert first["replayed"] is False and again["replayed"] is True
    assert bank == bank_before - 250_000_000
    assert len(charges) == 1 and len(occupied) == 1
    assert list(rooms_doc["session_receipts"]) == ["crash-1"]
    assert rooms_doc["session_receipts"]["crash-1"]["payment"]["transaction_id"] == charges[0]["id"]


def test_kill_during_the_single_write_leaves_nothing_then_retry_charges_once(disk_account):
    from unittest.mock import patch

    bank_before, *_ = _disk_state()
    with patch("tools.betting_account.save_documents", side_effect=SystemExit("killed mid-write")):
        with pytest.raises(SystemExit):
            _enter_paid()
    bank, occupied, charges, rooms_doc = _disk_state()
    assert (bank, occupied, charges) == (bank_before, [], [])
    assert rooms_doc["session_receipts"] == {}

    _enter_paid()
    bank, occupied, charges, _ = _disk_state()
    assert bank == bank_before - 250_000_000
    assert len(charges) == 1 and len(occupied) == 1


def test_rejected_entry_on_disk_moves_no_money(disk_account):
    bank_before, *_ = _disk_state()
    _enter_paid("first")
    with pytest.raises(ValueError, match="其他团队训练房间"):
        _enter_paid("second")
    bank, occupied, charges, rooms_doc = _disk_state()
    assert bank == bank_before - 250_000_000
    assert len(charges) == 1 and len(occupied) == 1
    assert "second" not in rooms_doc["session_receipts"]
