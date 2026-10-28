from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from frontend_source import read_frontend_source


ROOT = (Path(__file__).resolve().parents[1] / "src")
WEB = ROOT / "web"

LEAGUE_START = "const LEAGUE_CATALOG_SOURCE_NATIVE = "
LEAGUE_END = "function championshipEnabled"

PRELUDE = r'''
const assert = require("node:assert/strict");
const storage = new Map();
const localStorage = {
  getItem: (key) => (storage.has(key) ? storage.get(key) : null),
  setItem: (key, value) => { storage.set(key, String(value)); },
};
const app = {state:{}, leagueSelections:null, leagueDisplayCount:3};
const output = () => ({game_layout:"fm26", save_instance_id:"save-1"});
const activeUiLocale = () => "en-GB";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => (
  {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[char]
));
const uiText = (key, parameters = {}) => (
  Object.keys(parameters).length ? `${key} ${JSON.stringify(parameters)}` : key
);
const managedTeamIds = () => new Set([42]);
const refreshBlocksPublishedState = () => false;
const renderIcons = () => {};
const nodes = new Map();
const document = {
  querySelector: (selector) => nodes.get(selector) || null,
  querySelectorAll: () => [],
};
const $ = (selector) => document.querySelector(selector);
const catalogOf = (rows) => ({
  source:"native_competition_table", scope_id:"save-1", game_layout:"fm26",
  native:true, scanned_at:"2026-10-28T00:00:00.000Z", competitions:rows,
});
const entryOf = (id, name, shortName, reputation, available, source, reason) => ({
  competition_id:id, name, short_name:shortName || name, reputation,
  standings_available:available === true,
  standings_source:available === true ? (source || "native") : null,
  standings_reason:reason === undefined ? null : reason,
});
const competitionsOf = (ids) => ids.map((id) => ({
  competition_id:id, competition_name:`Competition ${id}`, reputation:10,
  source:"native",
  teams:[{team_id:1, team_name:"Alpha", position:1, played:2, won:2, drawn:0, lost:0, goal_difference:3, points:6}],
}));
'''


@lru_cache(maxsize=1)
def league_block() -> str:
    """Return the raw (non-projected) league block of the shipped ``app.js``."""
    source = read_frontend_source(WEB / "app.js", mode="raw")
    if source.count(LEAGUE_START) != 1 or source.count(LEAGUE_END) != 1:
        raise AssertionError("league block markers changed in src/web/app.js")
    body = source.split(LEAGUE_START, 1)[1].split(LEAGUE_END, 1)[0]
    return LEAGUE_START + body + "\n"


def run_node(body: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for the isolated frontend harness")
    source = PRELUDE + "\n" + league_block() + "\n" + body
    return subprocess.run(
        [node, "-"], input=source, text=True, encoding="utf-8",
        capture_output=True, timeout=60, check=False,
    )


def assert_node_ok(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_league_picker_filters_by_name_short_name_and_competition_id() -> None:
    body = r'''
app.state.league_catalog = catalogOf([
  entryOf(11, "Manchester United", "Man Utd", 900, true, "native"),
  entryOf(12, "Real Madrid", "Real", 950, true, "native"),
  entryOf(13, "曼联", "曼联", 800, false, null, "no_native_format"),
  entryOf(14, "Aarhus", "", 100, false, null, "not_a_league"),
]);
const ids = (query) => leaguePickerMatches(query).rows.map((row) => row.id);

assert.deepEqual(ids(""), [12, 11, 13, 14], "unfiltered rows stay reputation sorted");
assert.deepEqual(ids("united"), [11], "matches the full name");
assert.deepEqual(ids("UNITED"), [11], "matching is case-insensitive");
assert.deepEqual(ids("man utd"), [11], "matches the short name");
assert.deepEqual(ids("Man"), [11], "a short-name prefix still matches");
assert.deepEqual(ids("12"), [12], "matches the competition id");
assert.deepEqual(ids("aarhus"), [14], "a missing short name falls back to the name");
assert.deepEqual(ids("曼联"), [13], "zh-CN input matches a zh-CN name");
assert.deepEqual(ids("real madrid "), [12], "surrounding whitespace is ignored");
assert.deepEqual(ids("zzz"), [], "an unmatched query yields no rows");
assert.equal(leaguePickerMatches("").total, 4, "total counts every match");
const many = Array.from({length:120}, (_, index) => entryOf(1000 + index, `Club ${index}`, "", 500));
app.state.league_catalog = catalogOf(many);
const capped = leaguePickerMatches("");
assert.equal(capped.rows.length, 50, "at most 50 rows reach the DOM");
assert.equal(capped.total, 120, "the refine counter still sees every match");
const markup = leaguePickerOptionRows(capped.rows, capped.total, 0, null, null);
assert.equal((markup.match(/role="option"/g) || []).length, 50, "only 50 options are rendered");
assert.ok(markup.includes('league-picker-refine'), "the refine hint appears above the cap");
assert.ok(markup.includes("league.picker.refine"), "the hint is a localized string, not hard-coded copy");
assert.ok(markup.includes("&quot;shown&quot;:50") && markup.includes("&quot;total&quot;:120"),
  "the hint reports the rendered row count and the full match count");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_default_order_uses_native_reputation_instead_of_old_metadata() -> None:
    body = r'''
const competitions = competitionsOf([7, 8, 9]);
competitions[0].reputation = 200;
competitions[1].reputation = 10;
competitions[2].reputation = 100;
app.state.league_standings = {competitions};
app.state.league_catalog = catalogOf([
  entryOf(7, "League A", "A", 100, true),
  entryOf(8, "League B", "B", 190, true),
  entryOf(9, "League C", "C", 150, true),
]);
const index = leagueDataIndex();
assert.deepEqual(index.competitions.map(row => row.competition_id), [8, 9, 7],
  "the game's native reputation determines the default league ranking");
assert.deepEqual(leagueSelections(index.competitions), [8, 9, 7]);
assert.equal(competitions[0].reputation, 200, "display ordering does not mutate standings facts");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_defaults_update_when_the_native_catalog_arrives_later() -> None:
    body = r'''
const competitions = competitionsOf([7, 8, 9]);
competitions[0].reputation = 200;
competitions[1].reputation = 10;
competitions[2].reputation = 100;
app.state.league_standings = {competitions};
assert.deepEqual(leagueSelections(leagueDataIndex().competitions), [7, 9, 8]);
app.state.league_catalog = catalogOf([
  entryOf(7, "League A", "A", 100, true),
  entryOf(8, "League B", "B", 190, true),
  entryOf(9, "League C", "C", 150, true),
]);
assert.deepEqual(leagueSelections(leagueDataIndex().competitions), [8, 9, 7],
  "a temporary fallback must not freeze the defaults ahead of the native ranking");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_picker_keeps_unavailable_competitions_selectable() -> None:
    body = r'''
app.state.league_catalog = catalogOf([
  entryOf(21, "English League One", "League One", 400, false, null, "not_league_opening_stage"),
  entryOf(22, "Scottish Premiership", "Premiership", 600, true, "native"),
]);
const unavailable = leagueDataIndex().catalogRowsById.get(21);
const row = leaguePickerOptionRow(unavailable, 2, null, null);
assert.ok(row.includes('role="option"'), "the row is an option");
assert.ok(row.includes('id="league-picker-option-2-21"'), "the row exposes a stable id");
assert.ok(!row.includes("disabled"), "unavailable rows must stay selectable");
assert.ok(row.includes("league-picker-option unavailable"), "unavailable rows are marked visually");
assert.ok(row.includes('aria-selected="false"'), "unselected rows report aria-selected=false");
assert.equal(leaguePickerOptionRow(unavailable, 2, 21, 21).includes("selected"), true,
  "a chosen row is marked selected");
const rows = leaguePickerOptionRows([unavailable], 1, 2, null, null);
assert.ok(!rows.includes("league-picker-refine"), "no refine hint when every match is shown");
const empty = leaguePickerOptionRows([], 0, 2, null, null);
assert.ok(empty.includes("league-picker-empty"), "an unmatched search renders the empty result");
const markup = leaguePickerMarkup(2, 22, "Scottish Premiership");
assert.ok(markup.includes('role="listbox"'), "the options container is a listbox");
assert.ok(markup.includes('id="league-picker-options-2"'), "the listbox has a stable id");
assert.ok(markup.includes('aria-controls="league-picker-options-2"'), "the combobox controls that id");
assert.ok(markup.includes('role="combobox"'), "the search field is a combobox");
assert.ok(markup.includes('aria-autocomplete="list"'), "the combobox declares list autocomplete");
assert.ok(markup.includes('aria-expanded="false"'), "the collapsed combobox starts collapsed");
assert.ok(!markup.includes("aria-activedescendant"), "nothing is active before the first key");
assert.ok(markup.includes('class="league-picker"') && !markup.includes("<span class=\"league-picker\""),
  "the picker root is a div because the panel holds block content");
assert.ok(markup.includes('data-league-slot="2"'), "the trigger keeps the legacy slot hook");
assert.ok(!markup.includes("<select"), "the picker replaces the native select");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_ranked_defaults_and_manual_replacements_are_save_scoped() -> None:
    body = r'''
const competitions = competitionsOf([7, 8]);
app.state.data_scope_id = "save-42";
assert.equal(leagueSelectionScope(), "save-42", "the active save scopes the storage key");
const firstKey = leagueSelectionStorageKey();
assert.ok(firstKey.endsWith("save-42"), "the preference belongs to the current save");
localStorage.setItem("fm-odds-league-slots-fm26", JSON.stringify([8, 7]));
localStorage.setItem("fm-odds-league-slots-save-42", JSON.stringify([8, 7]));
assert.deepEqual(leagueSelections(competitions), [7, 8],
  "old auto-filled lists cannot override the new reputation-ranked defaults");
assert.equal(storage.get(firstKey), undefined, "automatic defaults are not saved as manual choices");
assert.equal(storage.get("fm-odds-league-slots-fm26"), "[8,7]", "legacy preferences are preserved for older builds");
leaguePickerSelect(0, 8);
app.leagueSelections = null;
assert.deepEqual(leagueSelections(competitions), [8, 7], "the player's later manual replacement survives reload");
app.leagueSelections = null;
app.state.data_scope_id = "save-99";
const secondKey = leagueSelectionStorageKey();
assert.notEqual(secondKey, firstKey, "another save reads its own preference");
assert.deepEqual(leagueSelections(competitions), [7, 8], "an empty save bucket auto-fills from available rows");
assert.equal(storage.get(secondKey), undefined, "another save has no manual preferences yet");
assert.deepEqual(JSON.parse(storage.get(firstKey)), [8, 7], "the other save's custom order is unchanged");
app.leagueSelections = null;
app.state.data_scope_id = "";
assert.equal(leagueSelectionScope(), "save-1", "a blank scope falls back to the save instance id");
assert.ok(leagueSelectionStorageKey().endsWith("save-1"), "the fallback still scopes the key");
app.leagueSelections = null;
app.state.data_scope_id = "   ";
assert.equal(leagueSelectionScope(), "", "a whitespace-only scope trims away");
assert.ok(leagueSelectionStorageKey().endsWith("fm26"),
  "an unscoped connection uses the game layout instead of a bogus save key");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_board_falls_back_to_native_select_without_catalog() -> None:
    body = r'''
const competitions = competitionsOf([7]);
app.state.league_standings = {competitions};
let index = leagueDataIndex();
assert.equal(index.catalogRows.length, 0, "no catalog yields no picker rows");
const legacy = leagueBoard(index.competitionsById.get(7), competitions, 0, new Set());
assert.ok(legacy.includes('<select data-league-slot="0"'), "the legacy native select is preserved");
assert.ok(!legacy.includes("league-picker"), "no picker markup without a catalog");
assert.ok(legacy.includes("league-table"), "the standings table still renders");
assert.ok(!legacy.includes("league-reason") && !legacy.includes("league.unavailable"),
  "the fallback path never mentions a reason");
let signature = leagueRenderStateSignature(index, [7], new Set());
assert.ok(!signature.includes("native_competition_table"), "an absent catalog adds no signature noise");

app.state.league_catalog = catalogOf([
  entryOf(31, "League Without Table", "No Table", 300, false, null, "native_rows_incomplete"),
  entryOf(32, "Reconstructed League", "Recon", 700, true, "reconstructed", "reconstructed_ahead_of_native"),
]);
index = leagueDataIndex();
assert.equal(index.catalogRows.length, 2, "the catalog feeds the picker");
const picker = leagueBoard(index.competitionsById.get(7), competitions, 0, new Set());
assert.ok(picker.includes("<button"), "the picker trigger replaces the native select");
assert.ok(!picker.includes("<select"), "no native select once a catalog exists");
assert.ok(picker.includes('data-league-slot="0"'), "the picker keeps the slot hook");

const unavailable = leagueBoard(undefined, competitions, 1, new Set());
assert.ok(unavailable.includes("league-unavailable"), "a standings-less pick stays inside the board");
assert.ok(unavailable.includes("league.reason.no_native_format"), "the reason code drives the label");
assert.ok(unavailable.includes('role="status"'), "the notice is announced");
assert.ok(!unavailable.includes("league-table"), "no empty table is drawn for an unavailable pick");

const reconstructed = leagueBoard(index.competitionsById.get(7), competitions, 2, new Set());
assert.ok(reconstructed.includes("league-table"), "a reconstructed table still renders");
assert.ok(!reconstructed.includes("league-unavailable"), "an available table never shows the notice");

const mystery = leagueDataIndex().catalogRowsById.get(31);
assert.ok(leagueReasonLabel(mystery).includes("league.reason.native_rows_incomplete"),
  "each frozen reason code owns a label");
mystery.standingsReason = "some_future_code";
assert.ok(leagueReasonLabel(mystery).includes("league.reason.unknown"),
  "an unknown reason falls back to the default label");

const changed = catalogOf([entryOf(31, "Renamed League", "Renamed", 300, false, null, "native_rows_incomplete")]);
app.state.league_catalog = changed;
assert.notEqual(leagueDataIndex().catalogSignature, index.catalogSignature,
  "a catalog change invalidates the render signature");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_picker_tracks_the_active_option_for_assistive_technology() -> None:
    body = r'''
app.state.league_catalog = catalogOf([
  entryOf(41, "First League", "First", 900, true, "native"),
  entryOf(42, "Second League", "Second", 800, false, null, "not_a_league"),
]);
const activeClasses = new Set();
const items = [41, 42].map((id) => ({
  id:`league-picker-option-0-${id}`,
  classList:{
    contains:(name) => activeClasses.has(`${id}:${name}`),
    toggle:(name, on) => { on ? activeClasses.add(`${id}:${name}`) : activeClasses.delete(`${id}:${name}`); },
  },
  scrollIntoView(){},
}));
const attributes = new Map();
const input = {
  value:"",
  setAttribute:(name, value) => attributes.set(name, String(value)),
  getAttribute:(name) => (attributes.has(name) ? attributes.get(name) : null),
  removeAttribute:(name) => attributes.delete(name),
  focus(){},
};
const activeItem = () => items.find((item) => item.classList.contains("active")) || null;
const options = {
  querySelectorAll: () => items,
  querySelector: (selector) => (selector.includes("active") ? activeItem() : null),
};
const pane = {
  querySelector(selector) {
    if (selector === ".league-picker-input") return input;
    if (selector === "[data-league-options]") return options;
    if (selector.startsWith("[data-league-options]")) return activeItem();
    return null;
  },
};
nodes.set('.league-picker[data-league-picker="0"]', pane);

leaguePickerMoveActive(0, 1);
assert.equal(input.getAttribute("aria-activedescendant"), "league-picker-option-0-41",
  "the first arrow opens on the first row");
assert.equal(input.getAttribute("aria-expanded"), "true", "the combobox is expanded while navigating");
leaguePickerMoveActive(0, 1);
assert.equal(input.getAttribute("aria-activedescendant"), "league-picker-option-0-42",
  "the active descendant follows the arrow keys");
leaguePickerMoveActive(0, -1);
assert.equal(input.getAttribute("aria-activedescendant"), "league-picker-option-0-41",
  "moving back restores the previous descendant");
activeClasses.clear();
leaguePickerSyncActiveDescendant(0);
assert.equal(input.getAttribute("aria-activedescendant"), null,
  "no active row clears the active descendant");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_render_fills_a_catalog_only_save_and_caps_the_visible_boards() -> None:
    body = r'''
const grid = {innerHTML:"", style:{setProperty(){}}};
nodes.set("#league-board-grid", grid);
nodes.set("#page-league", {setAttribute(){}});
nodes.set("#league-refresh-button", {disabled:false, setAttribute(){}});
nodes.set("#league-sync-status", {hidden:false});
app.state.league_standings = {competitions:[]};
app.state.league_catalog = catalogOf([
  entryOf(51, "Alpha League", "Alpha", 900, false, null, "no_native_format"),
  entryOf(52, "Beta League", "Beta", 800, false, null, "not_a_league"),
  entryOf(53, "Gamma League", "Gamma", 700, false, null, "team_standing_unverified"),
]);
app.leagueDisplayCount = 2;
renderLeague();
assert.ok(!grid.innerHTML.includes("league-empty"), "a catalog-only save is never a dead end");
assert.equal((grid.innerHTML.match(/data-league-slot="/g) || []).length, 2,
  "the visible board count caps the rendered pickers");
assert.ok(grid.innerHTML.includes("league-picker"), "the catalog drives the picker even without standings");
assert.ok(grid.innerHTML.includes("league-unavailable"), "each unavailable board explains itself");
assert.deepEqual(app.leagueSelections, [51, 52], "the automatically displayed competitions are available");
assert.equal(storage.get(leagueSelectionStorageKey()), undefined,
  "a catalog-only fallback is never saved as the player's choice");

app.leagueDisplayCount = 9;
app.leagueRenderSignature = null;
renderLeague();
assert.equal((grid.innerHTML.match(/data-league-slot="/g) || []).length, 3,
  "the cap follows the stored selection length, not the standings count");

app.state.league_catalog = null;
app.state.league_standings = {competitions:[]};
app.leagueRenderSignature = null;
grid.innerHTML = "";
renderLeague();
assert.ok(grid.innerHTML.includes("league-empty"), "without standings and catalog the empty state returns");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


def test_league_search_survives_refresh_and_closes_when_the_save_changes() -> None:
    body = r'''
const grid = {innerHTML:"", style:{setProperty(){}}};
nodes.set("#league-board-grid", grid);
nodes.set("#page-league", {setAttribute(){}});
nodes.set("#league-refresh-button", {disabled:false, setAttribute(){}});
nodes.set("#league-sync-status", {hidden:false});
app.state.data_scope_id = "save-1";
app.state.league_standings = {competitions:competitionsOf([7])};
app.state.league_catalog = catalogOf([entryOf(7, "Search League", "Search", 100, true)]);
renderLeague();
let panel;
let input;
let trigger;
let opened;
let focused = false;
const attributes = new Map();
const mountPicker = () => {
  opened = false;
  panel = {hidden:true, style:{}};
  input = {
    value:"", setAttribute(){}, removeAttribute(){},
    focus(){ focused = true; document.activeElement = input; },
  };
  const options = {innerHTML:"", querySelector(){ return null; }, querySelectorAll(){ return []; }};
  const pane = {
    classList:{add(){ opened = true; }, remove(){ opened = false; }},
    querySelector(selector) {
      if (selector === ".league-picker-panel") return panel;
      if (selector === ".league-picker-trigger") return trigger;
      if (selector === ".league-picker-input") return input;
      if (selector === "[data-league-options]") return options;
      return null;
    },
  };
  trigger = {
    dataset:{leagueSlot:"0"}, closest(){ return pane; },
    setAttribute:(name, value) => attributes.set(name, value),
    getBoundingClientRect:() => ({left:10, right:310, top:10, bottom:48, width:300}),
  };
  nodes.set('.league-picker[data-league-picker="0"]', pane);
};
globalThis.window = {innerWidth:1024, innerHeight:768};
Object.defineProperty(grid, "innerHTML", {set(value){ mountPicker(); }});
mountPicker();
leaguePickerOpen(trigger);
input.value = leaguePickerState.query = "Search";
focused = false;
app.state.data_version = 2;
renderLeague();
assert.equal(panel.hidden, false, "a same-save refresh keeps the search panel open");
assert.equal(opened, true, "the rebuilt picker stays expanded");
assert.equal(input.value, "Search", "the search text survives background refresh");
assert.equal(focused, true, "typing can continue in the rebuilt input");

app.state.data_scope_id = "save-2";
app.state.league_catalog = {...app.state.league_catalog, scope_id:"save-2"};
renderLeague();
assert.equal(leaguePickerState.slot, null, "switching saves ends the old search");
assert.equal(leaguePickerState.query, "", "the old save's query is cleared");
assert.equal(panel.hidden, true, "a new save never reopens the old save's picker");
process.stdout.write("ok");
'''
    assert_node_ok(run_node(body))


I18N_MODULES = (
    "i18n.shell.js", "i18n.static.js", "i18n.settings.js", "i18n.commerce.js",
    "i18n.facilities.js", "i18n.items.js", "i18n.relationship.js", "i18n.world.js",
    "i18n.enums.js", "i18n.js",
)

I18N_SCRIPT = r'''
const assert = require("node:assert/strict");
const fs = require("fs");
const vm = require("vm");
const context = {
  window:{FMODDI18nModules:[], FMODDLocalePacks:{}},
  document:{documentElement:{dataset:{}}, querySelector:()=>null, dispatchEvent:()=>{}},
  NodeFilter:{SHOW_TEXT:4}, CustomEvent:class CustomEvent {},
};
vm.createContext(context);
for (const file of process.argv.slice(1)) vm.runInContext(fs.readFileSync(file, "utf8"), context);
const i18n = context.window.FMODDI18n;
const keys = JSON.parse(process.env.LEAGUE_I18N_KEYS);
const resolved = {};
for (const locale of ["en-GB", "zh-CN"]) {
  i18n.setLocale(locale, {persist:false, root:null});
  const catalog = Object.fromEntries(i18n.catalogKeys(locale).map((key) => [key, i18n.t(key)]));
  resolved[locale] = {};
  for (const key of keys) {
    assert.ok(Object.hasOwn(catalog, key), `${key} is missing from ${locale}`);
    resolved[locale][key] = catalog[key];
  }
}
for (const key of keys) {
  assert.notEqual(resolved["en-GB"][key], key, `${key} has no en-GB copy`);
  assert.notEqual(resolved["zh-CN"][key], key, `${key} has no zh-CN copy`);
  assert.notEqual(resolved["en-GB"][key], resolved["zh-CN"][key], `${key} is untranslated in zh-CN`);
}
process.stdout.write(`ok ${keys.length}`);
'''


def test_league_picker_i18n_keys_resolve_in_both_locales() -> None:
    keys = sorted(set(re.findall(r'"(league\.[a-z0-9_.]+)"', league_block())))
    assert keys, "the league block references league i18n keys"
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for the isolated frontend harness")
    result = subprocess.run(
        [node, "-e", I18N_SCRIPT, *(str(WEB / name) for name in I18N_MODULES)],
        text=True, encoding="utf-8", capture_output=True, timeout=60, check=False,
        env={**os.environ, "LEAGUE_I18N_KEYS": json.dumps(keys)},
    )
    assert_node_ok(result)
    assert result.stdout.strip() == f"ok {len(keys)}", result.stdout


def test_web_scripts_pass_node_syntax_check() -> None:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for the isolated frontend harness")
    for name in ("app.js", "i18n.commerce.js", "i18n.static.js"):
        result = subprocess.run(
            [node, "--check", str(WEB / name)],
            text=True, encoding="utf-8", capture_output=True, timeout=60, check=False,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"


def test_league_index_signature_and_managed_team_context_are_reused() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    league = script.split("function leagueData()", 1)[1].split(
        "function championshipEnabled", 1,
    )[0]
    index = league.split("function leagueDataIndex()", 1)[1].split(
        "function leagueSelectionStorageKey", 1,
    )[0]
    board = league.split("function leagueBoard", 1)[1].split(
        "function leagueRenderStateSignature", 1,
    )[0]
    renderer = league.split("function renderLeague()", 1)[1]

    assert "app.leagueIndexSource === data" in index
    assert "competitionsById:new Map" in index
    assert "function leagueBoard(competition, competitions, slot, managed)" in league
    assert "managedTeamIds()" not in board
    assert "const signature = leagueRenderStateSignature" in renderer
    assert "if (app.leagueRenderSignature === signature) return;" in renderer
    assert renderer.index("app.leagueRenderSignature === signature") < renderer.index("root.innerHTML =")


def test_championship_index_covers_settlement_teams_and_render_state() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    championship = script.split("function championshipEnabled()", 1)[1].split(
        "const EMPTY_TRAINING_DATA", 1,
    )[0]
    index = championship.split("function championshipDataIndex()", 1)[1].split(
        "function championshipSettlementDate", 1,
    )[0]
    renderer = championship.split("function renderChampionship()", 1)[1]

    assert "sources?.data === data" in index
    assert "sources.catalog === catalog" in index
    assert "competitionsBySeasonKey" in index
    assert "teamsByCompetitionId" in index
    assert "championshipDataIndex().competitionsBySeasonKey.get" in championship
    assert "index.teamsByCompetitionId.get(competitionId)?.get" in renderer
    assert "const signature = championshipRenderStateSignature" in renderer
    assert "if (app.championshipRenderSignature === signature) return;" in renderer
    assert renderer.index("app.championshipRenderSignature === signature") < renderer.index("root.innerHTML =")
    assert 'aria-pressed="${chosen}"' in renderer
    assert 'role="group" aria-label="${escapeHtml(uiText("championship.team_choice"' in renderer


def test_league_and_championship_publish_busy_keyboard_and_motion_feedback() -> None:
    markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "app.css").read_text(encoding="utf-8")

    assert 'aria-labelledby="league-page-title" aria-busy="false"' in markup
    assert 'id="league-sync-status" role="status" aria-live="polite" hidden' in markup
    assert 'id="league-refresh-button"' in markup
    assert 'data-i18n-aria-label="world.refresh" aria-busy="false"' in markup
    assert 'role="group" aria-label="Display competition count" data-i18n-aria-label="league.display_count"' in markup
    assert 'aria-label="Outright markets" data-i18n-aria-label="bet.championship" aria-busy="false"' in markup
    assert ".league-page-controls .segmented button:focus-visible" in styles
    assert ".league-refresh-button:focus-visible" in styles
    assert "font-size:13px" in styles.split(".league-refresh-button {", 1)[1].split("}", 1)[0]
    assert ".league-board>header select:focus-visible" in styles
    assert ".championship-fixture-row:focus-visible" in styles
    assert ".championship-team:focus-visible" in styles
    reduced_motion = styles.split("@media (prefers-reduced-motion: reduce)", 1)[1]
    assert ".league-sync-status > i" in reduced_motion
    assert '.league-refresh-button[aria-busy="true"] svg' in reduced_motion
    assert ".championship-team" in reduced_motion


def test_league_manual_refresh_uses_standings_refresh_and_busy_state() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    renderer = script.split("function renderLeague()", 1)[1].split(
        "function championshipEnabled", 1,
    )[0]
    handler = script.split(
        '$("#league-refresh-button").addEventListener("click"', 1,
    )[1].split('$("#canteen-dock-tabs")', 1)[0]

    assert 'refreshButton.disabled = busy' in renderer
    assert 'refreshButton.setAttribute("aria-busy", String(busy))' in renderer
    assert 'request("/api/league/refresh"' in handler
    assert "if (response.started)" in handler
    assert 'beginRefreshStatusPolling("fast"' in handler


def test_league_rows_do_not_style_unverified_position_zones() -> None:
    script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    board = script.split("function leagueBoard", 1)[1].split(
        "function leagueRenderStateSignature", 1,
    )[0]

    assert "top-zone" not in board
    assert "bottom-zone" not in board
    assert "positionClass" not in board
    assert 'class="managed"' in board


def test_league_page_background_matches_feature_pages_in_both_themes() -> None:
    styles = (ROOT / "web" / "app.css").read_text(encoding="utf-8")
    dark_styles = (ROOT / "web" / "dark-theme.css").read_text(encoding="utf-8")

    league_page = styles.split(".league-page {", 1)[1].split("}", 1)[0]
    feature_page = styles.split(".feature-page {", 1)[1].split("}", 1)[0]
    dark_league_page = dark_styles.split(
        ':root[data-theme="dark"] .league-page {', 1,
    )[1].split("}", 1)[0]
    dark_feature_page = dark_styles.split(
        ':root[data-theme="dark"] .feature-page {', 1,
    )[1].split("}", 1)[0]

    background = lambda block: block.split("background:", 1)[1].split(";", 1)[0]

    assert background(league_page) == background(feature_page)
    assert background(dark_league_page) == background(dark_feature_page)
