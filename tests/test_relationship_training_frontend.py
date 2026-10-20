from pathlib import Path


ROOT = (Path(__file__).resolve().parents[1] / "src")
APP_JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
APP_CSS = (ROOT / "web" / "app.css").read_text(encoding="utf-8")


def test_development_settlement_requires_explicit_backup_confirmation():
    assert 'data-relationship-room-settle=' in APP_JS
    assert '"/api/training/relationship-rooms/settle"' in APP_JS
    assert "请先备份存档" in APP_JS
    assert "已备份，开始结算" in APP_JS
    assert "app.developerMode" in APP_JS


def test_relationship_room_candidate_rules_are_present_in_frontend():
    for job_type in (1, 16, 2, 34, 22, 26):
        assert str(job_type) in APP_JS
    assert "coaching_license" in APP_JS
    assert "relationshipTrainingGuiderQualified" in APP_JS
    assert "relationshipTrainingAttributeValue" in APP_JS
    assert 'room.sku==="video_analysis_room"?"分析团队":"运动科学团队"' in APP_JS
    assert 'room.sku==="video_analysis_room"?"数据分析":"运动科学"' in APP_JS
    assert 'room?.sku==="sports_science_room" ? Number(a.age||0)-Number(b.age||0)' in APP_JS
    assert "relationshipTrainingPickerOpen" in APP_JS
    assert "relationshipTrainingGuidanceRoles" in APP_JS
    assert 'tactical_room:{guide:"coach",student:"player"}' in APP_JS
    assert 'video_analysis_room:{guide:"analyst",student:"player"}' in APP_JS
    assert 'sports_science_room:{guide:"scientist",student:"player"}' in APP_JS


def test_relationship_floor_reuses_212_room_visual_structure():
    for class_name in (
        "training-room-panel", "training-room-hero", "training-room-section",
        "training-room-card", "training-room-card-head", "training-available-item",
        "room-card-icon", "room-attr-chips",
    ):
        assert class_name in APP_JS
    for class_name in (
        "training-room-chips", "training-player-field", "training-player-menu",
        "training-player-option", "training-player-group",
        "training-room-selected-people", "training-room-person-card",
        "training-room-effect-preview",
    ):
        assert class_name in APP_JS
        assert class_name in APP_CSS


def test_relationship_floor_rendering_survives_without_training_entry():
    # The 8F relationship-room renderer and grouping stay in the source (plan
    # §1.2), but the three-module training ground no longer exposes that floor
    # or its old available/unlock dock. The module-level constants above use the
    # legacy zh-CN projection, so this test reads the shipped source explicitly.
    from frontend_source import raw_web_source

    script = raw_web_source(ROOT / "web" / "app.js")
    index = raw_web_source(ROOT / "web" / "index.html")
    assert "function renderRelationshipTrainingFloor" in script
    assert "function renderRelationshipTrainingAvailablePanel" in script
    assert "renderRelationshipTrainingAvailablePanel(data, allInstances)" in script
    assert "data-relationship-room-detail=" in script
    assert "relationshipTrainingDetail(" in script
    assert '<span>可用房间</span>' not in script
    assert '<span>房间解锁</span>' not in script
    module_block = script.split("const TRAINING_MODULES = [", 1)[1].split("];", 1)[0]
    assert 'key:"player_training"' in module_block
    assert 'key:"position_training"' in module_block
    assert 'key:"staff_training"' in module_block
    assert module_block.count('key:"') == 3
    assert "relationship_8f" not in module_block
    assert "relationship_8f" not in index
    assert "data-training-scene=" not in index
    assert 'data-training-module="relationship_8f"' not in script
    assert 'id="training-dock-tabs"' not in index
    assert 'category("occupied", uiText("relationship.occupied_group")' in script
    assert 'category("idle", uiText("relationship.idle")' in script


def test_relationship_floor_uses_exact_212_building_image():
    asset = ROOT / "web" / "assets" / "training" / "office_4f.webp"
    assert asset.is_file()
    assert asset.stat().st_size == 705097
    assert ".training-stage.relationship_8f { background-image:url('/assets/training/office_4f.webp'); }" in APP_CSS


def test_relationship_floor_keeps_original_image_without_room_overlays():
    renderer = APP_JS.split("function renderRelationshipTrainingFloor", 1)[1].split(
        "async function unlockRelationshipTrainingRoom", 1,
    )[0]
    assert 'stage.querySelector("#training-stage-items").innerHTML = ""' in renderer
    assert "relationship-room-stage" not in renderer


def test_relationship_room_preselection_matches_212_interaction_contract():
    assert "relationshipTrainingSelectionValid" in APP_JS
    assert "relationshipTrainingSelectionCards" in APP_JS
    assert "relationshipTrainingEffectPreview" in APP_JS
    assert "data-relationship-room-picker" in APP_JS
    assert "data-relationship-room-option" in APP_JS
    assert "data-relationship-room-staff-role" not in APP_JS
    assert '"world.editor.ca"' in APP_JS
    assert "staffJobCategory(person)===value" in APP_JS
    assert "data-relationship-room-remove" in APP_JS
    assert "请按每个角色的人数要求选择人员" in APP_JS
    assert "pair.effect_pair === false" in APP_JS
    assert "仅用于负面关系检查" in APP_JS


def test_relationship_room_preview_hides_manager_and_missing_relationship_labels():
    assert 'if (!detail) return "";' in APP_JS
    assert 'if (reason.includes("主教练") || reason.includes("前主教练")) return "";' in APP_JS
    assert "]).filter(Boolean).join(\"\");" in APP_JS


def test_relationship_room_groups_and_attributes_match_212_contract():
    assert '"relationship.training"' in APP_JS
    assert 'app.trainingPlayerGroupState[stateKey] = false' in APP_JS
    assert 'app.trainingPlayerGroupState[subKey] = false' in APP_JS
    assert '"relationship.room.positive_attributes"' in APP_JS
    assert '"relationship.room.negative_attributes"' in APP_JS
    assert "training-active-detail" in APP_JS


def test_relationship_floor_removes_all_right_stage_dimming():
    assert ".training-stage.relationship_8f::after { display:none; }" in APP_CSS
