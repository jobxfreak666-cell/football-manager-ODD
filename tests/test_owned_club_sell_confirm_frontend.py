"""Sell confirmation must run the real frontend function, once, in the current scope."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = (Path(__file__).resolve().parents[1] / "src")


def function_source(start, end):
    script = (ROOT / "web/app.js").read_text(encoding="utf-8")
    return start + script.split(start, 1)[1].split(end, 1)[0]


def sell_source():
    script = (ROOT / "web/app.js").read_text(encoding="utf-8")
    parts = [function_source("function beginOwnedClubOperation(", "async function runOwnedClubOperation")]
    marker = "function ownedClubPortfolioDisplayName("
    if marker in script:
        parts.insert(0, function_source(marker, "async function sellOwnedClub"))
    parts.append(function_source("async function sellOwnedClub", "async function repayOwnedClubDebt"))
    return "\n".join(parts)


def run_js(source):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the isolated frontend harness")
    result = subprocess.run(
        [node, "-"], input="const assert = require('node:assert/strict');\n" + source,
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


HARNESS = r'''
const posts = [];
const confirms = [];
let confirmImpl = async () => true;
let requestImpl = async () => ({acquired:[{id:99}], sale_price:250, economy:{wallet:1}});
const applied = [];
const toasts = [];
const uiText = (key, vars = {}) => key === "portfolio.sell.confirm"
  ? `SELL ${vars.club} ${vars.amount}` : key;
const formatFullMoney = (value) => `GBP${value}`;
const ownedClubSalePrice = () => 250;
const escapeHtml = (value) => String(value);
const renderIcons = () => {};
const clearOwnedClubDetailCache = () => {};
const rebuildOwnedClubPortfolioSummaryFromCache = () => {
  const clubs = app.worldClubs?.acquired || [];
  app.ownedClubPortfolioSummary = {club_count:clubs.length};
  applied.push("summary");
};
const applyEconomySnapshot = (economy) => applied.push(["economy", economy]);
const renderBank = () => applied.push("bank");
const renderMyClubs = () => applied.push("render");
const toast = (message) => toasts.push(message);
const runOwnedClubOperation = async (_button, _label, task) => task();
const stateLoads = [];
const worldClubLoads = [];
const loadOrder = [];
let loadStateImpl = async () => {};
let loadWorldClubsImpl = async () => {};
const loadState = async (options) => {
  stateLoads.push(options || {});
  loadOrder.push("state");
  return loadStateImpl(options);
};
const loadWorldClubs = async (options) => {
  worldClubLoads.push(options || {});
  loadOrder.push("world-clubs");
  return loadWorldClubsImpl(options);
};
function makeButton() {
  return {
    dataset:{}, disabled:false, innerHTML:"<span>Sell</span>", isConnected:true,
    setAttribute() {}, removeAttribute() {},
  };
}
function clubRecord() {
  return {
    id:10, name:"NAC FC", renamed_short_name:"North London",
    ownership_active:true, portfolio_metrics:{sale_price:250},
  };
}
let app;
function makeApp() {
  app = {
    state:{data_scope_id:"scope-a"},
    worldClubsRequestKey:0,
    worldClubs:{acquired:[clubRecord()], group_name:"My Group"},
    ownedClubMetrics:new Map([[10, {sale_price:250}]]),
    ownedClubMetricsVersion:0,
    ownedClubOperationsInFlight:new Set(),
  };
  return app;
}
const fmoddConfirm = (...args) => { confirms.push(args); return confirmImpl(...args); };
const request = (...args) => { posts.push(args); return requestImpl(...args); };
'''


def test_sell_confirm_uses_card_name_title_and_ignores_cancel():
    run_js(HARNESS + sell_source() + r'''
    (async () => {
      makeApp();
      confirmImpl = async () => false;
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 0);
      assert.equal(confirms.length, 1);
      const [message, confirmLabel, title] = confirms[0];
      assert.equal(message, "SELL North London GBP250");
      assert.equal(confirmLabel, "portfolio.sell.title");
      assert.equal(title, "portfolio.sell.title");
      assert.equal(app.ownedClubOperationsInFlight.size, 0);
      assert.equal(toasts.length, 0);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')


def test_sell_confirm_and_post_reject_repeat_clicks():
    run_js(HARNESS + sell_source() + r'''
    (async () => {
      makeApp();
      let releaseConfirm;
      confirmImpl = () => new Promise(resolve => { releaseConfirm = resolve; });
      const first = sellOwnedClub(10, makeButton());
      const second = sellOwnedClub(10, makeButton());
      await Promise.resolve();
      assert.equal(confirms.length, 1);
      releaseConfirm(false);
      await first;
      await second;
      assert.equal(posts.length, 0);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);

      let releasePost;
      confirmImpl = async () => true;
      requestImpl = () => new Promise(resolve => { releasePost = resolve; });
      const posting = sellOwnedClub(10, makeButton());
      for (let attempt = 0; attempt < 5 && posts.length === 0; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      const confirmsAtPost = confirms.length;
      const repeated = sellOwnedClub(10, makeButton());
      await Promise.resolve();
      assert.equal(confirms.length, confirmsAtPost);
      assert.equal(posts.length, 1);
      assert.equal(posts[0][0], "/api/world-clubs/sell");
      assert.equal(posts[0][1].method, "POST");
      assert.equal(JSON.parse(posts[0][1].body).team_id, 10);
      releasePost({acquired:[{id:99}], sale_price:250, economy:{wallet:1}});
      await posting;
      await repeated;
      assert.equal(posts.length, 1);
      assert.equal(app.worldClubs.acquired[0].id, 99);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')


def test_sell_does_not_post_or_apply_after_scope_or_ownership_changes():
    run_js(HARNESS + sell_source() + r'''
    (async () => {
      makeApp();
      const button = makeButton();
      confirmImpl = async () => {
        app.state.data_scope_id = "scope-b";
        return true;
      };
      await sellOwnedClub(10, button);
      assert.equal(posts.length, 0);
      assert.equal(app.worldClubs.acquired[0].id, 10);
      assert.equal(button.disabled, false);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);

      app.state.data_scope_id = "scope-a";
      confirmImpl = async () => {
        app.worldClubs.acquired = [];
        return true;
      };
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 0);

      app.worldClubs.acquired = [clubRecord()];
      confirmImpl = async () => true;
      requestImpl = async () => {
        app.state.data_scope_id = "scope-c";
        app.worldClubs = {acquired:[{id:77, name:"Kept"}], group_name:"New"};
        return {acquired:[{id:1}], sale_price:999, economy:{wallet:5}};
      };
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 1);
      assert.equal(app.worldClubs.acquired[0].id, 77);
      assert.equal(app.ownedClubMetrics.has(10), true);
      assert.deepEqual(applied, []);
      assert.equal(toasts.length, 0);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')


def test_sell_reuses_real_world_clubs_request_key():
    script = (ROOT / "web/app.js").read_text(encoding="utf-8")
    reset = script.split("function resetAccountScopedWorldState() {", 1)[1].split(
        "async function loadStateOnce", 1,
    )[0]
    assert "app.worldClubsRequestKey += 1" in reset
    assert "app.worldClubs = null" in reset
    load = script.split("async function loadWorldClubs(", 1)[1].split(
        "function ownedClubPortfolioDisplayName(", 1,
    )[0]
    assert "const requestKey = ++app.worldClubsRequestKey" in load


def test_sell_rejects_replaced_ownership_inactive_row_and_request_key_change():
    run_js(HARNESS + sell_source() + r'''
    (async () => {
      makeApp();
      assert.equal(app.worldClubsRequestKey, 0);
      const original = app.worldClubs.acquired[0];
      confirmImpl = async () => {
        app.worldClubs.acquired = [clubRecord()];
        return true;
      };
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 0);
      assert.equal(toasts.length, 0);
      assert.deepEqual(applied, []);
      assert.equal(app.worldClubs.acquired[0].id, 10);
      assert.notEqual(app.worldClubs.acquired[0], original);

      app.worldClubs.acquired = [original];
      original.ownership_active = true;
      confirmImpl = async () => {
        original.ownership_active = false;
        return true;
      };
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 0);
      assert.equal(toasts.length, 0);
      assert.deepEqual(applied, []);

      original.ownership_active = true;
      app.state.data_scope_id = "scope-a";
      confirmImpl = async () => {
        app.state.data_scope_id = "scope-b";
        app.worldClubsRequestKey += 1;
        app.state.data_scope_id = "scope-a";
        return true;
      };
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 0);
      assert.equal(toasts.length, 0);
      assert.deepEqual(applied, []);
      assert.equal(app.worldClubs.acquired[0], original);

      app.worldClubsRequestKey = 4;
      confirmImpl = async () => true;
      requestImpl = async () => {
        app.state.data_scope_id = "scope-b";
        app.worldClubsRequestKey += 1;
        app.state.data_scope_id = "scope-a";
        return {acquired:[{id:1}], sale_price:999, economy:{wallet:5}};
      };
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 1);
      assert.equal(app.worldClubs.acquired[0], original);
      assert.equal(app.ownedClubMetrics.has(10), true);
      assert.equal(toasts.length, 0);
      assert.equal(applied.some((item) => Array.isArray(item) && item[0] === "economy"), false);
      assert.deepEqual(stateLoads, [{fresh:true}]);
      assert.equal(worldClubLoads.length, 1);

      posts.length = 0;
      stateLoads.length = 0;
      worldClubLoads.length = 0;
      applied.length = 0;
      app.worldClubsRequestKey = 4;
      requestImpl = async () => {
        app.worldClubsRequestKey += 1;
        throw new Error("stale sell");
      };
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 1);
      assert.equal(toasts.length, 0);
      assert.equal(app.worldClubs.acquired[0], original);
      assert.deepEqual(applied, []);

      app.worldClubsRequestKey = 0;
      app.worldClubs.acquired = [clubRecord()];
      let releasePost;
      const confirmsAtPost = confirms.length;
      confirmImpl = async () => true;
      requestImpl = () => new Promise(resolve => { releasePost = resolve; });
      const posting = sellOwnedClub(10, makeButton());
      for (let attempt = 0; attempt < 5 && posts.length < 2; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      const repeated = sellOwnedClub(10, makeButton());
      await Promise.resolve();
      assert.equal(posts.length, 2);
      assert.equal(confirms.length, confirmsAtPost + 1);
      releasePost({acquired:[{id:99}], sale_price:250, economy:{wallet:1}});
      await posting;
      await repeated;
      assert.equal(posts.length, 2);
      assert.equal(confirms.length, confirmsAtPost + 1);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')


def test_sell_success_refreshes_when_inflight_list_replaces_ownership():
    """POST must not keep a pre-sale list snapshot, or reuse that list promise."""
    run_js(HARNESS + sell_source() + r'''
    (async () => {
      makeApp();
      const listKey = "world-clubs:pre-sale";
      let releaseGet;
      const oldList = new Promise(resolve => { releaseGet = resolve; });
      oldList.finally(() => {
        loadOrder.push("old-list-finally");
        app.pageDataRequests.delete(listKey);
        if (app.worldClubsLoadPromise === oldList) app.worldClubsLoadPromise = null;
      });
      app.pageDataRequests = new Map([[listKey, oldList]]);
      app.worldClubsLoadPromise = oldList;
      app.worldClubsRequestKey = 2;
      app.state.economy = {wallet:100};
      const original = app.worldClubs.acquired[0];
      let releasePost;
      confirmImpl = async () => true;
      requestImpl = () => new Promise(resolve => { releasePost = resolve; });
      loadStateImpl = async () => {
        app.state.economy = {wallet:880};
      };
      loadWorldClubsImpl = async () => {
        const pending = app.pageDataRequests.get(listKey);
        if (pending) {
          loadOrder.push("reused-pending");
          return pending;
        }
        app.worldClubs = {acquired:[], group_name:"My Group"};
        app.worldClubsRequestKey += 1;
        return app.worldClubs;
      };
      const posting = sellOwnedClub(10, makeButton());
      for (let attempt = 0; attempt < 5 && posts.length === 0; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      assert.equal(posts.length, 1);
      releasePost({acquired:[{id:1}], sale_price:999, economy:{wallet:1}});
      await new Promise(resolve => setTimeout(resolve, 0));
      assert.equal(worldClubLoads.length, 0);
      releaseGet("stale-acquired");
      await posting;
      assert.equal(app.worldClubs.acquired.length, 0);
      assert.notEqual(app.worldClubs.acquired[0], original);
      assert.equal(app.state.economy.wallet, 880);
      assert.equal(app.ownedClubMetrics.has(10), false);
      assert.equal(app.ownedClubPortfolioSummary.club_count, 0);
      assert.deepEqual(stateLoads, [{fresh:true}]);
      assert.equal(worldClubLoads.length, 1);
      assert.equal(loadOrder.includes("reused-pending"), false);
      assert.ok(loadOrder.indexOf("old-list-finally") < loadOrder.indexOf("state"));
      assert.ok(loadOrder.indexOf("old-list-finally") < loadOrder.indexOf("world-clubs"));
      assert.equal(applied.some(item => Array.isArray(item) && item[0] === "economy"), false);
      assert.equal(toasts.length, 0);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);

      makeApp();
      stateLoads.length = 0;
      worldClubLoads.length = 0;
      loadOrder.length = 0;
      applied.length = 0;
      posts.length = 0;
      let releaseLateGet;
      const lateList = new Promise(resolve => { releaseLateGet = resolve; });
      app.pageDataRequests = new Map([[listKey, lateList]]);
      app.worldClubsLoadPromise = lateList;
      confirmImpl = async () => true;
      requestImpl = () => new Promise(resolve => { releasePost = resolve; });
      const switched = sellOwnedClub(10, makeButton());
      for (let attempt = 0; attempt < 5 && posts.length === 0; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      releasePost({acquired:[{id:1}], sale_price:999, economy:{wallet:5}});
      await new Promise(resolve => setTimeout(resolve, 0));
      releaseLateGet();
      app.state.data_scope_id = "scope-b";
      app.worldClubs = {acquired:[{id:77, name:"Kept"}], group_name:"New"};
      await switched;
      assert.equal(app.worldClubs.acquired[0].id, 77);
      assert.equal(app.state.economy, undefined);
      assert.equal(stateLoads.length, 0);
      assert.equal(worldClubLoads.length, 0);
      assert.equal(applied.some(item => Array.isArray(item) && item[0] === "economy"), false);
      assert.equal(toasts.length, 0);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')


def test_sell_failure_restores_button_and_flight_state():
    run_js(HARNESS + sell_source() + r'''
    (async () => {
      makeApp();
      const button = makeButton();
      confirmImpl = async () => true;
      requestImpl = async () => { throw new Error("sell failed"); };
      await sellOwnedClub(10, button);
      assert.equal(posts.length, 1);
      assert.equal(button.disabled, false);
      assert.equal(button.dataset.ownedBusy, undefined);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);
      assert.equal(app.worldClubs.acquired[0].id, 10);
      assert.deepEqual(toasts, ["sell failed"]);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    ''')
