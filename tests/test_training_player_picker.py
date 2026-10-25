"""Exercise the equipment-training player picker without a browser or FM."""
from pathlib import Path
import subprocess


def test_equipment_training_player_picker_toggles_inside_its_field():
    root = Path(__file__).resolve().parents[1] / "src"
    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const root = process.argv[1];
const source = fs.readFileSync(root + "/web/app.js", "utf8");
const styles = fs.readFileSync(root + "/web/app.css", "utf8");

// 1. The picker is mounted inside the player field, not at the end of the panel.
const panelStart = source.indexOf("function trainingUsePanel(facility)");
assert.ok(panelStart >= 0, "the equipment training panel must exist");
const panelEnd = source.indexOf("function selectedGameIsFm26()", panelStart);
assert.ok(panelEnd > panelStart);
const panel = source.slice(panelStart, panelEnd);
const panelReturn = panel.slice(panel.indexOf("return `<div class=\"training-use-panel"));
assert.ok(panelReturn.length > 0);
assert.ok(!panelReturn.includes("${playerPickerCard}"),
  "the panel must not mount the player picker outside the player field");
assert.ok(panel.includes("</button>${playerPickerCard}</div>"),
  "the player picker must render inside the player field");

// 2. Rendering the field keeps the list nested in it, and only while open.
const templateStart = source.indexOf("const playerPickerCard = app.trainingPlayerPickerOpen");
assert.ok(templateStart >= 0);
const templateEnd = source.indexOf("const durationOptions = habit ?", templateStart);
assert.ok(templateEnd > templateStart);
const template = source.slice(templateStart, templateEnd);
assert.ok(!template.includes("aria-modal"), "the picker must not render as a modal dialog");

const renderField = (open) => {
  const context = {
    app: {trainingPlayerPickerOpen: open, trainingPlayerSearch: "", trainingRosterLoading: false},
    uiText: (key) => key,
    escapeHtml: (value) => String(value),
    filteredPlayers: [], idleCount: 0, playerRows: "",
    positionFilters: [["all", "all"]], playerPositionFilter: "all",
    selectedPlayer: null, selectedTargetKey: "", selectedTargetSummary: "",
    restrictedPositionLabel: "", disabled: false,
  };
  vm.createContext(context);
  vm.runInContext(template + "\nglobalThis.picker = playerPicker;", context);
  return context.picker;
};

const collapsed = renderField(false);
assert.ok(collapsed.includes('class="training-player-field"'));
assert.ok(collapsed.includes("data-training-player-toggle"));
assert.ok(!collapsed.includes("training-player-picker-layer"),
  "a collapsed picker must not render the candidate list");
assert.ok(collapsed.endsWith("</button></div>"));

const expanded = renderField(true);
assert.ok(expanded.includes('data-training-player-picker-layer'));
assert.ok(expanded.includes('</button><div class="training-player-picker-layer"'),
  "the open list must follow the trigger inside the same player field");
assert.ok(expanded.endsWith("</div></div>"));

// 3. A second click on the trigger collapses the open list.
const toggleStart = source.indexOf("if(playerClose){");
assert.ok(toggleStart >= 0);
const toggleEnd = source.indexOf("if(cancel){", toggleStart);
assert.ok(toggleEnd > toggleStart);
const toggleBlock = source.slice(toggleStart, toggleEnd).trimEnd();

const toggle = {renders: [], frames: 0};
const toggleContext = {
  app: {trainingPlayerPickerOpen: false, trainingPlayerSearch: "x", trainingPlayerPositionFilter: "defenders", trainingPlayerId: 2, trainingPreferredMoves: ["old"]},
  renderTraining: (options) => toggle.renders.push(options),
  requestAnimationFrame: () => { toggle.frames += 1; },
  $: () => null,
};
vm.createContext(toggleContext);
vm.runInContext(
  "globalThis.runToggle = (action) => {"
    + "const playerClose = action === 'close' ? {} : null;"
    + "const playerPosition = action === 'filter' ? {dataset:{trainingPlayerPosition:'goalkeepers'}} : null;"
    + "const playerOption = action === 'select' ? {dataset:{trainingPlayerOption:'71'}} : null;"
    + "const playerToggle = action === 'toggle' ? {} : null; " + toggleBlock + " };",
  toggleContext,
);
const app = toggleContext.app;
toggleContext.runToggle("toggle");
assert.equal(app.trainingPlayerPickerOpen, true);
assert.equal(app.trainingPlayerSearch, "", "opening must reset the search field");
assert.equal(toggle.renders.length, 1);
assert.equal(toggle.renders[0].skipStage, true);
assert.equal(toggle.frames, 1, "opening must focus the search field");
toggleContext.runToggle("toggle");
assert.equal(app.trainingPlayerPickerOpen, false, "a second click on the trigger must collapse the list");
assert.equal(toggle.renders.length, 2);
assert.equal(toggle.frames, 1, "collapsing must not focus the search field");
toggleContext.runToggle("filter");
assert.equal(app.trainingPlayerPositionFilter, "goalkeepers", "a position tab must update the active filter");
assert.equal(toggle.renders.length, 3, "changing the filter must refresh the candidate list");
toggleContext.runToggle("select");
assert.equal(app.trainingPlayerId, 71, "choosing a candidate must retain the chosen player");
assert.equal(app.trainingPlayerPickerOpen, false, "choosing a candidate must close the list");
assert.equal(app.trainingPreferredMoves, null, "changing player must clear player-specific preferred moves");
assert.equal(toggle.renders.length, 4);

// 4. Outside clicks and Escape close only the popup, preserving the active form.
//    This catches both the focused-select render guard and native submit ordering.
const escapeAnchor = source.indexOf('if (event.key !== "Escape" || !app.trainingPlayerPickerOpen) return;');
assert.ok(escapeAnchor >= 0, "Escape must close an open player picker");
const escapeStart = source.lastIndexOf('document.addEventListener("keydown"', escapeAnchor);
const outsideAnchor = source.indexOf('if (!app.trainingPlayerPickerOpen) return;', escapeAnchor);
assert.ok(outsideAnchor > escapeAnchor);
const outsideStart = source.lastIndexOf('document.addEventListener("click"', outsideAnchor);
const listenersEnd = source.indexOf('document.addEventListener("pointerdown"', outsideAnchor);
assert.ok(escapeStart >= 0 && outsideStart > escapeStart && listenersEnd > outsideStart);
const pickerHandlers = source.slice(escapeStart, listenersEnd);
const closeHelperStart = source.lastIndexOf("function closeTrainingPlayerPicker(", escapeStart);
const closeHelper = closeHelperStart >= 0 ? source.slice(closeHelperStart, escapeStart) : "";

function createPickerHarness(focusKind) {
  const listeners = {};
  const documentHandlers = {};
  const initialForm = {id: "training-inline-form"};
  let currentForm = initialForm;
  let layerAttached = true;
  let focusCount = 0;
  const layer = {remove: () => { layerAttached = false; }};
  const trigger = {
    attributes: {"aria-expanded": "true"},
    setAttribute: (name, value) => { trigger.attributes[name] = value; },
    focus: () => { focusCount += 1; },
  };
  const field = {querySelector: (selector) => selector === "[data-training-player-picker-layer]" ? (layerAttached ? layer : null)
    : selector === "[data-training-player-toggle]" ? trigger : null};
  const dock = {
    id: "training-dock-content",
    querySelector: (selector) => selector === ".training-player-field" ? field : null,
    addEventListener: (type, handler) => { listeners[type] = handler; },
  };
  const activeElement = {
    matches: (selector) => focusKind === "select" && selector.includes("select"),
    closest: () => null,
  };
  const app = {
    page: "training", trainingPlayerPickerOpen: true,
    trainingPlayerSearch: "striker", trainingPlayerPositionFilter: "defenders",
    interactiveSurfacePointer: null, _lastDockHash: "expanded",
  };
  const context = {
    app,
    $: (selector) => selector === "#training-dock-content" ? dock : null,
    document: {
      activeElement,
      addEventListener: (type, handler) => { documentHandlers[type] = handler; },
    },
    renderTraining: () => {
      if (app.interactiveSurfacePointer === dock.id || activeElement.matches("select, .fmodd-select-trigger")) return;
      currentForm = {id: "training-inline-form", replaced: true};
      layerAttached = app.trainingPlayerPickerOpen;
      trigger.attributes["aria-expanded"] = String(app.trainingPlayerPickerOpen);
    },
    requestAnimationFrame: (callback) => callback(),
    submitInlineTraining: async (form) => { context.submittedForm = form; },
  };
  vm.createContext(context);
  vm.runInContext(closeHelper + pickerHandlers, context);
  const submitAnchor = source.indexOf('$("#training-dock-content").addEventListener("submit"');
  const submitEnd = source.indexOf("\n  });", submitAnchor);
  assert.ok(submitAnchor >= 0 && submitEnd > submitAnchor);
  vm.runInContext(source.slice(submitAnchor, submitEnd + "\n  });".length), context);
  return {
    app, activeElement, documentHandlers, listeners, trigger,
    get currentForm() { return currentForm; }, initialForm,
    get submittedForm() { return context.submittedForm; },
    get layerAttached() { return layerAttached; }, get focusCount() { return focusCount; },
    clickOutside() {
      documentHandlers.click({target: focusKind === "select" ? activeElement : {closest: () => null}});
    },
    async submitCurrentForm() {
      const form = currentForm;
      await listeners.submit({target: {closest: (selector) => selector === "#training-inline-form" ? form : null}, preventDefault() {}});
      return form;
    },
  };
}

(async () => {
  const submitHarness = createPickerHarness("button");
  const submitButton = {closest: () => null};
  submitHarness.documentHandlers.click({target: submitButton});
  assert.equal(submitHarness.layerAttached, false, "clicking Start must close the list");
  assert.equal(submitHarness.currentForm, submitHarness.initialForm,
    "an outside click must not detach the form before its native submit event");
  const submittedForm = await submitHarness.submitCurrentForm();
  assert.equal(submitHarness.submittedForm, submittedForm,
    "the existing delegated submit handler must still receive the original form");
  assert.equal(submittedForm, submitHarness.initialForm);

  const selectHarness = createPickerHarness("select");
  const focusedSelect = selectHarness.activeElement;
  selectHarness.clickOutside();
  assert.equal(selectHarness.app.trainingPlayerPickerOpen, false);
  assert.equal(selectHarness.layerAttached, false,
    "clicking a target or duration select must remove the open list even when rendering is skipped");
  assert.equal(selectHarness.trigger.attributes["aria-expanded"], "false");
  assert.equal(selectHarness.currentForm, selectHarness.initialForm,
    "closing the popup must preserve the form containing the focused select");
  assert.equal(selectHarness.activeElement, focusedSelect, "the select must keep focus");
  assert.equal(selectHarness.app.trainingPlayerSearch, "");
  assert.equal(selectHarness.app.trainingPlayerPositionFilter, "all");
  assert.equal(selectHarness.app._lastDockHash, null, "the next full render must reconcile the locally closed popup");

  const escapeHarness = createPickerHarness("search");
  let prevented = 0;
  escapeHarness.documentHandlers.keydown({key: "Escape", preventDefault: () => { prevented += 1; }});
  assert.equal(prevented, 1);
  assert.equal(escapeHarness.app.trainingPlayerPickerOpen, false);
  assert.equal(escapeHarness.layerAttached, false, "Escape must remove the popup in place");
  assert.equal(escapeHarness.currentForm, escapeHarness.initialForm);
  assert.equal(escapeHarness.trigger.attributes["aria-expanded"], "false");
  assert.equal(escapeHarness.focusCount, 1, "Escape must return focus to the player trigger");
})().catch((error) => { console.error(error); process.exitCode = 1; });

// 5. Search input and the candidate filter still narrow the rendered roster.
const searchAnchor = source.indexOf('if(!event.target.matches("#training-player-search")) return;');
const searchStart = source.lastIndexOf('$("#training-dock-content").addEventListener("input"', searchAnchor);
const searchEnd = source.indexOf("\n  });", searchAnchor);
assert.ok(searchStart >= 0 && searchEnd > searchAnchor);
const searchInputHandler = source.slice(searchStart, searchEnd + "\n  });".length);
const searchHarness = {handler: null, renderOptions: null, focused: 0, range: null};
const searchInput = {
  value: "",
  focus: () => { searchHarness.focused += 1; },
  setSelectionRange: (start, end) => { searchHarness.range = [start, end]; },
};
const searchDock = {addEventListener: (type, handler) => { assert.equal(type, "input"); searchHarness.handler = handler; }};
const searchContext = {
  app: {trainingPlayerSearch: ""},
  $: (selector) => selector === "#training-dock-content" ? searchDock : selector === "#training-player-search" ? searchInput : null,
  renderTraining: (options) => { searchHarness.renderOptions = options; searchInput.value = searchContext.app.trainingPlayerSearch; },
  requestAnimationFrame: (callback) => callback(),
};
vm.createContext(searchContext);
vm.runInContext(searchInputHandler, searchContext);
searchHarness.handler({target: {closest: () => null, matches: (selector) => selector === "#training-player-search", value: "Alex"}});
assert.equal(searchContext.app.trainingPlayerSearch, "Alex");
assert.equal(searchHarness.renderOptions.skipStage, true);
assert.equal(searchHarness.focused, 1, "typing must retain focus in the search field after the list rerenders");
assert.deepEqual(searchHarness.range, [4, 4], "typing must restore the caret at the end of the search value");

const filterStart = source.indexOf('const playerSearch = String(app.trainingPlayerSearch || "").trim()', panelStart);
const filterEnd = source.indexOf("const playerRows = filteredPlayers.map", filterStart);
assert.ok(filterStart > panelStart && filterEnd > filterStart);
const filterCode = source.slice(filterStart, filterEnd) + "\nglobalThis.visiblePlayers = filteredPlayers;";
const filterContext = {
  app: {trainingPlayerSearch: "alex", trainingPlayerPositionFilter: "defenders"},
  sortedPlayers: [
    {id: 1, name: "Alex Centre Back", group: "defenders", position: "CB", training_team_type: "club"},
    {id: 2, name: "Alex Striker", group: "forwards", position: "ST", training_team_type: "club"},
    {id: 3, name: "Sam Centre Back", group: "defenders", position: "CB", training_team_type: "club"},
  ],
  playerPositionGroup: (player) => player.group,
  primaryPlayerPosition: (player) => player.position,
  uiText: (key) => key,
};
vm.createContext(filterContext);
vm.runInContext(filterCode, filterContext);
assert.deepEqual(Array.from(filterContext.visiblePlayers, (player) => player.id), [1],
  "search text and the selected position must both filter candidates");

// 6. The picker now lives inside the training form, so Enter in its search box
//    must not implicitly submit the training form.
const submitGuardAnchor = source.indexOf('if(event.key!=="Enter" || !event.target.matches("#training-player-search")) return;');
assert.ok(submitGuardAnchor >= 0,
  "the search box must swallow Enter so it cannot submit the training form");
const submitGuardStart = source.lastIndexOf('$("#training-dock-content").addEventListener("keydown"', submitGuardAnchor);
assert.ok(submitGuardStart >= 0 && submitGuardStart < submitGuardAnchor);
const submitGuardEnd = source.indexOf("\n  });", submitGuardAnchor);
assert.ok(submitGuardEnd > submitGuardAnchor);
const submitGuardSource = source.slice(submitGuardStart, submitGuardEnd + "\n  });".length);

const guard = {handler: null};
const guardContext = {
  $: (selector) => ({addEventListener: (type, handler) => { assert.equal(type, "keydown"); guard.handler = handler; }}),
};
vm.createContext(guardContext);
vm.runInContext(submitGuardSource, guardContext);
assert.equal(typeof guard.handler, "function");
let prevented = 0;
const searchEnter = {key: "Enter", target: {matches: (selector) => selector === "#training-player-search"}, preventDefault: () => { prevented += 1; }};
guard.handler(searchEnter);
assert.equal(prevented, 1, "Enter in the search box must be swallowed");
prevented = 0;
const otherEnter = {key: "Enter", target: {matches: () => false}, preventDefault: () => { prevented += 1; }};
guard.handler(otherEnter);
assert.equal(prevented, 0, "Enter elsewhere must keep submitting the form");

// 7. The stylesheet must not keep the overlay geometry that covered the trigger.
const layerStart = styles.indexOf(".training-player-picker-layer {");
assert.ok(layerStart >= 0);
const layerRule = styles.slice(layerStart, styles.indexOf("}", layerStart) + 1);
assert.ok(!layerRule.includes("position:fixed"),
  "the picker must not cover the whole viewport and hide its own trigger");
assert.ok(layerRule.includes("position:relative"));
'''
    result = subprocess.run(
        ["node", "-e", script, str(root)],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
