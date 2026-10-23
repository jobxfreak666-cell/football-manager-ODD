"""Team training: the fourth training-ground module that replaced the 8F floor.

The old 8F relationship-training floor (floor tab, room unlock, room instances,
rename dialog) is gone. Its five rooms are the "team_training" module: no
unlock, one paid session per room, a training target and a settlement day.
These tests run the real module helpers from ``src/web/app.js`` in Node with
stubbed data sources and check what the player sees and what is sent.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src"


def raw(name: str) -> str:
    # Shipped source as-is; this file is on conftest's legacy projection list.
    with open(ROOT / "web" / name, encoding="utf-8") as handle:
        return handle.read()


APP_JS = raw("app.js")
APP_CSS = raw("app.css")
INDEX_HTML = raw("index.html")


def extract(start: str, end: str) -> str:
    assert APP_JS.count(start) == 1, start
    return start + APP_JS.split(start, 1)[1].split(end, 1)[0] + "\n"


TEAM = extract("function teamTrainingRooms() {", "async function loadTrainingPreferredMoves(")
ROLE_LABEL = extract("function relationshipTrainingRoleLabel(role) {", "function relationshipTrainingManagedPeople(")

ROOMS = [
    {"sku": "mind_room", "icon": "heart-handshake", "session_fee_minor": 250000000,
     "roles": [{"key": "player_a", "kind": "player", "min": 1, "max": 1}, {"key": "player_b", "kind": "player", "min": 0, "max": 1}],
     "scope_attributes": [{"key": "hidden:适应性", "direction": "inc"}, {"key": "hidden:争论", "direction": "dec"}],
     "eligible_staff_ids": {}, "active": None},
    {"sku": "tactical_room", "icon": "clipboard-list", "session_fee_minor": 750000000,
     "roles": [{"key": "coach", "kind": "staff", "min": 1, "max": 1}, {"key": "player", "kind": "player", "min": 1, "max": 3}],
     "scope_attributes": [{"key": "hidden:雄心", "direction": "inc"}, {"key": "精神:团队合作", "direction": "inc"}],
     "eligible_staff_ids": {"coach": [101]}, "active": None},
]
ACTIVE = {
    "room_id": "room-7", "status": "occupied", "started_on": "2026-10-20", "settle_on": "2026-10-30",
    "days_used": 2, "remaining_days": 8, "fee_minor": 750000000, "attributes": ["hidden:雄心"], "target": "16",
    "participants": [
        {"id": 101, "kind": "staff", "role": "coach", "name": "Arne Slot", "estimated_days": 10, "remaining_days": 8, "settle_on": "2026-10-30"},
        {"id": 1, "kind": "player", "role": "player", "name": "Alexis", "estimated_days": 8, "remaining_days": 6, "settle_on": "2026-10-28"},
    ],
}


def run(script: str, rooms=None) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required")
    source = f"""
const assert = require("node:assert/strict");
const T = {{
  "training.team.per_session":"每次 {{amount}}", "training.team.row_active":"{{date}} 结算",
  "training.team.settle_value":"{{date}}（{{days}} 天后）", "training.team.settle_pending":"选好人员后显示",
  "training.team.target_value":"{{label}}（{{days}} 天 · {{date}} 结算）", "training.until_next":"直到下一点",
  "training.until_value":"直到{{target}}", "training.team.person_days":"还需 {{days}} 天 · {{date}}",
  "training.team.latest_mark":"最长", "training.team.started_on":"{{date}} 开始",
}};
const uiText = (key, params = {{}}) => String(T[key] ?? key).replace(/\\{{(\\w+)\\}}/g, (m, k) => (k in params ? String(params[k]) : m));
const uiPlural = (key, count) => `${{key}}:${{count}}`;
const uiLegacy = (v) => String(v ?? "");
const activeUiLocale = () => "zh-CN";
const escapeHtml = (v) => String(v).replace(/[&<>"]/g, (c) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}})[c]);
const localizedTrainingAttribute = (key) => String(key).split(":").pop();
const trainingFeeLabel = (minor) => `£${{Number(minor) / 100}}`;
const trainingPersonRoleLabel = (kind, person) => kind === "staff" ? "Coach" : "MC";
const formatPounds = (v) => `£${{v}}`;
const clientSubmissionId = (() => {{ let n = 0; return () => `sub-${{++n}}`; }})();
const nodes = {{"#training-roster":{{dataset:{{}}, innerHTML:""}}, "#training-dock-content":{{dataset:{{}}, innerHTML:""}}, "#training-settle-button":null}};
const $ = (selector) => nodes[selector];
const toasts = []; const toast = (m) => toasts.push(m);
const requests = []; let respond = () => ({{}});
const request = async (path, options = {{}}) => {{ requests.push({{path, body:JSON.parse(options.body || "{{}}"), options}}); return respond(path, options); }};
const fmoddConfirm = async () => true;
const applyEconomySnapshot = () => {{}};
const renderIcons = () => {{}};
let renders = 0; const renderTraining = () => {{ renders += 1; }};
const trainingScopeKey = () => "scope";
const trainingCurrentTeamId = () => 1;
const PLAYERS = [{{id:1,name:"Alexis",age:24,ca:150,training_team_id:1}},{{id:2,name:"Curtis",age:23,ca:130,training_team_id:1}}];
const STAFF = [{{id:101,name:"Arne Slot",training_team_id:1,training_subject_type:"staff"}},{{id:102,name:"Kit",training_team_id:1,training_subject_type:"staff"}}];
const trainingFirstTeamPlayers = () => PLAYERS;
const trainingCurrentStaff = () => STAFF;
const app = {{state:{{training_ground:{{team_rooms:{json.dumps(rooms if rooms is not None else ROOMS, ensure_ascii=False)}}}}}, page:"training", trainingModule:"team_training",
  teamTrainingAttributes:new Set(), teamTrainingSelections:{{}}, teamTrainingTarget:"until_increase", teamTrainingPreviewSeq:0}};
const trainingData = () => app.state.training_ground;
const TEAM_TRAINING_TARGETS = ["until_increase", "14", "16", "18", "20"];
{ROLE_LABEL}
{TEAM}
(async () => {{
{script}
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
    result = subprocess.run([node, "-"], input=source, text=True, encoding="utf-8", capture_output=True, timeout=40)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_room_list_shows_session_fee_or_settle_date_without_unlock() -> None:
    rooms = json.loads(json.dumps(ROOMS))
    rooms[1]["active"] = ACTIVE
    run(r'''
renderTeamTrainingRoster();
const html = nodes["#training-roster"].innerHTML;
assert.match(html, /data-team-room="mind_room"/);
assert.match(html, /每次 £2500000/);
assert.match(html, /10-30 结算/);
assert.doesNotMatch(html, /unlock|floor|8F/i);
''', rooms)


def test_settlement_day_waits_for_people_and_blocked_targets_are_disabled() -> None:
    run(r'''
app.teamTrainingRoomSku = "tactical_room";
renderTeamTrainingDetail();
let html = nodes["#training-dock-content"].innerHTML;
assert.match(html, /选好人员后显示/);
assert.equal(requests.length, 0);
assert.doesNotMatch(html, /预估/);
assert.match(html, /id="team-training-submit" type="submit" disabled/);
// Only staff listed by the backend are offered for the coach role.
assert.match(html, /value="101"/);
assert.doesNotMatch(html, /value="102"/);
respond = () => ({target_options:{until_increase:{days:3,settle_on:"2026-10-25"},"14":{days:9,settle_on:"2026-10-31"},"16":null,"18":null,"20":null}, negative:false});
app.teamTrainingSelections.coach = [101];
app.teamTrainingSelections.player = [1];
renderTeamTrainingDetail();
await new Promise((resolve) => setImmediate(resolve));
assert.equal(requests[0].path, "/api/training/relationship-rooms/preview");
assert.deepEqual(requests[0].body.participants, [{role:"coach",kind:"staff",id:101,team_id:1},{role:"player",kind:"player",id:1,team_id:1}]);
assert.equal(requests[0].body.room_sku, "tactical_room");
assert.equal(requests[0].options.__backgroundRead, true);
renderTeamTrainingDetail();
html = nodes["#training-dock-content"].innerHTML;
assert.match(html, /2026-10-25（3 天后）/);
assert.match(html, /直到14（9 天 · 10-31 结算）/);
assert.match(html, /<option value="16"  disabled>/);
assert.doesNotMatch(html, /id="team-training-submit" type="submit" disabled/);
''')


def test_enter_sends_target_and_reuses_submission_id_on_retry() -> None:
    run(r'''
app.teamTrainingRoomSku = "mind_room";
renderTeamTrainingDetail();
app.teamTrainingSelections.player_a = [1];
app.teamTrainingTarget = "14";
let fail = true;
respond = (path) => {
  if (path.endsWith("/enter")) {
    if (fail) { fail = false; const error = new Error("timeout"); error.code = "REQUEST_TIMEOUT"; throw error; }
    return {replayed:true, team_rooms:[{...app.state.training_ground.team_rooms[0], active:{room_id:"r1", settle_on:"2026-11-02", participants:[]}}, ...app.state.training_ground.team_rooms.slice(1)]};
  }
  return {};
};
await submitTeamTraining();
await submitTeamTraining();
const enters = requests.filter((row) => row.path === "/api/training/relationship-rooms/enter");
assert.equal(enters.length, 2);
assert.equal(enters[0].body.target, "14");
assert.equal(enters[0].body.room_sku, "mind_room");
assert.ok(enters[0].body.client_submission_id);
assert.equal(enters[1].body.client_submission_id, enters[0].body.client_submission_id);
assert.equal(toasts.at(-1), "training.duplicate_confirmed");
assert.equal(app.state.training_ground.team_rooms[0].active.room_id, "r1");
''')


def test_active_room_is_read_only_lists_each_person_and_marks_the_longest() -> None:
    rooms = json.loads(json.dumps(ROOMS))
    rooms[1]["active"] = ACTIVE
    run(r'''
app.teamTrainingRoomSku = "tactical_room";
renderTeamTrainingDetail();
const html = nodes["#training-dock-content"].innerHTML;
assert.match(html, /2026-10-20 开始/);
assert.match(html, /<strong>2026-10-30<\/strong>/);
assert.match(html, /还需 8 天 · 10-30<b>最长<\/b>/);
assert.match(html, /还需 6 天 · 10-28<\/em>/);
assert.doesNotMatch(html, /<form|<select|type="checkbox"/);
''', rooms)


def test_manual_settle_uses_the_active_room_id() -> None:
    rooms = json.loads(json.dumps(ROOMS))
    rooms[1]["active"] = ACTIVE
    run(r'''
respond = () => ({settlement:{attribute_changes:[1], relationship_changes:[], early_settlement:{reason:"participant_left_team", skipped_participants:[{id:1,name:"Alexis"}]}}, team_rooms:app.state.training_ground.team_rooms.map((room) => ({...room, active:null}))});
await settleTeamTrainingRoom(app.state.training_ground.team_rooms[1]);
assert.equal(requests[0].path, "/api/training/relationship-rooms/settle");
assert.deepEqual(requests[0].body, {room_id:"room-7"});
assert.equal(app.state.training_ground.team_rooms[1].active, null);
assert.equal(toasts.at(-1), "relationship.room.settle_done");
''', rooms)


def test_header_settle_button_routes_active_team_rooms_and_sync_errors_surface() -> None:
    assert "if (teamRoom?.active) { settleTeamTrainingRoom(teamRoom); return; }" in APP_JS
    assert "...(settlement.team_training?.errors || [])," in APP_JS
    assert "voided_room_ids" not in APP_JS


def test_floor_code_is_removed_but_building_images_stay() -> None:
    for gone in (
        "renderRelationshipTrainingFloor", "unlockRelationshipTrainingRoom", "enterRelationshipTrainingRoom",
        "relationship-rooms/unlock", "TRAINING_FLOOR_LABEL_KEYS", "relationship_8f", "trainingScene",
        "training-room-rename", "data-relationship-room",
    ):
        assert gone not in APP_JS, gone
    assert "relationship_8f" not in APP_CSS
    assert "training-floor" not in APP_CSS
    assert "training-room-rename-dialog" not in INDEX_HTML
    for image in ("outdoor.webp", "outdoor_2.webp", "office_3f.webp", "office_4f.webp", "indoor.webp", "comprehensive_7f.webp"):
        assert (ROOT / "web" / "assets" / "training" / image).is_file(), image


def test_each_module_has_its_own_background() -> None:
    assert "stage.dataset.module = app.trainingModule;" in APP_JS
    for module, image in (
        ("player_training", "outdoor.webp"), ("position_training", "outdoor_2.webp"),
        ("staff_training", "office_3f.webp"), ("team_training", "office_4f.webp"),
    ):
        assert f'.training-stage[data-module="{module}"]' in APP_CSS
        assert f"url('/assets/training/{image}')" in APP_CSS
