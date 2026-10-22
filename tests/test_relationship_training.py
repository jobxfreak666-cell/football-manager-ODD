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
    # Two different players can use the same room type at the same time.
    other = rooms.enter_relationship_training_room(
        "mind_room", [_player(2, "player_a")], ["精神:意志力"], "2026-08-20",
    )
    assert other["room"]["id"] != entered["room"]["id"]


def test_session_is_charged_once_and_replay_is_not_charged_again(room_store):
    charges: list[int] = []

    def charge():
        charges.append(1)
        return {"total": 2_500_000.0, "bank": 2_500_000.0, "wallet": 0.0, "transaction_id": "t1"}

    args = ("mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20")
    first = rooms.enter_relationship_training_room(
        *args, client_submission_id="pay-1", session_fee_minor=250_000_000,
        charge=charge, refund=lambda _payment: None,
    )
    again = rooms.enter_relationship_training_room(
        *args, client_submission_id="pay-1", session_fee_minor=250_000_000,
        charge=charge, refund=lambda _payment: None,
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
        charge=charge, refund=lambda _payment: None,
    )
    assert late["replayed"] is True and len(charges) == 1


def test_charged_session_requires_a_submission_id(room_store):
    with pytest.raises(ValueError, match="刷新页面"):
        rooms.enter_relationship_training_room(
            "mind_room", [_player(1, "player_a")], ["精神:意志力"], "2026-08-20",
            charge=lambda: {"total": 1.0}, refund=lambda _payment: None,
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
            charge=lambda: charges.append(1) or {"total": 1.0},
            refund=lambda _payment: None,
        )
    assert charges == []


def test_failed_entry_after_charge_is_refunded(room_store):
    refunds = []
    payment = {"total": 2_500_000.0, "bank": 2_500_000.0, "wallet": 0.0}
    with pytest.raises(ValueError, match="至少选择一项训练属性"):
        rooms.enter_relationship_training_room(
            "mind_room", [_player(1, "player_a")], ["not-in-scope"], "2026-08-20",
            client_submission_id="refund-1",
            charge=lambda: dict(payment), refund=refunds.append,
        )
    assert refunds == [payment]
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
            client_submission_id="double-click", charge=charge,
            refund=lambda _payment: None,
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
