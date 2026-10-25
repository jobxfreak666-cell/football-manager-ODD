"""Exercise the manual intelligence search with deferred requests, without FM."""
from pathlib import Path
import subprocess


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
