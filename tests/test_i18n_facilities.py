from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from tools.training_ground import FACILITIES


ROOT = (Path(__file__).resolve().parents[1] / "src")


def facilities_probe() -> dict[str, object]:
    probe = r'''
const fs = require("fs");
const vm = require("vm");
const root = process.argv[1];
const context = {window:{FMODDI18nModules:[]}, document:{documentElement:{dataset:{}}, querySelector:()=>null, dispatchEvent:()=>{}}, NodeFilter:{SHOW_TEXT:4}, CustomEvent:class CustomEvent {}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(root + "/web/i18n.facilities.js", "utf8"), context);
const module = context.window.FMODDI18nModules[0];
vm.runInContext(fs.readFileSync(root + "/web/i18n.js", "utf8"), context);
const i18n = context.window.FMODDI18n;
const keys = Object.fromEntries(Object.entries(module.messages).map(([locale, catalog]) => [locale, Object.keys(catalog).sort()]));
i18n.setLocale("en-GB", {persist:false, root:null});
const english = [i18n.t("canteen.ban_all_confirm", {count:4}), i18n.tp("canteen.people", 2), i18n.translateLegacy("解锁建设")];
i18n.setLocale("zh-CN", {persist:false, root:null});
const chinese = [i18n.t("canteen.ban_all_confirm", {count:4}), i18n.tp("canteen.people", 2), i18n.translateLegacy("解锁建设")];
console.log(JSON.stringify({keys, messages:module.messages, english, chinese}));
'''
    result = subprocess.run(
        ["node", "-e", probe, str(ROOT)], check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def placeholders(value: str) -> set[str]:
    return set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", value))


def test_facility_view_labels_are_available_in_every_supported_locale() -> None:
    probe = r'''
const fs = require("fs");
const vm = require("vm");
const root = process.argv[1];
const html = fs.readFileSync(root + "/web/index.html", "utf8");
const sources = [...html.matchAll(/<script\s+src="([^"]+)"/g)].map((match) => match[1]);
const context = {window:{FMODDI18nModules:[]}, document:{documentElement:{dataset:{}}, querySelector:()=>null, dispatchEvent:()=>{}}, NodeFilter:{SHOW_TEXT:4}, CustomEvent:class CustomEvent {}};
vm.createContext(context);
for (const source of sources) {
  if (!source.startsWith("/i18n") || source === "/i18n.js") continue;
  vm.runInContext(fs.readFileSync(root + "/web" + source, "utf8"), context, {filename:source});
}
vm.runInContext(fs.readFileSync(root + "/web/i18n.js", "utf8"), context);
const locales = ["en-GB","zh-CN"];
const labels = {};
for (const locale of locales) {
  context.window.FMODDI18n.setLocale(locale, {persist:false, root:null});
  labels[locale] = ["facilities.view.compact"].map((key) => context.window.FMODDI18n.t(key));
}
console.log(JSON.stringify(labels));
'''
    result = subprocess.run(
        ["node", "-e", probe, str(ROOT)], check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    labels = json.loads(result.stdout)
    expected_keys = {"facilities.view.compact"}
    assert set(labels) == {"en-GB", "zh-CN"}
    for locale, values in labels.items():
        assert all(value and value not in expected_keys for value in values), (locale, values)


def test_facilities_catalog_has_locale_and_placeholder_parity() -> None:
    output = facilities_probe()
    keys = output["keys"]
    assert set(keys) == {"en-GB", "zh-CN"}
    assert keys["en-GB"] == keys["zh-CN"]
    for key in keys["en-GB"]:
        variants = [output["messages"][locale][key] for locale in ("en-GB", "zh-CN")]
        assert placeholders(variants[0]) == placeholders(variants[1]), key
    assert output["english"] == [
        "Deny all 4 first-team players access to the canteen for 3 days? Each decision can be revoked.",
        "2 people",
        "Unlock construction",
    ]
    assert output["chinese"] == [
        "是否禁止当前一线队全部 4 名球员在3天内进入球队食堂？可逐人撤销。",
        "2 人",
        "解锁建设",
    ]


def test_counselling_roster_copy_and_unlock_confirmation_are_localised() -> None:
    probe = r'''
const fs = require("fs");
const vm = require("vm");
const root = process.argv[1];
const html = fs.readFileSync(root + "/web/index.html", "utf8");
const sources = [...html.matchAll(/<script\s+src="([^"]+)"/g)].map((match) => match[1]);
const context = {window:{FMODDI18nModules:[]}, document:{documentElement:{dataset:{}}, querySelector:()=>null, dispatchEvent:()=>{}}, NodeFilter:{SHOW_TEXT:4}, CustomEvent:class CustomEvent {}};
vm.createContext(context);
for (const source of sources) {
  if (!source.startsWith("/i18n") || source === "/i18n.js") continue;
  vm.runInContext(fs.readFileSync(root + "/web" + source, "utf8"), context, {filename:source});
}
vm.runInContext(fs.readFileSync(root + "/web/i18n.js", "utf8"), context);
const locales = ["en-GB","zh-CN"];
const messages = {};
for (const locale of locales) {
  context.window.FMODDI18n.setLocale(locale, {persist:false, root:null});
  messages[locale] = {
    description: context.window.FMODDI18n.t("activity.counselling_roster_description"),
    action: context.window.FMODDI18n.t("activity.start_counselling"),
    confirmation: context.window.FMODDI18n.t("activity.confirm_counselling_unlock", {price:"£100K", player:"Alex"}),
  };
}
console.log(JSON.stringify(messages));
'''
    result = subprocess.run(
        ["node", "-e", probe, str(ROOT)], check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    messages = json.loads(result.stdout)
    assert messages["zh-CN"] == {
        "description": "选择有不满的球员进行心理辅导",
        "action": "开始谈话",
        "confirmation": "确认从钱包支付 £100K 为 Alex 进行心理辅导？\n\n这会直接修改 FM 进程内存，请先备份存档。",
    }
    for locale, copy in messages.items():
        assert copy["description"] and copy["description"] != "activity.counselling_roster_description", locale
        assert copy["action"] and copy["action"] != "activity.start_counselling", locale
        assert "£100K" in copy["confirmation"] and "Alex" in copy["confirmation"], locale
        assert "\n\n" in copy["confirmation"], locale  # backup-save reminder paragraph

    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    metadata = script.split("activityMeta.psychological_counseling =", 1)[1].split(";", 1)[0]
    assert 'action:uiText("activity.start_counselling")' in metadata


def test_career_discussion_room_uses_the_requested_name() -> None:
    output = facilities_probe()
    messages = output["messages"]

    assert messages["en-GB"]["activity.node_retirement"] == "Career discussion room"
    assert messages["zh-CN"]["activity.node_retirement"] == "生涯交流室"


def test_black_room_description_uses_the_short_random_injury_copy() -> None:
    output = facilities_probe()
    messages = output["messages"]

    assert messages["en-GB"]["activity.black_room_description"] == "Add a random injury to the player"
    assert messages["zh-CN"]["activity.black_room_description"] == "为球员添加随机伤病"


def test_migrated_facility_renderers_use_semantic_messages_with_bounded_data_allowlist() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    for key in (
        'uiPlural("canteen.people", players.length)',
        'uiText("canteen.banned_remaining", {days:remaining})',
        'uiText("canteen.per_game_day"',
        'uiText("canteen.open", {name:uiText(plan.nameKey)})',
        'uiText("canteen.ban_all_confirm", {count:players.length})',
        'setAttribute("aria-label", uiText("training.modules"))',
        'labelKey:"training.module.player_training"',
        'labelKey:"training.module.position_training"',
        'labelKey:"training.module.staff_training"',
        'uiText(kind === "staff" ? "training.roster.staff_title" : "training.roster.player_title")',
        'uiPlural(kind === "staff" ? "training.roster.staff_count" : "training.roster.player_count", people.length)',
        'uiText("training.roster.loading")',
        'uiText("training.roster_empty")',
        'uiText("training.roster_error")',
        'uiText("training.roster_retry")',
        'uiText("training.select_person")',
        'uiText(module === "staff_training" ? "training.select_staff_hint" : "training.select_player_hint")',
        'uiText("training.project_label")',
        'uiText("training.fee_label")',
        'uiText("training.estimated_time")',
        'uiText("training.current_target_label")',
        'uiText("training.arrange")',
        'uiText("training.active_task")',
        'uiText("training.cancel_task")',
        'uiText("training.reason_active")',
        'uiText("training.staff_ineligible")',
        'uiText("training.reason_no_project")',
        'uiText("training.not_eligible")',
        'uiText("training.idle")',
        'uiText("training.arranged")',
        'uiText("training.arrange_failed")',
        'uiPlural("training.position_roster_count", filteredPlayers.length)',
        'uiText(group.labelKey)',
        'uiText("activity.floor_entertainment_eyebrow")',
        'uiText("activity.floor_talk_room_eyebrow")',
        'uiText("activity.floor_international_eyebrow")',
        'uiText("activity.floor_intelligence_eyebrow")',
    ):
        assert key in script

    for literal in (
        'eyebrow:"PLAYER LOUNGE"',
        'eyebrow:"PRIVATE TALKS"',
        'eyebrow:"MEDIA CENTRE"',
        'eyebrow:"INTERNATIONAL DESK"',
        'eyebrow:"MATCH INTELLIGENCE"',
    ):
        assert literal not in script

    # These migrated renderers may retain only API/user values (names,
    # descriptions, and fixture data) and stable CSS/data attributes. None is
    # a Chinese UI literal, so the explicit allowlist is intentionally empty.
    allowed_game_or_user_data: tuple[str, ...] = ()
    for function in (
        "canteenRosterPanel", "renderHospital", "renderInventory",
        "renderTrainingModuleTabs", "renderTrainingRoster", "renderTrainingPersonDetail",
    ):
        body = re.search(rf"function {function}\([^)]*\) \{{(.*?)(?=\nfunction |\Z)", script, re.S)
        assert body, function
        residual = re.findall(r"[一-龥]+", body.group(1))
        assert residual == list(allowed_game_or_user_data), (function, residual)


def test_training_ground_catalog_and_renderers_use_current_project_semantic_keys() -> None:
    output = facilities_probe()
    expected = {
        f"training.facility.{sku}.{field}"
        for sku in FACILITIES
        for field in ("name", "description")
    }
    assert expected
    for locale in ("en-GB", "zh-CN"):
        assert expected <= set(output["keys"][locale]), locale
        assert all(str(output["messages"][locale][key]).strip() for key in expected), locale

    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    for call in (
        "trainingProjectOptionLabel(row)",
        "trainingProjectName(project)",
        "trainingFacilityName(project?.sku, project || {})",
        "trainingFacilityDescription(project?.sku, project || {})",
        "trainingArchiveFacilityLabel(details.facility_sku,details.facility_name)",
    ):
        assert call in script
    for bypass in (
        "<strong>${escapeHtml(item.name)}</strong>",
        "<small>${escapeHtml(item.description)}</small>",
        "<span>${escapeHtml(product.name || facility.sku)}</span>",
    ):
        assert bypass not in script
    for stale in (
        "training.equipment_shop",
        "training.equipment_storage",
        "training.floor_unlock_confirm",
        "training.buy",
        "training.place",
        "training.sell",
        "training.available_equipment",
        "training.sell_confirm",
        "training.repeat",
    ):
        assert stale not in script, stale
        for locale in ("en-GB", "zh-CN"):
            assert stale not in output["keys"][locale], (locale, stale)


def test_three_module_training_copy_is_bilingual_and_cancel_copy_warns_no_refund() -> None:
    output = facilities_probe()
    messages = output["messages"]
    expected = {
        "training.modules": ("Training modules", "训练模块"),
        "training.module.player_training": ("Player training", "球员训练"),
        "training.module.position_training": ("Position training", "位置训练"),
        "training.module.staff_training": ("Staff training", "职员训练"),
        "training.roster.player_title": ("First-team players", "一线队球员"),
        "training.roster.staff_title": ("Club staff", "球队职员"),
        "training.fee_label": ("Fixed fee", "单次费用"),
        "training.free": ("Free", "免费"),
        "training.cancel_title": ("Cancel training task?", "取消训练任务？"),
        "training.cancel_message": (
            "Cancel this training task? The fee for this task will not be refunded.",
            "取消这次训练任务？取消后不会退还本次训练费用。",
        ),
        "training.cancel_confirm": ("Confirm cancellation", "确认取消"),
        "training.cancel_keep": ("Keep training", "继续训练"),
        "training.active_summary": (
            "{speed} {action} {attribute}{range}{guidance} · {status}",
            "{speed}{action}{attribute}{range}{guidance} · {status}",
        ),
    }
    for key, (english, chinese) in expected.items():
        assert messages["en-GB"][key] == english, key
        assert messages["zh-CN"][key] == chinese, key
    for base in ("training.roster.player_count", "training.roster.staff_count"):
        for suffix in ("one", "other"):
            assert messages["en-GB"][f"{base}.{suffix}"].strip()
            assert messages["zh-CN"][f"{base}.{suffix}"].strip()

    # Cancel confirmation must pass the warning copy first and the keep-training
    # action last; the fee must never be described as refundable.
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert (
        'uiText("training.cancel_message"),\n'
        '    uiText("training.cancel_confirm"),\n'
        '    uiText("training.cancel_title"),\n'
        '    uiText("training.cancel_keep"),'
    ) in script
    assert "will not be refunded" in messages["en-GB"]["training.cancel_message"]
    assert "不会退还" in messages["zh-CN"]["training.cancel_message"]
    assert 'const key = "training.active_summary";' in script
    assert "return trainingFocusSummaryText(speed, action, attribute, attributeRange, guidance, remaining);" in script
