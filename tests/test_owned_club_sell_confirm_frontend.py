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
let loadWorldClubsImpl = async () => {
  app.worldClubs = {...app.worldClubs};
  return app.worldClubs;
};
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
    dataset:{}, disabled:false, innerHTML:"<span>Sell</span>", isConnected:true, focusCount:0,
    setAttribute() {}, removeAttribute() {}, focus() { this.focusCount += 1; },
  };
}
const dialogClasses = new Set();
const confirmDialog = {classList:{
  add:(name) => dialogClasses.add(name),
  remove:(name) => dialogClasses.delete(name),
  contains:(name) => dialogClasses.has(name),
}};
const $ = (selector) => selector === "#fmodd-confirm-dialog" ? confirmDialog : null;
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
    ownedClubSalesAwaitingSync:new Map(),
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
      assert.deepEqual(toasts, ["portfolio.sell.stale"]);
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
      assert.deepEqual(toasts, ["portfolio.sell.stale"]);
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
      assert.deepEqual(toasts, ["portfolio.sell.stale", "portfolio.sell.stale"]);
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
      assert.equal(toasts.length, 3);
      assert.equal(toasts[2], "portfolio.sell.stale");
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
      assert.equal(app.ownedClubMetrics.has(10), false);
      assert.equal(toasts.length, 4);
      assert.equal(toasts[3], "portfolio.sell.done");
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
      assert.equal(toasts.length, 4);
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
      assert.deepEqual(toasts, ["portfolio.sell.done"]);
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
      assert.deepEqual(toasts, ["portfolio.sell.done"]);
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


def test_sell_button_stays_idle_and_dialog_is_danger_while_confirm_is_open():
    run_js(HARNESS + sell_source() + r"""
    (async () => {
      makeApp();
      const button = makeButton();
      let releaseConfirm;
      confirmImpl = () => new Promise(resolve => { releaseConfirm = resolve; });
      const selling = sellOwnedClub(10, button);
      await Promise.resolve();
      assert.equal(button.disabled, false);
      assert.equal(button.dataset.ownedBusy, undefined);
      assert.equal(button.innerHTML, "<span>Sell</span>");
      assert.equal(confirmDialog.classList.contains("is-danger"), true);
      let busyWhilePosting = null;
      requestImpl = async () => {
        busyWhilePosting = button.disabled;
        return {acquired:[], sale_price:250, economy:{wallet:1}};
      };
      releaseConfirm(true);
      await selling;
      assert.equal(confirmDialog.classList.contains("is-danger"), false);
      assert.equal(busyWhilePosting, true);
      assert.deepEqual(toasts, ["portfolio.sell.done"]);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    """)


def test_sell_cancel_returns_focus_and_clears_danger_style():
    run_js(HARNESS + sell_source() + r"""
    (async () => {
      makeApp();
      const button = makeButton();
      confirmImpl = async () => false;
      await sellOwnedClub(10, button);
      assert.equal(button.focusCount, 1);
      assert.equal(confirmDialog.classList.contains("is-danger"), false);
      assert.equal(button.disabled, false);

      confirmImpl = async () => { throw new Error("dialog failed"); };
      const other = makeButton();
      await sellOwnedClub(10, other);
      assert.equal(confirmDialog.classList.contains("is-danger"), false);
      assert.equal(other.focusCount, 1);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    """)


@pytest.mark.parametrize("failure", ["state", "state-false", "list-null", "list-throw"])
def test_completed_sale_blocks_resale_until_read_only_sync_succeeds(failure):
    run_js(HARNESS + sell_source() + r"""
    (async () => {
      makeApp();
      const failure = FAILURE;
      const original = app.worldClubs.acquired[0];
      confirmImpl = async () => true;
      requestImpl = async () => {
        app.worldClubsRequestKey += 1;
        return {acquired:[], sale_price:250, economy:{wallet:1}};
      };
      loadStateImpl = async () => {
        if (failure === "state") throw new Error("state failed");
        return failure !== "state-false";
      };
      loadWorldClubsImpl = async () => {
        if (failure === "list-throw") throw new Error("list failed");
        return null;
      };
      await sellOwnedClub(10, makeButton());
      assert.deepEqual(toasts, ["portfolio.sell.sync_failed"]);
      assert.equal(ownedClubSalePendingSync(10), true);
      assert.equal(app.ownedClubMetrics.has(10), false);
      // Keep the raw snapshot intact; the portfolio excludes this confirmed sale.
      assert.equal(app.worldClubs.acquired[0], original);
      await sellOwnedClub(10, makeButton());
      assert.equal(posts.length, 1);
      assert.equal(confirms.length, 1);
      loadStateImpl = async () => {};
      loadWorldClubsImpl = async () => {
        app.worldClubs = {acquired:[], group_name:"My Group"};
        return app.worldClubs;
      };
      await retryOwnedClubSaleSync();
      assert.equal(posts.length, 1);
      assert.equal(ownedClubSalePendingSync(10), false);
      assert.equal(app.ownedClubOperationsInFlight.size, 0);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    """.replace("FAILURE", repr(failure)))


def test_pending_sale_is_excluded_from_cached_portfolio_without_overwriting_ownership():
    index_source = function_source("function ownedClubDataIndex()", "function saveOwnedClubOrder")
    run_js(HARNESS + sell_source() + index_source + r"""
    const localStorage = {getItem:() => "[]"};
    const ownedClubOrderStorageKey = () => "order";
    const output = () => ({});
    makeApp();
    app.ownedClubIndexVersion = 0;
    const original = app.worldClubs.acquired[0];
    const before = ownedClubDataIndex();
    assert.equal(before.active.length, 1);
    app.ownedClubSalesAwaitingSync.set(10, {scope:"scope-a"});
    const pending = ownedClubDataIndex();
    assert.equal(pending.ordered.length, 0);
    assert.equal(pending.active.length, 0);
    assert.equal(app.worldClubs.acquired[0], original);
    assert.equal(ownedClubDataIndex(), pending);
    // A different account must never inherit the sale marker.
    app.state.data_scope_id = "scope-b";
    assert.equal(ownedClubDataIndex().active.length, 1);
    """)


def test_sale_sync_keeps_marker_on_discarded_read_and_preserves_fresh_reacquisition():
    run_js(HARNESS + sell_source() + r"""
    (async () => {
      makeApp();
      app.ownedClubSalesAwaitingSync.set(10, {scope:"scope-a"});
      const original = app.worldClubs;
      loadWorldClubsImpl = async () => original;
      await retryOwnedClubSaleSync();
      assert.equal(ownedClubSalePendingSync(10), true);
      assert.deepEqual(toasts, ["portfolio.sell.sync_failed"]);
      const reacquired = {...clubRecord(), acquired_at:"later"};
      loadWorldClubsImpl = async () => {
        app.worldClubs = {acquired:[reacquired]};
        return app.worldClubs;
      };
      await retryOwnedClubSaleSync();
      assert.equal(ownedClubSalePendingSync(10), false);
      assert.equal(app.worldClubs.acquired[0], reacquired);
      assert.equal(posts.length, 0);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    """)


def test_sale_sync_double_retry_and_account_switch_do_not_touch_new_account():
    run_js(HARNESS + sell_source() + r"""
    (async () => {
      makeApp();
      app.ownedClubSalesAwaitingSync.set(10, {scope:"scope-a"});
      let releaseState;
      loadStateImpl = () => new Promise(resolve => { releaseState = resolve; });
      const first = retryOwnedClubSaleSync();
      const second = retryOwnedClubSaleSync();
      for (let attempt = 0; attempt < 5 && !releaseState; attempt += 1) await Promise.resolve();
      assert.equal(stateLoads.length, 1);
      app.state.data_scope_id = "scope-b";
      app.ownedClubSalesAwaitingSync.clear();
      const newSale = {scope:"scope-b"};
      app.ownedClubSalesAwaitingSync.set(10, newSale);
      app.ownedClubSaleSyncLoading = null;
      app.worldClubs = {acquired:[{id:77}]};
      const renderCount = applied.length;
      releaseState();
      await first;
      await second;
      assert.equal(worldClubLoads.length, 0);
      assert.equal(posts.length, 0);
      assert.equal(app.worldClubs.acquired[0].id, 77);
      assert.equal(app.ownedClubSalesAwaitingSync.get(10), newSale);
      assert.equal(applied.length, renderCount);
      assert.deepEqual(toasts, []);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    """)


def test_metrics_started_before_sale_cannot_restore_sold_cache_or_group_totals():
    metrics_source = function_source("async function performOwnedClubMetricsLoad", "async function loadOwnedClubMetrics")
    run_js(HARNESS + sell_source() + metrics_source + r"""
    const activeOwnedClubs = () => app.worldClubs.acquired.filter(club => !ownedClubSalePendingSync(club.id));
    (async () => {
      makeApp();
      app.ownedClubMetricsScope = "scope-a";
      app.ownedClubMetricsRequestKey = 0;
      let releaseMetrics;
      requestImpl = async path => {
        if (path.startsWith("/api/world-clubs/metrics")) return new Promise(resolve => {releaseMetrics=resolve;});
        return {acquired:[], sale_price:250};
      };
      const reading = performOwnedClubMetricsLoad({force:true});
      await sellOwnedClub(10, makeButton());
      assert.equal(ownedClubSalePendingSync(10), false);
      assert.equal(app.ownedClubPortfolioSummary.club_count, 0);
      releaseMetrics({data_scope_id:"scope-a", metrics:{10:{balance:999}}, summary:{club_count:1,balance:999}});
      await reading;
      assert.equal(app.ownedClubMetrics.has(10), false);
      assert.equal(app.ownedClubPortfolioSummary.club_count, 0);
      assert.equal(app.ownedClubMetricsLoading, false);
    })().catch(error => {console.error(error);process.exitCode=1;});
    """)
