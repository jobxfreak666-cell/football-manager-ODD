from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tools.club_reader import STAFF_JOB_TYPES
from tools.club_vision import BOARD_IMPORTANCE_OPTIONS, CLUB_VISION_TYPE_NAMES
from tools.initial_data_audit import NATION_NAMES
from tools.preferred_moves import FM24_VERIFIED_PREFERRED_MOVES
from tools.training_ground import FACILITIES


ROOT = Path(__file__).resolve().parents[1] / "src"
LOCALES = ("en-GB", "zh-CN")


def _enum_probe() -> dict[str, object]:
    script = r'''
const fs = require("fs"), vm = require("vm"), root = process.argv[1];
const context = {window:{FMODDI18nModules:[]},document:{documentElement:{dataset:{}},querySelector:()=>null,dispatchEvent:()=>{}},NodeFilter:{SHOW_TEXT:4},CustomEvent:class CustomEvent {}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(root + "/web/i18n.enums.js", "utf8"), context);
const modules = context.window.FMODDI18nModules.map(module => module.messages);
const result = {
  modules,
  sourceKeys:context.window.FMODDTrainingAttributeSourceKeys,
  groupSourceKeys:context.window.FMODDTrainingAttributeGroupSourceKeys,
};
vm.runInContext(fs.readFileSync(root + "/web/i18n.js", "utf8"), context);
const i18n = context.window.FMODDI18n;
result.rendered = {};
for (const locale of ["en-GB", "zh-CN"]) {
  i18n.setLocale(locale, {persist:false,root:null});
  result.rendered[locale] = [
    i18n.t("staff.job.64"),
    i18n.t("nation.name.1651"),
    i18n.t("training.attribute.pace"),
    i18n.t("club.nature.1"),
    i18n.t("stadium.state.1"),
  ];
}
console.log(JSON.stringify(result));
'''
    result = subprocess.run(
        ["node", "-e", script, str(ROOT)], check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def _validate_bilingual_catalogs(modules: list[dict[str, dict[str, str]]]) -> None:
    for module in modules:
        assert set(module) == set(LOCALES)
        assert set(module["en-GB"]) == set(module["zh-CN"])
        assert all(value.strip() for catalog in module.values() for value in catalog.values())


def test_dynamic_enum_domains_have_complete_bilingual_stable_id_coverage() -> None:
    output = _enum_probe()
    modules = output["modules"]
    assert len(modules) == 6
    _validate_bilingual_catalogs(modules)

    enum_keys = set(modules[0]["en-GB"])
    expected_enum_keys = {
        *(f"staff.job.{value}" for value in STAFF_JOB_TYPES),
        *(f"training.preferred_move.{value}" for value in FM24_VERIFIED_PREFERRED_MOVES),
        *(f"owned.vision.target.{value}" for value in CLUB_VISION_TYPE_NAMES),
        *(f"owned.vision.importance.{value}" for value, _label in BOARD_IMPORTANCE_OPTIONS),
        *(f"owned.vision.category.{value}" for value in (
            "competition", "finance", "reputation", "recruitment", "youth",
            "style", "stadium", "other",
        )),
    }
    assert enum_keys == expected_enum_keys

    nation_keys = {
        *(f"nation.name.{identifier}" for identifier in NATION_NAMES),
        *(f"continent.name.{value}" for value in (
            "africa", "asia", "europe", "north_america", "south_america",
            "oceania", "other",
        )),
    }
    assert set(modules[1]["en-GB"]) == nation_keys

    source_keys = output["sourceKeys"]
    expected_sources = {
        key.split(":", 1)[-1]
        for facility in FACILITIES.values()
        for key in facility.get("attributes", [])
    }
    assert set(source_keys) == expected_sources
    assert set(modules[2]["en-GB"]) == {
        *source_keys.values(), *output["groupSourceKeys"].values(),
    }

    assert set(modules[3]["en-GB"]) == {
        *(f"relationship.event.role.{value}" for value in (
            "mentor", "coach", "analyst", "scientist", "student", "player",
            "player_a", "player_b", "manager", "activity_target", "counselor",
            "counselee", "trainee",
        )),
        *(f"relationship.event.outcome.{value}" for value in (
            "unlocked", "relieved", "opened_up", "no_effect", "rupture",
        )),
        *(f"relationship.event.source.{value}" for value in (
            "counselling", "staff_drinks", "staff_hot_spring",
            "staff_football_game", "staff_massage",
        )),
    }
    assert set(modules[4]["en-GB"]) == {
        f"home.connection.{value}" for value in (
            "connecting", "connected", "retained", "managed_team_missing",
            "manager_missing", "read_failed", "game_detected", "offline",
        )
    }
    assert set(modules[5]["en-GB"]) == {
        *(f"club.nature.{code}" for code in (1, 2, 3)),
        *(f"stadium.state.{code}" for code in (1, 2, 6, 11, 16)),
        *(f"stadium.pitch_type.{code}" for code in range(1, 9)),
    }


def test_dynamic_enum_copy_renders_in_both_supported_languages() -> None:
    assert _enum_probe()["rendered"] == {
        "en-GB": [
            "Head of Youth Development", "Brazil", "Pace", "Professional", "Very good",
        ],
        "zh-CN": ["青训主管", "巴西", "速度", "职业", "非常好"],
    }


def _club_nation_renderer_probe() -> dict[str, str]:
    script = r'''
const fs = require("fs"), vm = require("vm"), root = process.argv[1];
const appSource = fs.readFileSync(root + "/web/app.js", "utf8");
const helper = appSource.slice(appSource.indexOf("function localizedNationName"), appSource.indexOf("function localizedContinentName"));
const labels = {"nation.name.765":"England","nation.name.1651":"People's Republic of China","world.not_read":"Not read","world.unnamed_nation":"Unnamed nation"};
const context = {window:{FMODDNationSourceIds:{"英格兰":765,"中国":1651}},uiText:key=>labels[key]||key,activeUiLocale:()=>"en-GB"};
vm.createContext(context);
vm.runInContext(helper, context);
console.log(JSON.stringify({
  pending:vm.runInContext('localizedClubNation({nation:"未分类"})', context),
  verified:vm.runInContext('localizedClubNation({nation:"未分类"},{id:1651,name:"中国"})', context),
  indexed:vm.runInContext('localizedClubNation({nation_id:765,nation:"英格兰"})', context),
}));
'''
    result = subprocess.run(
        ["node", "-e", script, str(ROOT)], check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_club_nation_labels_require_a_verified_stable_id() -> None:
    assert _club_nation_renderer_probe() == {
        "pending": "Not read",
        "verified": "People's Republic of China",
        "indexed": "England",
    }


def test_dynamic_renderers_resolve_stable_enum_ids_instead_of_raw_labels() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    for token in (
        'localizedEnumLabel("staff.job", person?.job_type',
        'localizedEnumLabel("owned.vision.target", type',
        'localizedVisionImportance(option.value)',
        'localizedVisionTarget(row)',
        'localizedNationName(nation)',
        'localizedContinentName(row.name)',
        'localizedContinentName(nation.continent)',
        'localizedTrainingAttribute(selectedTargetKey)',
        'localizedTrainingAttributeGroup(group)',
        'localizedClubNature(status)',
        'localizedStadiumState(stadium)',
        'localizedStadiumPitchType(stadium)',
        'localizedClubNation(club, metrics.nation)',
    ):
        assert token in script
    assert '"/i18n.enums.js"' in (ROOT / "web" / "index.html").read_text(encoding="utf-8")
