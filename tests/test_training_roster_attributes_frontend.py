"""Training roster: clicking a player shows their attributes; clicking staff shows only the coaching licence."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from frontend_source import read_frontend_source

WEB = Path(__file__).resolve().parents[1] / "src" / "web"
APP_JS = read_frontend_source(WEB / "app.js", mode="raw")
I18N_ENUMS = (WEB / "i18n.enums.js").read_text(encoding="utf-8")


def extract(start: str, end: str) -> str:
    assert APP_JS.count(start) == 1, start
    return start + APP_JS.split(start, 1)[1].split(end, 1)[0] + "\n"


LOCALIZE = extract("function localizedTrainingAttribute(attributeKey) {", "function creditDefaultEffects(")
ROSTER = extract("function trainingAttributeValueClass(value) {", "function renderTrainingPersonDetail()")
OPEN_PERSON = extract("function openTrainingPerson(kind, personId) {", "function renderTrainingModuleTabs()")
DETAIL = extract("function renderTrainingPersonDetail() {", "function teamTrainingRooms()")
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
const app = {{ trainingModule: "player_training", trainingPersonKind: null, trainingPersonId: null, trainingPlayerSearch: "", showHiddenAttributes: false }};
const roster = {{ dataset: {{}}, innerHTML: "" }};
const detail = {{ dataset: {{}}, innerHTML: "" }};
const $ = (selector) => selector === "#training-dock-content" ? detail : roster;
const trainingRoster = () => PLAYERS;
const trainingFirstTeamPlayers = () => PLAYERS;
const trainingCurrentStaff = () => PLAYERS;
const filteredTrainingRoster = (kind, people) => people;
const trainingPersonFocus = () => null;
const trainingFocusKey = () => "";
const trainingStaffEligible = () => true;
const trainingPersonRoleLabel = () => "";
const trainingFocusUsage = () => "";
{ROSTER}
{OPEN_PERSON}
{DETAIL}
const renderTraining = () => renderTrainingRoster();
{script}
"""
    result = subprocess.run([node, "-"], input=source, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def rows_after_clicking(person_id, locale="zh-CN", kind="player", module="player_training", show_hidden=True):
    out = run(locale, f"""
app.showHiddenAttributes = {json.dumps(show_hidden)};
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
    def test_clicking_the_same_player_or_staff_twice_collapses_the_row(self):
        for kind, module, person_id, people in (
            ("player", "player_training", 1, PLAYERS),
            ("staff", "staff_training", 101, STAFF),
        ):
            with self.subTest(kind=kind):
                out = run("zh-CN", f"""
app.trainingModule = {json.dumps(module)};
PLAYERS.splice(0, PLAYERS.length, ...{json.dumps(people, ensure_ascii=False)});
openTrainingPerson({json.dumps(kind)}, {person_id});
const firstClick = roster.innerHTML;
openTrainingPerson({json.dumps(kind)}, {person_id});
const secondClick = roster.innerHTML;
renderTrainingPersonDetail();
console.log(JSON.stringify([firstClick, secondClick, detail.innerHTML, app.trainingPersonKind, app.trainingPersonId]));
""")
                opened, closed, empty_detail, selected_kind, selected_id = json.loads(out)
                self.assertIn('aria-expanded="true"', opened)
                self.assertIn("training-person-attributes", opened)
                self.assertNotIn('aria-expanded="true"', closed)
                self.assertNotIn("training-person-attributes", closed)
                self.assertIn("training-detail-empty", empty_detail)
                self.assertIn("training.select_person", empty_detail)
                self.assertIsNone(selected_kind)
                self.assertIsNone(selected_id)

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


    def test_staff_licence_name_follows_ui_language_by_code(self):
        row = staff_rows_after_clicking(104)[3]
        self.assertIn("<b>training.licence.national_b</b>", row)
        self.assertIn("training.next_license</span><b>training.licence.national_a</b>", row)
        self.assertNotIn("国家", row)

    def test_hidden_attributes_stay_hidden_when_setting_is_off(self):
        row = rows_after_clicking(1, show_hidden=False)[0]
        self.assertIn("training-person-attributes", row)
        self.assertNotIn("<h4>隐藏</h4>", row)
        self.assertNotIn("hidden-group", row)
        for hidden in ("争议性", "左脚", "右脚", "受伤倾向"):
            self.assertNotIn(hidden, row)
        self.assertIn("传球<b>16</b>", row)

    def test_hidden_attributes_show_when_setting_is_on(self):
        row = rows_after_clicking(1, show_hidden=True)[0]
        self.assertIn("<h4>隐藏</h4>", row)
        self.assertIn("受伤倾向<b>7</b>", row)

    def test_turning_setting_off_refreshes_the_open_row(self):
        out = run("zh-CN", """
app.trainingPersonKind = "player";
app.trainingPersonId = 1;
app.showHiddenAttributes = true;
renderTrainingRoster();
const on = roster.innerHTML;
app.showHiddenAttributes = false;
renderTrainingRoster();
console.log(JSON.stringify([on, roster.innerHTML]))
""")
        on, off = json.loads(out)
        self.assertIn("受伤倾向", on)
        self.assertNotIn("受伤倾向", off)
        self.assertNotIn("hidden-group", off)

    def test_hidden_attribute_cells_use_neutral_tone(self):
        out = run("zh-CN", """
app.trainingPersonKind = "player";
app.trainingPersonId = 1;
app.showHiddenAttributes = true;
PLAYERS[0].hidden_attributes = {"受伤倾向": 20, "争论": 3, "左脚": 16};
renderTrainingRoster();
console.log(JSON.stringify(roster.innerHTML.split('<article').slice(1)));
""")
        row = json.loads(out)[0]
        hidden = row.split('hidden-group', 1)[1]
        self.assertIn('value-normal">受伤倾向<b>20</b>', hidden)
        self.assertIn('value-normal">争议性<b>3</b>', hidden)
        self.assertIn('value-normal">左脚<b>16</b>', hidden)
        for tone in ("value-elite", "value-good", "value-weak"):
            self.assertNotIn(tone, hidden)
        # Visible attributes keep their colour scale.
        self.assertIn('value-elite">传球<b>16</b>', row)


if __name__ == "__main__":
    unittest.main()
