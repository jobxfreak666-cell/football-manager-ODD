"""Exercise the manual intelligence search with deferred requests, without FM."""
from pathlib import Path
import subprocess

import pytest


def test_manual_intelligence_search_preserves_results_and_rejects_stale_responses():
    root = Path(__file__).resolve().parents[1] / "src"
    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const source = fs.readFileSync(process.argv[1] + "/web/app.js", "utf8");
const start = source.indexOf("async function refreshMatchIntelligence()");
assert.ok(start >= 0, "manual search must have a real request handler");
const end = source.indexOf("async function loadMatchIntelligence", start);
assert.ok(end > start);
const old = {candidates:[{fixture_id:"old"}]};
const app = {state:{data_scope_id:"save-a"}, page:"activity", activityFloor:"intelligence",
  matchIntelligence:old, matchIntelligenceLoading:false, activityActionBusy:false};
const pending = [], notices = [], renders = [];
let click;
const context = {app, uiText:key => key, toast:message => notices.push(message),
  document:{querySelectorAll:selector => {
    assert.equal(selector, "[data-intelligence-search]");
    return [{addEventListener:(type, handler) => {assert.equal(type, "click"); click = handler;}}];
  }},
  renderActivity:() => renders.push(app.matchIntelligenceLoading),
  request:(path, options) => {
    assert.equal(path, "/api/activity/intelligence/refresh");
    assert.equal(options.method, "POST");
    assert.equal(JSON.parse(options.body).data_scope_id, app.state.data_scope_id);
    return new Promise((resolve, reject) => pending.push({resolve, reject}));
  }};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const binding = source.split("\n").find(line => line.includes('document.querySelectorAll("[data-intelligence-search]")'));
assert.ok(binding, "the visible button must invoke the manual search handler");
vm.runInContext(binding, context);
(async () => {
  const first = click();
  assert.equal(app.matchIntelligenceLoading, true);
  assert.equal(app.matchIntelligence, old, "keep the displayed list while searching");
  await context.refreshMatchIntelligence();
  assert.equal(pending.length, 1, "double clicks must not start another scan");
  const fresh = {candidates:[{fixture_id:"new"}]};
  pending[0].resolve({intelligence:fresh, data_scope_id:"save-a"});
  await first;
  assert.equal(app.matchIntelligence, fresh);
  assert.equal(app.matchIntelligenceLoading, false);
  assert.equal(notices.length, 1);
  const failure = context.refreshMatchIntelligence();
  pending[1].reject(new Error("busy"));
  await failure;
  assert.equal(app.matchIntelligence, fresh, "failed searches must retain existing results");
  assert.equal(app.matchIntelligenceError, "busy");
  assert.equal(app.matchIntelligenceLoading, false);
  const codedErrors = [
    ["match_intelligence_busy", "activity.intelligence_search_busy"],
    ["match_intelligence_scope_changed", "activity.intelligence_context_changed"],
    ["match_intelligence_context_changed", "activity.intelligence_context_changed"],
    ["match_intelligence_save_pending", "activity.intelligence_context_changed"],
    ["match_intelligence_save_required", "activity.intelligence_context_changed"],
    ["match_intelligence_scope_required", "activity.intelligence_context_changed"],
    ["match_intelligence_clock_unavailable", "activity.intelligence_clock_unavailable"],
    ["match_intelligence_probe_failed", "activity.intelligence_search_failed"],
    ["match_intelligence_projection_failed", "activity.intelligence_search_failed"],
    ["activity_centre_locked", "activity.floor_locked"],
  ];
  for (const [code, expectedKey] of codedErrors) {
    const failedSearch = context.refreshMatchIntelligence();
    const error = new Error("Request failed");
    error.code = code;
    pending[pending.length - 1].reject(error);
    await failedSearch;
    assert.equal(app.matchIntelligenceError, expectedKey, `${code} must use its semantic message`);
    assert.equal(notices[notices.length - 1], expectedKey, `${code} toast must be localised`);
    assert.equal(app.matchIntelligence, fresh, `${code} must preserve the displayed candidates`);
  }
  const unknownFailure = context.refreshMatchIntelligence();
  const unknownError = new Error("Request failed");
  unknownError.code = "unrecognised_code";
  pending[pending.length - 1].reject(unknownError);
  await unknownFailure;
  assert.equal(app.matchIntelligenceError, "Request failed", "unknown codes must keep the server message fallback");
  const stale = context.refreshMatchIntelligence();
  app.state.data_scope_id = "save-b";
  app.matchIntelligence = null;
  const noticeCount = notices.length;
  pending[13].resolve({intelligence:old, data_scope_id:"save-a"});
  await stale;
  assert.equal(app.matchIntelligence, null, "do not publish results from another save");
  assert.equal(notices.length, noticeCount);
  assert.equal(app.matchIntelligenceLoading, false);
  const wrongResponse = context.refreshMatchIntelligence();
  pending[14].resolve({intelligence:old, data_scope_id:"save-a"});
  await wrongResponse;
  assert.equal(app.matchIntelligence, null, "reject responses labelled for another save");
  app.activityActionBusy = true;
  await context.refreshMatchIntelligence();
  assert.equal(pending.length, 15, "do not search during an intelligence purchase");
  assert.deepEqual(renders.slice(0, 2), [true, false]);
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
    result = subprocess.run(
        ["node", "-e", script, str(root)],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_intelligence_views_keep_their_results_during_search_and_after_failure():
    root = Path(__file__).resolve().parents[1] / "src"
    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const source = fs.readFileSync(process.argv[1] + "/web/app.js", "utf8");
const start = source.indexOf('    if (selectedActivity.kind === "match_intelligence") {');
const end = source.indexOf('    if (selectedActivity.kind === "salary_policy")', start);
assert.ok(start >= 0 && end > start);
const candidate = {fixture_id:"kept", competition_id:1, competition_name:"Saved competition",
  fixture_date:"2026-10-25", kickoff_time:"15:00", available:true, purchased_today:true,
  home:{id:1,name:"Saved home"}, away:{id:2,name:"Saved away"},
  tiers:[{key:"outcome",name:"Outcome",price:40000000,random_price:40000000,specific_price:40000000}]};
const app = {matchIntelligence:{candidates:[candidate]}, matchIntelligenceLoading:false,
  matchIntelligenceError:"", activityActionBusy:false, intelligenceExpandedFixtures:new Set(),
  favoriteCompetitionIds:new Set(), favoriteTeamIds:new Set(), intelligenceHistoryGroup:"today"};
const activityIndex = {candidates:[candidate], availableCandidates:[candidate],
  availableByCompetition:new Map([[candidate.competition_name,[candidate]]]),
  candidatesByFixtureId:new Map([[candidate.fixture_id,candidate]]),
  obtainedCandidates:[candidate], randomAvailableTiers:new Set(["outcome"])};
const context = {app, activityIndex, selectedActivity:{kind:"match_intelligence",name:"Intelligence",description:""},
  uiText:key => key, escapeHtml:value => String(value), formatPounds:value => `GBP ${value}`,
  activeUiLocale:() => "en-GB", activityHead:(title,summary,count,extra,action) => `<header>${action}</header>`};
vm.createContext(context);
vm.runInContext(`function renderPanel() {${source.slice(start,end)}}`, context);
for (const mode of ["random","specific","obtained"]) {
  app.intelligenceMode = mode;
  app.matchIntelligenceLoading = true;
  app.matchIntelligenceError = "";
  const searching = context.renderPanel();
  assert.ok(searching.includes(mode === "random" ? "GBP 40000000" : "Saved home"), `${mode} must preserve results while searching`);
  assert.match(searching, /data-intelligence-search[^>]*disabled/, "search must prevent duplicate requests");
  for (const button of searching.matchAll(/<button[^>]*data-intelligence-(?:purchase|random)[^>]*>/g)) {
    assert.ok(button[0].includes("disabled"), "purchases must wait for the current search");
  }
  app.matchIntelligenceLoading = false;
  app.matchIntelligenceError = "Search failed";
  const failed = context.renderPanel();
  assert.ok(failed.includes(mode === "random" ? "GBP 40000000" : "Saved home"), `${mode} must preserve results after failure`);
  assert.ok(failed.includes("Search failed"), "the retained list must show the failed search feedback");
}
'''
    result = subprocess.run(
        ["node", "-e", script, str(root)],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_intelligence_reload_preserves_results_and_rejects_another_save():
    root = Path(__file__).resolve().parents[1] / "src"
    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const source = fs.readFileSync(process.argv[1] + "/web/app.js", "utf8");
const start = source.indexOf("async function loadMatchIntelligence(");
const end = source.indexOf("async function loadRetirementPlayers(", start);
assert.ok(start >= 0 && end > start);
const old = {candidates:[{fixture_id:"kept"}]};
const app = {state:{data_scope_id:"save-a"}, page:"activity", activityFloor:"intelligence",
  matchIntelligence:old, matchIntelligenceLoading:false, matchIntelligenceError:"", activityActionBusy:false};
const pending = [];
let click;
const context = {app, uiText:key => key, renderActivity:() => {},
  document:{querySelectorAll:selector => {
    assert.equal(selector, "[data-intelligence-refresh]");
    return [{addEventListener:(type, handler) => {assert.equal(type, "click"); click = handler;}}];
  }},
  request:path => {
    assert.equal(path, "/api/activity/intelligence");
    return new Promise((resolve,reject) => pending.push({resolve,reject}));
  }};
vm.createContext(context);
vm.runInContext(source.slice(start,end), context);
const bindingStart = source.indexOf('  document.querySelectorAll("[data-intelligence-refresh]")');
const bindingEnd = source.indexOf('  document.querySelectorAll(', bindingStart + 3);
vm.runInContext(source.slice(bindingStart,bindingEnd), context);
(async () => {
  const first = context.loadMatchIntelligence(true);
  click();
  assert.equal(app.matchIntelligence, old, "reload must keep the visible projection");
  assert.equal(app.matchIntelligenceLoading, true);
  await context.loadMatchIntelligence(true);
  assert.equal(pending.length, 1, "reload must be single-flight");
  pending[0].reject(new Error("Reload failed"));
  await first;
  assert.equal(app.matchIntelligence, old);
  assert.equal(app.matchIntelligenceError, "Reload failed");
  assert.equal(app.matchIntelligenceLoading, false);
  const stale = context.loadMatchIntelligence(true);
  app.state.data_scope_id = "save-b";
  app.matchIntelligence = null;
  pending[1].resolve(old);
  await stale;
  assert.equal(app.matchIntelligence, null, "another save cannot receive the old reload");
  assert.equal(app.matchIntelligenceError, "");
  assert.equal(app.matchIntelligenceLoading, false);
  app.activityActionBusy = true;
  await context.loadMatchIntelligence(true);
  assert.equal(pending.length, 2, "reload must wait for an active purchase");
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
    result = subprocess.run(
        ["node", "-e", script, str(root)],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("has_projection", [True, False], ids=["previous-day-projection", "first-load"])
def test_failed_automatic_intelligence_reload_waits_for_an_explicit_retry(has_projection):
    root = Path(__file__).resolve().parents[1] / "src"
    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const source = fs.readFileSync(process.argv[1] + "/web/app.js", "utf8");
const handlerStart = source.indexOf("async function refreshMatchIntelligence()");
const handlerEnd = source.indexOf("async function loadRetirementPlayers(", handlerStart);
const gateStart = source.indexOf("  const intelligencePricingDate = ", source.indexOf("function renderActivity()"));
const gateEnd = source.indexOf("  const activityPlayers = ", gateStart);
assert.ok(handlerStart >= 0 && handlerEnd > handlerStart && gateStart >= 0 && gateEnd > gateStart);
const old = process.argv[2] === "true"
  ? {pricing:{game_date:"2026-10-25"}, candidates:[{fixture_id:"kept"}]}
  : null;
const app = {state:{data_scope_id:"save-a", welfare:{activity_centres:{intelligence:{owned:true}}}},
  gameClock:{date:"2026-10-26"}, page:"activity", activityFloor:"intelligence",
  matchIntelligence:old, matchIntelligenceLoading:false, matchIntelligenceError:"", activityActionBusy:false};
const timers = [], pending = [];
let search;
const context = {app, uiText:key => key, toast:() => {},
  output:() => ({}), setTimeout:callback => timers.push(callback),
  document:{querySelectorAll:selector => {
    assert.equal(selector, "[data-intelligence-search]");
    return [{addEventListener:(type, handler) => {assert.equal(type,"click"); search = handler;}}];
  }},
  request:(path, options) => new Promise((resolve,reject) => pending.push({path,options,resolve,reject}))};
vm.createContext(context);
vm.runInContext(source.slice(handlerStart,handlerEnd), context);
// Exercise the production render gate rather than reproducing its conditions.
vm.runInContext(`function renderActivity() {
  const centreState = app.state.welfare.activity_centres;
  const gameDate = String(app.gameClock.date);
  ${source.slice(gateStart,gateEnd)}
}`, context);
const binding = source.split("\n").find(line => line.includes('document.querySelectorAll("[data-intelligence-search]")'));
vm.runInContext(binding, context);
(async () => {
  context.renderActivity();
  assert.equal(timers.length, 1, "opening stale or unread intelligence starts one automatic reload");
  for (let attempt = 0; attempt < 5 && timers.length; attempt++) {
    const task = timers.shift()();
    assert.equal(app.matchIntelligenceLoading, true);
    const request = pending[pending.length - 1];
    assert.equal(request.path, "/api/activity/intelligence");
    request.reject(new Error("Reload failed"));
    await task;
  }
  assert.equal(pending.length, 1, "a failed automatic reload must stop instead of rescheduling itself");
  assert.equal(timers.length, 0);
  assert.equal(app.matchIntelligenceLoading, false);
  assert.equal(app.matchIntelligenceError, "Reload failed");
  assert.equal(app.matchIntelligence, old, "the existing projection must survive the failed reload");
  for (let render = 0; render < 3; render++) context.renderActivity();
  assert.equal(timers.length, 0, "later renders must continue to wait for an explicit retry");

  const failedRetry = search();
  assert.equal(pending.length, 2, "the search button must remain usable after the automatic failure");
  assert.equal(pending[1].path, "/api/activity/intelligence/refresh");
  assert.equal(JSON.parse(pending[1].options.body).data_scope_id, "save-a");
  pending[1].reject(new Error("Search failed"));
  await failedRetry;
  assert.equal(app.matchIntelligence, old);
  assert.equal(app.matchIntelligenceError, "Search failed");
  assert.equal(app.matchIntelligenceLoading, false);
  assert.equal(timers.length, 0, "a failed explicit retry must not restart automatic requests");

  const retry = search();
  const fresh = {pricing:{game_date:"2026-10-26"},candidates:[{fixture_id:"fresh"}]};
  pending[2].resolve({data_scope_id:"save-a",intelligence:fresh});
  await retry;
  assert.equal(app.matchIntelligence, fresh);
  assert.equal(app.matchIntelligenceError, "");
  assert.equal(app.matchIntelligenceLoading, false);
  assert.equal(timers.length, 0);
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
    result = subprocess.run(
        ["node", "-e", script, str(root), str(has_projection).lower()],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
