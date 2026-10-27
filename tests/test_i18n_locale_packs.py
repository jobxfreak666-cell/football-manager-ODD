from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src"
SUPPORTED_LOCALES = ("en-GB", "zh-CN")


def _runtime_probe() -> dict[str, object]:
    script = r'''
const fs = require("fs"), vm = require("vm"), root = process.argv[1];
const html = fs.readFileSync(root + "/web/index.html", "utf8");
const sources = [...html.matchAll(/<script\s+src="([^"]+)"/g)].map(match => match[1]);
const context = {
  window:{FMODDI18nModules:[]},
  document:{documentElement:{dataset:{}},querySelector:()=>null,dispatchEvent:()=>{}},
  NodeFilter:{SHOW_TEXT:4},CustomEvent:class CustomEvent {},
};
vm.createContext(context);
for (const source of sources) {
  if (!source.startsWith("/i18n") || source === "/i18n.js") continue;
  vm.runInContext(fs.readFileSync(root + "/web" + source, "utf8"), context, {filename:source});
}
vm.runInContext(fs.readFileSync(root + "/web/i18n.js", "utf8"), context, {filename:"/i18n.js"});
const i18n = context.window.FMODDI18n;
const supportedLocales = [...i18n.SUPPORTED_LOCALES];
const rendered = {};
for (const locale of supportedLocales) {
  i18n.setLocale(locale, {persist:false,root:null});
  rendered[locale] = {
    language:i18n.t("settings.language"),
    title:i18n.t("page.my_clubs.title"),
  };
}
i18n.setLocale("en-GB", {persist:false,root:null});
const acceptedTraditional = i18n.setLocale("zh-TW", {persist:false,root:null});
const traditionalAttempt = {
  accepted:acceptedTraditional,
  locale:i18n.locale,
  text:i18n.t("settings.language"),
};
console.log(JSON.stringify({sources,supportedLocales,rendered,traditionalAttempt}));
'''
    result = subprocess.run(
        ["node", "-e", script, str(ROOT)], check=True, capture_output=True,
        text=True, encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_runtime_only_registers_the_two_retained_ui_languages() -> None:
    output = _runtime_probe()
    assert tuple(output["supportedLocales"]) == SUPPORTED_LOCALES
    assert all(
        source not in output["sources"]
        for source in (
            "/i18n.tw.js", "/i18n.ko.js", "/i18n.de.js", "/i18n.es.js", "/i18n.fr.js",
            "/i18n.ru.js", "/i18n.ja.js", "/i18n.pt-BR.js", "/i18n.pt-PT.js",
        )
    )


def test_both_retained_catalogs_render_and_traditional_chinese_stays_unsupported() -> None:
    output = _runtime_probe()
    assert output["rendered"] == {
        "en-GB": {"language": "Interface language", "title": "My Group"},
        "zh-CN": {"language": "界面语言", "title": "我的集团"},
    }
    assert output["traditionalAttempt"] == {
        "accepted": False,
        "locale": "en-GB",
        "text": "Interface language",
    }
