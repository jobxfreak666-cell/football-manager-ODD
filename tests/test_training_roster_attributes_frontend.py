"""Training roster: clicking a player shows their attributes; clicking staff shows only the coaching licence."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "web"
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")
I18N_ENUMS = (WEB / "i18n.enums.js").read_text(encoding="utf-8")


def extract(start: str, end: str) -> str:
    assert APP_JS.count(start) == 1, start
    return start + APP_JS.split(start, 1)[1].split(end, 1)[0] + "\n"


LOCALIZE = extract("function localizedTrainingAttribute(attributeKey) {", "function creditDefaultEffects(")
ROSTER = extract("function trainingAttributeValueClass(value) {", "function renderTrainingPersonDetail()")
LICENCE = extract("const COACHING_LICENSE_NAMES = {", "const COACHING_STAFF_JOB_TYPES")

PLAYERS = [
    {"id": 1, "name": "Outfield", "shirt_number": 11,
     "attributes": {"定位球": {"角球": 10}, "技术": {"传球": 16, "盯人": 5}, "精神": {"才华": 12}, "身体": {"速度": 9}},
     "hidden_attributes": {"争论": 17, "左脚": 20, "右脚": 9, "受伤倾向": 7}},
    {"id": 2, "name": "Keeper", "shirt_number": 1,
     "attributes": {"技术训练": {"任意球": 4}, "门将": {"一对一": 17, "意外性": 4}, "精神": {}, "身体": {"弹跳": 13}},
     "hidden_attributes": {}},
    {"id": 3, "name": "Unknown", "shirt_number": 9, "attributes": {}, "hidden_attributes": {}},
]


def run(locale: str, script: str) -> str:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required")
    source = f"""
const window = {{ FMODDI18nModules: [] }};
const document = {{ documentElement: {{ lang: {json.dumps(locale)} }} }};
{I18N_ENUMS}
const messages = Object.assign({{}}, ...window.FMODDI18nModules.map((m) => m.messages?.[{json.dumps(locale)}] || {{}}));
const uiText = (key) => messages[key] ?? key;
const uiLegacy = (text) => text;
const uiPlural = (key, n) => `${{n}}`;
const escapeHtml = (v) => String(v).replace(/[&<>"]/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}})[c]);
{LOCALIZE}
{LICENCE}
const PLAYERS = {json.dumps(PLAYERS, ensure_ascii=False)};
const app = {{ trainingModule: "player_training", trainingPersonKind: null, trainingPersonId: null, trainingPlayerSearch: "" }};
const roster = {{ dataset: {{}}, innerHTML: "" }};
const $ = () => roster;
const trainingRoster = () => PLAYERS;
const filteredTrainingRoster = (kind, people) => people;
const trainingPersonFocus = () => null;
const trainingFocusKey = () => "";
const trainingStaffEligible = () => true;
const trainingPersonRoleLabel = () => "";
const trainingFocusUsage = () => "";
{ROSTER}
{script}
"""
    result = subprocess.run([node, "-"], input=source, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def rows_after_clicking(person_id, locale="zh-CN", kind="player", module="player_training"):
    out = run(locale, f"""
app.trainingModule = {json.dumps(module)};
app.trainingPersonKind = {json.dumps(kind)};
app.trainingPersonId = {json.dumps(person_id)};
renderTrainingRoster();
console.log(JSON.stringify(roster.innerHTML.split('<article').slice(1)));
""")
    return json.loads(out)


STAFF = [
    {"id": 101, "name": "Coach B", "coaching_license": {"name": "National B", "next_name": "National A", "maximum": False}},
    {"id": 102, "name": "Coach Pro", "coaching_license": {"name": "Continental Pro", "next_name": None, "maximum": True}},
    {"id": 103, "name": "Coach Unread"},
    {"id": 104, "name": "Coach Coded", "coaching_license": {"code": 6, "name": "国家 B 级", "next_code": 5, "next_name": "国家 A 级", "maximum": False}},
]


def staff_rows_after_clicking(person_id, locale="zh-CN"):
    out = run(locale, f"""
app.trainingModule = "staff_training";
app.trainingPersonKind = "staff";
app.trainingPersonId = {json.dumps(person_id)};
PLAYERS.splice(0, PLAYERS.length, ...{json.dumps(STAFF, ensure_ascii=False)});
renderTrainingRoster();
console.log(JSON.stringify(roster.innerHTML.split('<article').slice(1)));
""")
    return json.loads(out)


class TrainingRosterAttributesTest(unittest.TestCase):
    def test_only_the_clicked_player_expands(self):
        rows = rows_after_clicking(1)
        self.assertIn("training-person-attributes", rows[0])
        self.assertIn('aria-expanded="true"', rows[0])
        self.assertIn("chevron-down", rows[0])
        for other in rows[1:]:
            self.assertNotIn("training-person-attributes", other)
            self.assertIn('aria-expanded="false"', other)

    def test_nothing_expands_before_a_click(self):
        rows = rows_after_clicking(None, kind=None)
        self.assertFalse(any("training-person-attributes" in row for row in rows))

    def test_outfield_groups_values_and_hidden_attributes(self):
        row = rows_after_clicking(1)[0]
        headings = [part.split("</h4>")[0] for part in row.split("<h4>")[1:]]
        self.assertEqual(headings, ["技术", "精神", "身体", "定位球", "隐藏"])
        self.assertIn('value-elite">传球<b>16</b>', row)
        self.assertIn('value-weak">盯人<b>5</b>', row)
        self.assertIn('value-normal">速度<b>9</b>', row)
        self.assertIn("争议性<b>17</b>", row)
        self.assertNotIn("争论", row)

    def test_goalkeeper_groups(self):
        row = rows_after_clicking(2)[1]
        headings = [part.split("</h4>")[0] for part in row.split("<h4>")[1:]]
        self.assertEqual(headings, ["门将", "身体", "门将技术"])

    def test_player_without_attributes_shows_empty_state(self):
        row = rows_after_clicking(3)[2]
        self.assertIn("training-person-attributes empty", row)
        self.assertNotIn("<h4>", row)

    def test_english_labels_for_previously_untranslated_attributes(self):
        rows = rows_after_clicking(1, locale="en-GB")
        rows += rows_after_clicking(2, locale="en-GB")
        text = "".join(rows)
        for label in ["Left Foot", "Right Foot", "Injury Proneness", "One on Ones", "Eccentricity", "Hidden", "Controversy"]:
            self.assertIn(label, text)
        for chinese in ["左脚", "右脚", "受伤倾向", "一对一", "意外性"]:
            self.assertNotIn(chinese, text)

    def test_staff_row_expands_to_coaching_licence_only(self):
        rows = staff_rows_after_clicking(101)
        self.assertIn("training-staff-licence", rows[0])
        self.assertIn('aria-expanded="true"', rows[0])
        self.assertIn("<h4>training.current_licence</h4>", rows[0])
        self.assertIn("<b>National B</b>", rows[0])
        self.assertIn("training.next_license</span><b>National A</b>", rows[0])
        # Staff never show the 21 abilities or hidden attributes.
        self.assertNotIn("ability-list", rows[0])
        self.assertNotIn("player-attribute-sections", rows[0])
        for other in rows[1:]:
            self.assertNotIn("training-person-attributes", other)

    def test_staff_licence_at_top_level_and_unread(self):
        top = staff_rows_after_clicking(102)[1]
        self.assertIn('class="licence-max">training.no_next_licence', top)
        self.assertNotIn("training.next_license", top)
        unread = staff_rows_after_clicking(103)[2]
        self.assertIn("<b>training.licence_unread</b>", unread)
        self.assertNotIn("training.no_next_licence", unread)


if __name__ == "__main__":
    unittest.main()

    def test_staff_licence_name_follows_ui_language_by_code(self):
        row = staff_rows_after_clicking(104)[3]
        self.assertIn("<b>training.licence.national_b</b>", row)
        self.assertIn("training.next_license</span><b>training.licence.national_a</b>", row)
        self.assertNotIn("国家", row)
