"""Exercise wallet debug visibility with the actual settings renderer."""
from pathlib import Path
import subprocess


def test_wallet_debug_controls_follow_the_runtime_version_without_stale_visibility():
    root = Path(__file__).resolve().parents[1] / "src"
    script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const source = fs.readFileSync(process.argv[1] + "/web/app.js", "utf8");
const html = fs.readFileSync(process.argv[1] + "/web/index.html", "utf8");
function node() {
  return {dataset:{}, style:{setProperty(){}}, classList:{toggle(){}},
    setAttribute(){}, closest(){return this;}};
}
const nodes = new Map();
const controls = ["data-cheat-clear", "data-cheat-add-100b"].map(attribute => {
  const markup = html.match(new RegExp("<button\\b[^>]*" + attribute + "[^>]*>"))[0];
  const control = {...node(), markup, hidden:/\bhidden\b/.test(markup)};
  nodes.set("[" + attribute + "]", control);
  return control;
});
const app = {state:{settings:{}}, settingsRenderSignature:null};
const context = {app, window:{}, FONT_SIZE_STEPS:[1,2,3,4,5,6], DEFAULT_FONT_SIZE_STEP:3,
  uiText:key => key, activeUiLocale:() => "en-GB", storedLocaleFontKey:() => "test",
  defaultBetMaxProfit:() => 100, syncSettingsDialogStatus(){}, syncLocaleFontControls(){},
  formatBettingLimitInput:String,
  $:selector => {if (!nodes.has(selector)) nodes.set(selector,node()); return nodes.get(selector);},
  document:{querySelectorAll:selector => {
    assert.equal(selector, "[data-wallet-debug]");
    return controls.filter(control => /\bdata-wallet-debug\b/.test(control.markup));
  }},
};
vm.createContext(context);
const signature = source.slice(source.indexOf("function settingsRenderStateSignature("),
  source.indexOf("function syncSettingsDialogStatus("));
const renderer = source.slice(source.indexOf("function renderSettingsControls("),
  source.indexOf("function shellDomIndex("));
vm.runInContext(signature + renderer, context);
for (const [version, hidden] of [["",true],["V2.7.0beta",true],
    ["V2.7.0beta-dev",false],["V2.7.0beta",true]]) {
  app.state.app_version = version;
  context.renderSettingsControls();
  assert.ok(controls.every(control => control.hidden === hidden),
    `wallet debug visibility must follow ${version || "unknown runtime"}`);
}
'''
    result = subprocess.run(
        ["node", "-e", script, str(root)], capture_output=True, text=True,
        encoding="utf-8", timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
