"""Offline frontend contract tests for the three-module training ground.

These tests execute the real browser-side helpers extracted from
``src/web/app.js`` in an isolated Node process with stubbed data sources. They
cover roster scope, project attribution, person occupancy, fixed fees, submit
payloads, cancellation confirmation, late responses and the retained position
workspace. One test runs ``node --check`` over the real script.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
APP_JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
APP_CSS = (ROOT / "web" / "app.css").read_text(encoding="utf-8")


def extract(start: str, end: str) -> str:
    if APP_JS.count(start) != 1:
        raise AssertionError(f"start marker missing/duplicate: {start[:70]}")
    body = APP_JS.split(start, 1)[1]
    if end not in body:
        raise AssertionError(f"end marker missing: {end[:70]}")
    return start + body.split(end, 1)[0] + "\n"


HELPERS = extract("const TRAINING_MODULES = [", "function managedFixtures() {")
DATA_INDEX = extract("function trainingDataIndex() {", "function trainingProduct(sku)")
POSITION_RUNTIME = extract(
    "function positionTrainingPayload(player, slot, durationMode) {",
    "async function startPositionTrainingAssignments(button)",
) + extract("function positionTrainingRows(state, playersById) {", "function managedFixtures() {")


def run_node(source: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for the isolated frontend harness")
    return subprocess.run(
        [node, "-"], input=source, text=True, encoding="utf-8",
        capture_output=True, timeout=40, check=False,
    )


BASE = r'''
const assert = require("node:assert/strict");
const fixtures = {
  app:{}, output:null, profiles:[], managedPlayers:[], dom:{},
  data:{catalog:[], focuses:[], preferred_moves:[], coaching_license_course_days:{}, player_manager:null},
  rosterCurrent:true, coachingCurrent:true,
};
const app = fixtures.app;
const trainingData = () => fixtures.data;
const output = () => fixtures.output || {
  managed_teams:[{id:1,name:"Current FC",team_type:"club"}],
  selected_manager_id:7, save_instance_id:"save-1",
};
const managedTeams = () => output().managed_teams || [];
const teamProfile = (teamId) => fixtures.profiles.find(
  (profile) => Number(profile.team?.id) === Number(teamId),
) || null;
const clubProfileSquads = (profile) => profile?.squads || [];
const trainingManagedPlayers = () => fixtures.managedPlayers;
const trainingProduct = (sku) => (trainingData().catalog || []).find((row) => row.sku === sku) || null;
const trainingFacilityName = (sku, product = {}) => product.name || sku;
const trainingFacilityDescription = (sku, product = {}) => product.description || "";
const playerAttributeValue = (player, key) => {
  if (!player?.attributes) return 0;
  const [group, name] = String(key).split(":");
  return Number(player.attributes[group]?.[name] || 0);
};
const trainingAttributeKeysForPlayer = (project, player) => (
  (project.attributes || []).filter((key) => playerAttributeValue(player, key) > 0)
);
const trainingPlayerMatchesPositionGroup = (player, group) => (player.group || "defenders") === group;
const trainingDurationTarget = (mode, current, direction = 1) => (
  mode === "until_increase"
    ? Number(current) + Number(direction)
    : Number(String(mode).split("_")[1])
);
const trainingEstimatedDays = (player, key, mode, multiplier = 3, direction = 1) => {
  const current = playerAttributeValue(player, key);
  const target = trainingDurationTarget(mode, current, direction);
  return Math.max(1, Math.ceil(Math.abs(target - current) * 14 / multiplier));
};
const trainingAttributeAffectsCa = (key, product = {}, caCosts = {}) => (
  product.attribute_kind !== "hidden" && caCosts.ca_affected !== false
);
const TRAINING_FIXED_TARGETS = [14,16,18,20];
const TRAINING_REDUCTION_TARGETS = [10,5,1];
const COACHING_STAFF_JOB_TYPES = new Set([2,20,22,26,34,64]);
const uiText = (key, values = {}) => key + (Object.keys(values).length ? "|" + JSON.stringify(values) : "");
const uiPlural = (key, count) => `${key}.${Number(count) === 1 ? "one" : "other"}`;
const escapeHtml = (value) => String(value);
const formatPounds = (value) => `GBP${Number(value)}`;
const activeUiLocale = () => "en-GB";
const localizedStaffRole = (staff) => staff.role || "staff";
const primaryPlayerPosition = (player) => player.primary_positions?.[0] || "";
const playerPositionGroup = (player) => player.group || "defenders";
const localizedTrainingAttribute = (key) => key;
const localizedPreferredMove = (move) => move.name || move.preferred_move_name || "";
let requestCalls = [];
let toasts = [];
let confirms = [];
let rendered = 0;
let updated = 0;
let requestImpl = async () => ({training_ground:{}, economy:{}, payment:{total:0}, focus:{}, duplicate:false});
let confirmImpl = async () => true;
let ensureDevelopmentRosterImpl = async () => true;
let ensureCoachingRosterImpl = async () => true;
let ensureRosterImpl = async () => true;
const request = async (path, options = {}) => {
  requestCalls.push({path, options, body:options.body ? JSON.parse(options.body) : null});
  return requestImpl(path, options);
};
const toast = (message) => toasts.push(String(message));
const fmoddConfirm = async (...args) => { confirms.push(args); return confirmImpl(); };
const renderTraining = () => { rendered += 1; };
const updateTrainingResponse = () => { updated += 1; };
const renderIcons = () => {};
const runItemOperation = async (_profile, _label, task) => task();
let localSubmit = 0;
const clientSubmissionId = () => `submission-${localSubmit += 1}`;
const ensurePlayerDevelopmentRosterLoaded = async () => ensureDevelopmentRosterImpl();
const ensureTrainingCoachingRosterLoaded = async () => ensureCoachingRosterImpl();
const ensureTrainingRosterLoaded = async () => ensureRosterImpl();
const managedCoachingRostersAreCurrent = () => fixtures.coachingCurrent;
const trainingRosterIsCurrent = () => fixtures.rosterCurrent;
const $ = (selector) => fixtures.dom[selector] || null;
function positionTrainingSlots() { return fixtures.slots || []; }
function positionTrainingAssignedPlayer(slotId) { return (fixtures.assigned && fixtures.assigned.get(slotId)) || null; }
function positionTrainingSlotPlaced() { return fixtures.slotPlaced !== false; }
function positionTrainingPlayerRating() { return fixtures.rating ?? 12; }
function positionTrainingTargetRating() { return fixtures.targetRating ?? 1; }
function activeTrainingFocus(playerId) { return (fixtures.active && fixtures.active[playerId]) || null; }
function player(id, name, extra = {}) {
  return {
    id, name, shirt_number:String(id), primary_positions:["DC"], positions:["DC"],
    attributes:{"身体":{"强壮":13},"技术":{"停球":12}},
    training_ca:{costs:{"身体:强壮":{next:1,to_14:2}}},
    ca:120, pa:150, training_team_id:1, training_team_name:"Current FC",
    training_team_type:"club", ...extra,
  };
}
function staff(id, name, extra = {}) {
  return {
    id, name, role:"Coach", job_type:20,
    coaching_license:{code:6,name:"National B",next_code:5,next_name:"National A",maximum:false},
    training_team_id:1, training_team_name:"Current FC", training_subject_type:"staff", ...extra,
  };
}
__HELPERS__
__DATA_INDEX__
__POSITION_RUNTIME__
(() => {
(async () => {
__TEST__
})().catch((error) => { console.error(error && error.stack || error); process.exitCode = 1; });
})();
'''


def harness(test_code: str) -> subprocess.CompletedProcess[str]:
    source = (
        BASE.replace("__HELPERS__", HELPERS)
        .replace("__DATA_INDEX__", DATA_INDEX)
        .replace("__POSITION_RUNTIME__", POSITION_RUNTIME)
        .replace("__TEST__", test_code)
    )
    if os.environ.get("T5_DUMP_SOURCE"):
        Path(os.environ["T5_DUMP_SOURCE"]).write_text(source, encoding="utf-8")
    return run_node(source)


def assert_node_ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


class TrainingTaskFrontendTests(unittest.TestCase):
    def test_markup_has_exactly_the_three_training_modules(self) -> None:
        helper_block = HELPERS.split("const TRAINING_MODULES = [", 1)[1].split("];", 1)[0]
        keys = re.findall(r'key:"([a-z_]+)"', helper_block)
        self.assertEqual(keys, ["player_training", "position_training", "staff_training"])
        self.assertIn('id="training-module-tabs"', INDEX_HTML)
        self.assertIn('id="training-roster"', INDEX_HTML)
        self.assertIn('id="training-dock-content"', INDEX_HTML)
        self.assertNotIn("data-training-scene=", INDEX_HTML)
        self.assertNotIn("data-training-dock=", INDEX_HTML)
        for legacy in (
            "training-edit-toggle", "training-rotate", "training-store-selected",
            "training-selection", "training-floor-lock",
        ):
            self.assertNotIn(legacy, INDEX_HTML, legacy)
        for route in (
            '"/api/training/purchase"', '"/api/training/place"',
            '"/api/training/store"', '"/api/training/sell"',
            '"/api/training/floor/purchase"',
        ):
            self.assertNotIn(route, APP_JS, route)
        self.assertNotIn("requestTrainingFloorUnlock", APP_JS)
        self.assertIn('request("/api/training/run"', APP_JS)
        self.assertIn('request("/api/training/cancel"', APP_JS)
        self.assertIn("project_sku", APP_JS)
        self.assertIn("client_submission_id", APP_JS)
        for css in (".training-roster {", ".training-person-row {", ".training-detail-panel {"):
            self.assertIn(css, APP_CSS, css)

    def test_module_tabs_render_three_entries(self) -> None:
        result = harness(r'''
    const root = {dataset:{}, innerHTML:"", setAttribute(name, value) { this[name] = value; }};
    fixtures.dom["#training-module-tabs"] = root;
    fixtures.data.catalog = [{sku:"strength_rack", module:"player_training"}];
    fixtures.profiles = [{
      team:{id:1,name:"Current FC",team_type:"club"},
      players:[player(1,"One")], staff:[staff(101,"Coach")],
    }];
    app.trainingModule = "player_training";
    renderTrainingModuleTabs();
    const buttons = [...root.innerHTML.matchAll(/data-training-module="([a-z_]+)"/g)].map((match) => match[1]);
    assert.deepEqual(buttons, ["player_training","position_training","staff_training"]);
    assert.equal((root.innerHTML.match(/aria-selected="true"/g) || []).length, 1);
        ''')
        assert_node_ok(result)

    def test_player_roster_is_only_the_current_first_team(self) -> None:
        result = harness(r'''
    fixtures.profiles = [
      {
        team:{id:1,name:"Current FC",team_type:"club"},
        players:[player(1,"One"),player(2,"Two")],
        squads:[
          {team_id:1,type_code:0,label:"First",players:[player(1,"One"),player(2,"Two")]},
          {team_id:9,type_code:1,label:"U21",players:[player(50,"Youth")]},
        ],
      },
      {team:{id:2,name:"Other FC",team_type:"club"},players:[player(60,"Other")]},
    ];
    fixtures.output = {
      managed_teams:[
        {id:1,name:"Current FC",team_type:"club"},
        {id:2,name:"Other FC",team_type:"club"},
      ],
      selected_manager_id:7, save_instance_id:"save-1",
    };
    const roster = trainingFirstTeamPlayers();
    assert.deepEqual(roster.map((row) => row.id), [1,2]);
    assert.ok(roster.every((row) => row.training_team_id === 1));
    assert.equal(trainingRoster("player_training").length, 2);
        ''')
        assert_node_ok(result)

    def test_staff_roster_uses_current_club_and_eligibility(self) -> None:
        result = harness(r'''
    fixtures.data.player_manager = {
      id:900, name:"Manager",
      coaching_license:{code:6,name:"B",next_code:5,next_name:"A",maximum:false},
    };
    fixtures.profiles = [
      {
        team:{id:1,name:"Current FC",team_type:"club"}, players:[],
        staff:[
          staff(101,"Eligible"), staff(102,"Analyst",{job_type:62}),
          staff(103,"Physio",{job_type:38,coaching_license:undefined}),
          staff(104,"Maxed",{coaching_license:{code:1,name:"Pro",next_code:0,next_name:"",maximum:true}}),
        ],
      },
      {team:{id:2,name:"Other FC",team_type:"club"},players:[],staff:[staff(201,"Other")]},
    ];
    fixtures.output = {managed_teams:[{id:1,name:"Current FC",team_type:"club"}], selected_manager_id:7};
    const roster = trainingCurrentStaff();
    assert.deepEqual(roster.map((row) => row.id), [900,101,102,103,104]);
    assert.equal(roster[0].training_subject_type, "player_manager");
    assert.equal(trainingStaffEligible(roster[0]), true);
    assert.equal(trainingStaffEligible(roster[1]), true);
    assert.equal(trainingStaffEligible(roster[2]), false);
    assert.equal(trainingStaffEligible(roster[3]), false);
    assert.equal(trainingStaffEligible(roster[4]), false);
    assert.equal(trainingRoster("staff_training").length, 5);
        ''')
        assert_node_ok(result)

    def test_projects_are_attributed_by_catalog_module_and_eligibility(self) -> None:
        result = harness(r'''
    fixtures.data.catalog = [
      {sku:"strength_rack",module:"player_training",attributes:["身体:强壮"]},
      {sku:"leadership_desk",module:"player_training",attributes:["身体:强壮"]},
      {sku:"coaching_desk",module:"staff_training",staff_training:true},
      {sku:"position_training_area",module:"position_training"},
      {sku:"goalkeeper_training_area",module:"player_training",position_group:"goalkeepers",attributes:["身体:强壮"]},
      {sku:"habit_lab",module:"player_training",attributes:[]},
    ];
    const outfield = player(1,"Outfield");
    const keeper = player(2,"Keeper",{group:"goalkeepers"});
    const coach = staff(101,"Coach");
    const playerProjects = trainingProjects("player_training").map((row) => row.sku);
    assert.ok(playerProjects.includes("strength_rack"));
    assert.ok(!playerProjects.includes("coaching_desk"));
    assert.ok(!playerProjects.includes("position_training_area"));
    assert.deepEqual(trainingProjects("staff_training").map((row) => row.sku), ["coaching_desk"]);
    assert.equal(trainingProjectApplies(trainingProduct("coaching_desk"),"staff",coach), true);
    assert.equal(trainingProjectApplies(trainingProduct("strength_rack"),"staff",coach), false);
    assert.equal(trainingProjectApplies(trainingProduct("goalkeeper_training_area"),"player",outfield), false);
    assert.equal(trainingProjectApplies(trainingProduct("goalkeeper_training_area"),"player",keeper), true);
    assert.equal(trainingProjectApplies(trainingProduct("habit_lab"),"player",outfield), true);
        ''')
        assert_node_ok(result)

    def test_fixed_fee_and_submission_ids_for_same_project(self) -> None:
        result = harness(r'''
    const project = {
      sku:"strength_rack", module:"player_training", attributes:["身体:强壮"],
      direction:1, task_price_minor:10_000_000, training_multiplier:3,
    };
    fixtures.data.catalog = [project];
    const one = player(1,"One");
    const two = player(2,"Two");
    const first = trainingRunPayload("player", one, project, "身体:强壮", "until_increase", 1, "");
    const second = trainingRunPayload("player", two, project, "身体:强壮", "until_increase", 1, "");
    const firstId = trainingSubmissionFor(first);
    assert.equal(trainingSubmissionFor(first), firstId);
    const secondId = trainingSubmissionFor(second);
    assert.equal(first.project_sku, second.project_sku);
    assert.equal(first.player_id, 1);
    assert.equal(second.player_id, 2);
    assert.ok(firstId && secondId && firstId !== secondId);
    const next = trainingTaskEstimate(project,"player",one,"身体:强壮","until_increase");
    const far = trainingTaskEstimate(project,"player",one,"身体:强壮","until_20");
    assert.equal(trainingFeeLabel(next.feeMinor), "GBP100000");
    assert.equal(trainingFeeLabel(0), "training.free");
    assert.equal(next.feeMinor, far.feeMinor);
    assert.equal(next.current, 13);
    assert.ok(far.days > next.days);
        ''')
        assert_node_ok(result)

    def test_occupancy_uses_person_type_not_compat_player_id(self) -> None:
        result = harness(r'''
    fixtures.data.focuses = [
      {id:"staff-focus",status:"active",focus_type:"coaching_license",staff_id:101,player_id:5,player_name:"Coach"},
      {id:"player-focus",status:"active",focus_type:"attribute",project_sku:"strength_rack",player_id:5,player_name:"Player"},
    ];
    const index = trainingDataIndex();
    assert.equal(index.activeFocusByStaff.get(101).id, "staff-focus");
    assert.equal(index.activeFocusByPlayer.get(5).id, "player-focus");
    assert.equal(trainingPersonFocus("player",5).id, "player-focus");
    assert.equal(trainingPersonFocus("staff",5), null);
    assert.equal(trainingPersonFocus("staff",101).id, "staff-focus");
    fixtures.data.catalog = [{sku:"strength_rack",module:"player_training",attributes:["身体:强壮"]}];
    fixtures.data.focuses = [{id:"player-focus",status:"active",focus_type:"attribute",player_id:5,player_name:"Player"}];
    fixtures.profiles = [{
      team:{id:1,name:"Current FC",team_type:"club"},
      players:[player(5,"Player")],
      squads:[{team_id:1,type_code:0,players:[player(5,"Player")]}],
    }];
    app.trainingPersonKind = "player";
    app.trainingPersonId = 5;
    app.trainingProjectSku = "strength_rack";
    app.trainingTargetKey = "身体:强壮";
    await submitTrainingPerson();
    assert.equal(requestCalls.length, 0);
    assert.ok(toasts.includes("training.reason_active"));
        ''')
        assert_node_ok(result)

    def test_submit_uses_project_sku_and_server_price(self) -> None:
        result = harness(r'''
    fixtures.data.catalog = [{
      sku:"strength_rack",module:"player_training",attributes:["身体:强壮"],
      direction:1,task_price_minor:10_000_000,training_multiplier:3,
    }];
    fixtures.profiles = [{
      team:{id:1,name:"Current FC",team_type:"club"},
      players:[player(1,"One")],
      squads:[{team_id:1,type_code:0,players:[player(1,"One")]}],
    }];
    requestImpl = async () => ({
      training_ground:{}, economy:{}, focus:{},
      payment:{total:100000}, duplicate:false,
    });
    app.trainingPersonKind = "player";
    app.trainingPersonId = 1;
    app.trainingProjectSku = "strength_rack";
    app.trainingTargetKey = "身体:强壮";
    await submitTrainingPerson();
    assert.equal(requestCalls.length, 1);
    const call = requestCalls[0];
    assert.equal(call.path, "/api/training/run");
    assert.equal(call.body.project_sku, "strength_rack");
    assert.equal(call.body.module, "player_training");
    assert.equal(call.body.player_id, 1);
    assert.equal(call.body.team_id, 1);
    assert.equal(call.body.operation, "attribute");
    assert.equal(call.body.attribute_key, "身体:强壮");
    assert.equal(call.body.duration_mode, "until_increase");
    assert.ok(call.body.client_submission_id);
    assert.equal(updated, 1);
    assert.ok(toasts.some((message) => message.startsWith("training.arranged")));
    assert.equal(app.trainingActionBusy, false);
    assert.equal(app.trainingSubmissionRetry, null);
        ''')
        assert_node_ok(result)

    def test_cancel_requires_second_confirmation_and_sends_once(self) -> None:
        result = harness(r'''
    const focus = {id:"focus-1",focus_type:"attribute"};
    confirmImpl = async () => false;
    await cancelTrainingTask(focus);
    assert.equal(requestCalls.length, 0);
    assert.equal(confirms.length, 1);
    assert.equal(confirms[0][0], "training.cancel_message");
    assert.equal(confirms[0][3], "training.cancel_keep");
    confirmImpl = async () => true;
    await cancelTrainingTask(focus);
    assert.equal(requestCalls.length, 1);
    assert.equal(requestCalls[0].path, "/api/training/cancel");
    assert.deepEqual(requestCalls[0].body, {focus_id:"focus-1"});
    assert.equal(updated, 1);
    assert.ok(toasts.includes("training.cancelled"));
    requestCalls = [];
    confirms = [];
    let release;
    requestImpl = () => new Promise((resolve) => { release = resolve; });
    const first = cancelTrainingTask({id:"focus-2",focus_type:"position"});
    await cancelTrainingTask({id:"focus-2",focus_type:"position"});
    assert.equal(requestCalls.length, 1);
    release({training_ground:{},focus:{}});
    await first;
        ''')
        assert_node_ok(result)

    def test_late_response_after_scope_change_is_ignored(self) -> None:
        result = harness(r'''
    fixtures.data.catalog = [{
      sku:"strength_rack",module:"player_training",attributes:["身体:强壮"],
      direction:1,task_price_minor:1,training_multiplier:3,
    }];
    fixtures.profiles = [{
      team:{id:1,name:"Current FC",team_type:"club"},
      players:[player(1,"One")],
      squads:[{team_id:1,type_code:0,players:[player(1,"One")]}],
    }];
    app.trainingPersonKind = "player";
    app.trainingPersonId = 1;
    app.trainingProjectSku = "strength_rack";
    app.trainingTargetKey = "身体:强壮";
    app.trainingScopeKey = "scope-a";
    app.trainingRequestSeq = 1;
    let release;
    requestImpl = () => new Promise((resolve) => { release = resolve; });
    const pending = submitTrainingPerson();
    app.trainingScopeKey = "scope-b";
    app.trainingRequestSeq = 99;
    release({training_ground:{},economy:{},focus:{},payment:{total:1},duplicate:false});
    await pending;
    assert.equal(updated, 0);
    assert.equal(toasts.length, 0);
        ''')
        assert_node_ok(result)

    def test_position_submission_keeps_project_sku_and_skips_occupied(self) -> None:
        result = harness(r'''
    fixtures.data.catalog = [{sku:"position_training_area",module:"position_training",task_price_minor:0}];
    const roster = [
      player(1,"One",{position_ratings:{ST:12}}),
      player(2,"Two",{position_ratings:{ST:13}}),
    ];
    const slot = {id:"st",position:"ST",placed:true,x:50,y:20};
    const payload = positionTrainingPayload(roster[0], slot, "until_20");
    assert.equal(payload.project_sku, "position_training_area");
    assert.equal(payload.module, "position_training");
    assert.equal(payload.player_id, 1);
    assert.equal(payload.position_key, "ST");
    assert.equal(payload.operation, "position");
    assert.equal(payload.team_id, 1);
    const state = {preset:"4231",durationMode:"until_20"};
    const byId = new Map(roster.map((row) => [row.id,row]));
    fixtures.slots = [slot];
    fixtures.assigned = new Map([["st", roster[0]]]);
    assert.deepEqual(positionTrainingRows(state, byId).map((row) => row.player.id), [1]);
    fixtures.assigned = new Map([["st", roster[1]]]);
    fixtures.active = {2:{id:"focus"}};
    assert.equal(positionTrainingRows(state, byId).length, 0);
        ''')
        assert_node_ok(result)

    def test_roster_failure_keeps_retry_entry(self) -> None:
        result = harness(r'''
    let attempts = 0;
    ensureDevelopmentRosterImpl = async () => {
      attempts += 1;
      if (attempts === 1) throw new Error("read failed");
      return true;
    };
    app.trainingModule = "player_training";
    await loadTrainingRoster();
    assert.equal(app.trainingRosterError, "read failed");
    assert.equal(app.trainingRosterLoading, false);
    await loadTrainingRoster({force:true});
    assert.equal(app.trainingRosterError, "");
    assert.equal(attempts, 2);
        ''')
        assert_node_ok(result)

    def test_app_js_passes_node_syntax_check(self) -> None:
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("Node.js is required")
        result = subprocess.run(
            [node, "--check", str(ROOT / "web" / "app.js")],
            capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
