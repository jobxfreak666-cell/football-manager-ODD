"""Keep a confirmed counselling purchase completed when its UI refresh fails."""

from __future__ import annotations

import json
import subprocess

import pytest

from frontend_source import raw_web_source


def _run_counselling_case(case: str, locale: str) -> None:
    source = raw_web_source("web/app.js")
    start = source.index("async function runCounseling(playerId)")
    end = source.index("async function startCounseling", start)
    payload = {
        "source": source[start:end],
        "controls": source[source.index("function updateCounselingWheelControls()"):start],
        "batch_action": source[source.index("async function counselAllRemaining()"):source.index("function settleCounselingWheel(")],
        "catalog": raw_web_source("web/i18n.facilities.js"),
        "case": case,
        "locale": locale,
    }
    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const id = 7;
const oldEconomy = {wallet:{balance:500000}}, oldWelfare = {version:"old"};
const freshEconomy = {wallet:{balance:400000}}, freshWelfare = {version:"fresh"};
const counselling = {player_id:id, player_name:"Alex", intimacy:3,
  effect:{effects:[{field:"morale", after:17}]}};
const payment = {wallet:100000, total:100000};
const blockedCase = input.case.startsWith("blocked-");
const retryableCase = input.case.startsWith("retryable-");
const response = {counseling:counselling, payment, economy:freshEconomy, welfare:freshWelfare};
if (input.case.startsWith("partial-")) {
  response.state_refresh_required = true;
  if (input.case !== "partial-economy") delete response.economy;
  if (input.case !== "partial-welfare") delete response.welfare;
}
const classes = new Set(["ready"]), notices = [], settlements = [], updates = [], requests = [];
const startButton = {disabled:false, textContent:"Start", innerHTML:"Start"};
const note = {textContent:""};
const card = {classList:{add:(...names) => names.forEach(name => classes.add(name)),
  remove:(...names) => names.forEach(name => classes.delete(name))},
  dataset:{counselingWheelPlayer:String(id)},
  querySelector:selector => selector === "[data-counseling-start]" ? startButton : note};
const otherClasses = new Set(["ready"]), otherStart = {disabled:false}, otherNote = {textContent:""};
const otherCard = {classList:{add:(...names) => names.forEach(name => otherClasses.add(name)),
  remove:(...names) => names.forEach(name => otherClasses.delete(name))},
  dataset:{counselingWheelPlayer:"8"},
  querySelector:selector => selector === "[data-counseling-start]" ? otherStart : otherNote};
const autoLabel = {textContent:""}, auto = {disabled:false, querySelector:() => autoLabel};
const confirmations = [];
const batch = {players:new Map([[id,{id, name:"Alex"}]]), running:new Set(), completed:new Set()};
if (blockedCase) batch.players.set(8, {id:8, name:"Sam"});
const app = {state:{economy:oldEconomy, welfare:oldWelfare}, counselingWheelBatch:batch};
const context = {app, window:{FMODDI18nModules:[]},
  document:{querySelector:selector => selector.includes('"8"') ? otherCard : card,
    querySelectorAll:() => [[card, classes], [otherCard, otherClasses]]
      .filter(([row, names]) => batch.players.has(Number(row.dataset.counselingWheelPlayer)) && names.has("ready"))
      .map(([row]) => row)},
  $:selector => selector === "#counseling-wheel-auto" ? auto : {disabled:false},
  managedPlayerTeamId:() => 12,
  renderIcons:() => {}, counselingCanAfford:() => true,
  fmoddConfirm:async message => {confirmations.push(message); return true;},
  counselingPrice:() => 100000, formatPounds:value => String(value),
  toast:message => notices.push(message),
  request:async (path, options) => {
    assert.equal(path, "/api/activity/counseling");
    assert.equal(options.method, "POST");
    const targetId = JSON.parse(options.body).player_id;
    assert.deepEqual(JSON.parse(options.body), {player_id:targetId, team_id:12});
    assert.ok(batch.players.has(targetId));
    requests.push(options);
    if (requests.length === 1 && (input.case === "post-failure" || blockedCase || retryableCase || input.case === "validation-failure")) {
      const error = new Error("Payment refused");
      error.code = input.case === "validation-failure" ? "invalid_request" : input.case.split("-")[1];
      error.retryable = retryableCase;
      throw error;
    }
    return response;
  },
  applyEconomySnapshot:economy => {
    assert.ok(economy, "a missing economy view must not clear the previous snapshot");
    if (input.case === "throw-economy") throw new Error("Economy render failed");
    app.state.economy = economy;
  },
  updateManagedPlayer:(playerId, changes) => {
    assert.ok(batch.players.has(playerId));
    if (input.case === "throw-player") throw new Error("Roster render failed");
    updates.push(changes);
  },
  settleCounselingWheel:(playerId, result, error, paid) => {
    settlements.push({playerId, result, error, paid});
    if (input.case === "throw-settlement") throw new Error("Result render failed");
    if (error) notices.push(error);
  },
};
vm.createContext(context);
vm.runInContext(input.catalog, context, {filename:"i18n.facilities.js"});
const messages = context.window.FMODDI18nModules[0].messages[input.locale];
context.uiText = (key, params = {}) => (messages[key] || key)
  .replace(/\{(\w+)\}/g, (match, name) => params[name] ?? match);
vm.runInContext(input.controls + input.batch_action, context, {filename:"app.js:counselling-controls"});
vm.runInContext(input.source, context, {filename:"app.js:runCounseling"});
const syncNotice = input.locale === "zh-CN"
  ? "辅导已完成，状态同步失败，请刷新查看。"
  : "Counselling completed, but state could not be synced. Refresh to view it.";
const reviewNotice = input.locale === "zh-CN"
  ? "结果或退款尚待核对，请刷新确认，勿重复支付。"
  : "The result or refund needs checking. Refresh to confirm; do not pay again.";
(async () => {
  await context.runCounseling(id);
  assert.equal(requests.length, 1, "one click must make only one purchase request");
  assert.equal(batch.running.size, 0);
  if (blockedCase) {
    assert.equal(batch.completed.has(id), false, "an uncertain outcome must not be reported as completed");
    assert.ok(batch.blocked?.has(id), "uncertain submission or compensation blocks another payment in this batch");
    assert.equal(classes.has("ready"), false);
    assert.equal(startButton.disabled, true);
    assert.deepEqual(notices, [reviewNotice]);
    await context.runCounseling(id);
    assert.equal(requests.length, 1, "manual invocation cannot repeat the uncertain paid POST");
    classes.add("ready");
    startButton.disabled = false;
    context.updateCounselingWheelControls();
    assert.equal(startButton.disabled, true, "the real control refresh must never re-enable a blocked payment");
    assert.equal(note.textContent, reviewNotice);
    classes.delete("ready");
    assert.equal(auto.disabled, false, "other unsubmitted players remain available");
    assert.equal(autoLabel.textContent, context.uiText("activity.counselling_auto_remaining", {count:1, total:"100000"}),
      "the batch quote excludes the blocked player");
    await context.counselAllRemaining();
    assert.deepEqual(requests.map(options => JSON.parse(options.body).player_id), [id, 8],
      "the real batch action must skip the blocked player");
    assert.equal(batch.completed.has(id), false);
    assert.ok(batch.completed.has(8));
    assert.equal(auto.disabled, true);
    assert.equal(autoLabel.textContent, reviewNotice, "an unresolved batch must not claim everyone was counselled");
    return;
  }
  if (input.case === "post-failure" || retryableCase || input.case === "validation-failure") {
    assert.equal(batch.completed.has(id), false, "a rejected payment is not completed");
    assert.ok(classes.has("ready"), "a rejected payment keeps the existing manual retry");
    assert.equal(startButton.disabled, false);
    assert.equal(batch.blocked?.has(id) || false, false, "ordinary validation failure or explicit retryability must not be blocked");
    assert.equal(app.state.economy, oldEconomy);
    assert.equal(app.state.welfare, oldWelfare);
    assert.deepEqual(notices, ["Payment refused"]);
    assert.equal(settlements[0].result, null);
    await context.runCounseling(id);
    assert.equal(requests.length, 2, "manual retry remains available after request failure");
    assert.ok(batch.completed.has(id));
    return;
  }
  assert.ok(batch.completed.has(id), "a confirmed purchase remains completed");
  assert.equal(classes.has("ready"), false, "a confirmed purchase must not offer another payment");
  assert.equal(startButton.disabled, true);
  await context.runCounseling(id);
  assert.equal(requests.length, 1, "retrying a completed card must not repeat the paid POST");
  assert.ok(settlements.some(entry => entry.result === counselling && !entry.error && entry.paid === payment),
    "keep the confirmed result and payment display even if other UI projection fails");
  assert.ok(settlements.every(entry => !entry.error), "UI sync failure must not report a failed purchase");
  if (input.case.startsWith("partial-") || input.case.startsWith("throw-")) {
    assert.deepEqual(notices, [syncNotice], "explain completion and refresh recovery in the selected locale");
  } else {
    assert.deepEqual(notices, []);
  }
  if (input.case.startsWith("partial-")) {
    assert.equal(app.state.economy, response.economy || oldEconomy);
    assert.equal(app.state.welfare, response.welfare || oldWelfare);
  }
  if (input.case === "normal") {
    assert.equal(app.state.economy, freshEconomy);
    assert.equal(app.state.welfare, freshWelfare);
    assert.equal(updates.length, 1);
    assert.equal(updates[0].manager_intimacy, 3);
    assert.equal(updates[0].has_unhappiness, false);
    assert.equal(updates[0].morale, 17);
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
'''
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("locale", ["en-GB", "zh-CN"])
@pytest.mark.parametrize("case", ["partial-both-missing", "partial-economy", "partial-welfare"])
def test_confirmed_counselling_preserves_missing_views_and_cannot_charge_again(case, locale):
    _run_counselling_case(case, locale)


@pytest.mark.parametrize("locale", ["en-GB", "zh-CN"])
@pytest.mark.parametrize("case", ["throw-economy", "throw-player", "throw-settlement"])
def test_confirmed_counselling_remains_complete_when_ui_projection_throws(case, locale):
    _run_counselling_case(case, locale)


@pytest.mark.parametrize("locale", ["en-GB", "zh-CN"])
def test_normal_counselling_updates_views_effects_and_completes(locale):
    _run_counselling_case("normal", locale)


@pytest.mark.parametrize("locale", ["en-GB", "zh-CN"])
def test_failed_counselling_post_keeps_existing_error_and_manual_retry(locale):
    _run_counselling_case("post-failure", locale)


@pytest.mark.parametrize("locale", ["en-GB", "zh-CN"])
@pytest.mark.parametrize("code", ["commit_unknown", "rollback_incomplete", "refund_incomplete"])
def test_uncertain_counselling_blocks_payment_and_is_excluded_from_real_batch_controls(code, locale):
    _run_counselling_case(f"blocked-{code}", locale)


@pytest.mark.parametrize("case", ["retryable-commit_unknown", "validation-failure"])
def test_counselling_retry_gate_respects_code_and_explicit_retryability(case):
    _run_counselling_case(case, "en-GB")
