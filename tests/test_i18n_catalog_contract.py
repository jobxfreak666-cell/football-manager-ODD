from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = (Path(__file__).resolve().parents[1] / "src")
LOCALES = ("en-GB", "zh-CN")
SUPPORTED_LOCALES = LOCALES


def _probe() -> dict[str, object]:
    script = r'''
const fs = require("fs");
const vm = require("vm");
const root = process.argv[1];
const html = fs.readFileSync(root + "/web/index.html", "utf8");
const sources = [...html.matchAll(/<script\s+src="([^"]+)"/g)].map((match) => match[1]);
const context = {
  window:{FMODDI18nModules:[]},
  document:{documentElement:{dataset:{}}, querySelector:()=>null, dispatchEvent:()=>{}},
  NodeFilter:{SHOW_TEXT:4}, CustomEvent:class CustomEvent {},
};
vm.createContext(context);
for (const source of sources) {
  if (!source.startsWith("/i18n") || source === "/i18n.js") continue;
  vm.runInContext(fs.readFileSync(root + "/web" + source, "utf8"), context, {filename:source});
}
const modules = context.window.FMODDI18nModules.map((entry) => entry.messages || {});
vm.runInContext(fs.readFileSync(root + "/web/i18n.js", "utf8"), context, {filename:"/i18n.js"});
const keyed = [...html.matchAll(/data-i18n(?:-aria-label|-placeholder|-title|-alt)?="([^"]+)"/g)].map((match) => match[1]);
const missing = {};
const supportedLocales = [...context.window.FMODDI18n.SUPPORTED_LOCALES];
const rendered = {};
for (const locale of supportedLocales) {
  context.window.FMODDI18n.setLocale(locale, {persist:false, root:null});
  missing[locale] = [...new Set(keyed.filter((key) => context.window.FMODDI18n.t(key) === key))].sort();
  rendered[locale] = {
    language:context.window.FMODDI18n.t("settings.language"),
    groupTitle:context.window.FMODDI18n.t("page.my_clubs.title"),
    gameDate:context.window.FMODDI18n.t("home.game_date", {date:"2026-07-01"}),
  };
}
console.log(JSON.stringify({sources, modules, supportedLocales, missing, rendered}));
'''
    result = subprocess.run(
        ["node", "-e", script, str(ROOT)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _parameters(value: str) -> set[str]:
    return set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", value))


def _validate_domain_catalog(module: dict[str, dict[str, str]]) -> None:
    assert set(module) == set(LOCALES), "locale set differs from supported locales"
    reference = module["en-GB"]
    assert reference, "empty catalog"
    for locale in LOCALES:
        translations = module[locale]
        assert set(translations) == set(reference), f"{locale}: keys differ"
        for key, value in translations.items():
            assert isinstance(value, str) and value.strip(), f"{locale}:{key}: empty or non-string value"
            assert _parameters(value) == _parameters(reference[key]), f"{locale}:{key}: parameters differ"


def test_domain_catalog_accepts_exact_bilingual_locale_set() -> None:
    locales = LOCALES
    _validate_domain_catalog({locale: {"greeting": "Hello {name}"} for locale in locales})


@pytest.mark.parametrize("defect, message", [
    ("missing_locale", "locale set differs"),
    ("extra_locale", "locale set differs"),
    ("missing_key", "keys differ"),
    ("extra_key", "keys differ"),
    ("empty_value", "empty or non-string value"),
    ("non_string", "empty or non-string value"),
    ("parameters", "parameters differ"),
])
def test_domain_catalog_rejects_invalid_extra_locale_translations(defect, message) -> None:
    module = {locale: {"greeting": "Hello {name}"} for locale in LOCALES}
    if defect == "missing_locale":
        del module["zh-CN"]
    elif defect == "extra_locale":
        module["ko-KR"] = dict(module["en-GB"])
    elif defect == "missing_key":
        module["zh-CN"].clear()
    elif defect == "extra_key":
        module["zh-CN"]["extra"] = "Extra"
    elif defect == "empty_value":
        module["zh-CN"]["greeting"] = "   "
    elif defect == "non_string":
        module["zh-CN"]["greeting"] = None
    else:
        module["zh-CN"]["greeting"] = "Hello {other_name}"
    with pytest.raises(AssertionError, match=message):
        _validate_domain_catalog(module)


def test_every_loaded_domain_catalog_has_locale_and_parameter_parity() -> None:
    output = _probe()
    modules = output["modules"]
    assert modules
    assert tuple(output["supportedLocales"]) == SUPPORTED_LOCALES
    for module in modules:
        _validate_domain_catalog(module)


def test_html_semantic_keys_resolve_and_catalogs_load_before_core() -> None:
    output = _probe()
    sources = output["sources"]
    assert sources.index("/i18n.js") < sources.index("/app.js")
    for source in sources:
        if source.startswith("/i18n.") and source not in {"/i18n.js"}:
            assert sources.index(source) < sources.index("/i18n.js")
    assert output["missing"] == {locale: [] for locale in SUPPORTED_LOCALES}


def test_both_supported_catalogs_render_localized_copy_and_parameters() -> None:
    output = _probe()
    assert output["rendered"] == {
        "en-GB": {
            "language": "Interface language",
            "groupTitle": "My Group",
            "gameDate": "Game date 2026-07-01",
        },
        "zh-CN": {
            "language": "界面语言",
            "groupTitle": "我的集团",
            "gameDate": "游戏日期 2026-07-01",
        },
    }
