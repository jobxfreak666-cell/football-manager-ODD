from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = (Path(__file__).resolve().parents[1] / "src")


def _between(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def _execute_money_runtime(script: str) -> dict:
    """Run the shipped money formatters and the betting-limit parsers."""
    prelude = "const round = " + _between(script, "const round = ", "const purchaseMoneyScale")
    prelude = prelude.replace(
        "const moneyRate = () => Number(moneySettings().money_rate || 1);",
        "const moneyRate = () => { moneyRateCalls += 1; return Number(moneySettings().money_rate || 1); };",
        1,
    )
    formatters = "const formatFullMoney = " + _between(
        script, "const formatFullMoney = ", "function economyFundingSnapshot()",
    )
    betting = "const formatBettingLimitInput = " + _between(
        script, "const formatBettingLimitInput = ", "const formatFixtureTime = ",
    )
    player_money = "function compactMoney(value) {" + _between(
        script, "function compactMoney(value) {", "function ownedClubMoney(",
    )
    driver = r'''
function takeRateCalls(run) {
  moneyRateCalls = 0;
  const value = run();
  return {value, calls: moneyRateCalls};
}
const output = {};
function record(name, value) { output[name] = value; }
app.compactMoney = false;
app.state.settings = {money_rate:1, money_symbol:"£", money_decimal_digits:2};
window.FMODDI18n.locale = "en-GB";
record("full-small", formatFullMoney(12.5));
record("full-negative-small", formatFullMoney(-12.5));
record("full-zero", formatFullMoney(0));
record("full-1500", formatFullMoney(1500));
record("money-1500", formatMoney(1500));
record("pounds-1500", formatPounds(1500));
record("global-1500", formatGlobalStatisticMoney(1500));
record("below-k", formatMoney(999.94));
record("k-boundary", formatMoney(1000));
record("stay-k", formatMoney(999949));
record("promote-m", formatMoney(999950));
record("negative-m", formatMoney(-2500000));
record("units", {
  K: formatMoney(1e3), M: formatMoney(1e6), B: formatMoney(1e9), T: formatMoney(1e12),
  P: formatMoney(1e15), E: formatMoney(1e18), Z: formatMoney(1e21), Y: formatMoney(1e24),
  R: formatMoney(1e27), Q: formatMoney(1e30),
});
record("promote-p", formatMoney(9.9995e14));
record("history-two", formatCompactMoney(1555000, 2));
record("history-stay", formatCompactMoney(999950, 2));
record("history-promote", formatCompactMoney(999995, 2));
record("history-negative", formatCompactMoney(-1555000, 2));
record("axis-shared", [250000, -1500000, 2000].map((value) => formatChartAxisMoney(value, 2000000)));
record("axis-k", formatChartAxisMoney(1500, 2000));
record("axis-q", formatChartAxisMoney(2e30, 3e30));
record("axis-promote", formatChartAxisMoney(999950, 999950));
record("axis-promote-lower", formatChartAxisMoney(500000, 999950));
record("axis-small", takeRateCalls(() => formatChartAxisMoney(12.5, 20)));
window.FMODDI18n.locale = "de-DE";
record("de-large", formatMoney(1500));
record("de-small", formatFullMoney(12.5));
record("de-negative-small", formatFullMoney(-12.5));
record("de-history", formatCompactMoney(-1555000, 2));
record("de-axis", formatChartAxisMoney(1500000, 2000000));
window.FMODDI18n.locale = "en-GB";
app.state.settings = {money_rate:2, money_symbol:"$", money_decimal_digits:2};
record("converted-large", formatMoney(500000));
record("converted-small", formatMoney(10));
record("player-converted", takeRateCalls(() => compactMoney(500000)));
record("player-unread", takeRateCalls(() => compactMoney(-1)));
record("player-invalid", compactMoney(Number.NaN));
record("player-small", compactMoney(400));
record("parse-m", parseBettingLimitInput("1.5M"));
record("parse-k", parseBettingLimitInput("1.5K"));
record("parse-q", parseBettingLimitInput("1Q"));
record("parse-invalid", parseBettingLimitInput("nope"));
record("limit-converted", formatBettingLimitInput(1500000));
record("limit-unaligned", formatBettingLimitInput(1501));
app.state.settings = {money_rate:1, money_symbol:"£", money_decimal_digits:2};
record("parse-m-gbp", parseBettingLimitInput("1.5M"));
record("limit-gbp", formatBettingLimitInput(1500000));
record("limit-k", formatBettingLimitInput(1500));
app.state.settings.money_decimal_digits = 0;
record("small-digits-zero", formatCompactMoney(12.5, 2));
record("zero-digits-promote", formatMoney(999.99));
record("zero-digits-promote-negative", formatMoney(-999.99));
record("zero-digits-below", formatMoney(999.49));
record("axis-zero-promote", formatChartAxisMoney(999.99, 999.99));
record("axis-zero-shared", formatChartAxisMoney(500, 999.99));
window.FMODDI18n.locale = "de-DE";
record("axis-zero-promote-de", formatChartAxisMoney(999.99, 999.99));
record("axis-zero-shared-de", formatChartAxisMoney(500, 999.99));
window.FMODDI18n.locale = "en-GB";
app.state.settings.money_decimal_digits = 2;
record("two-digits-promote", formatMoney(999.995));
record("two-digits-promote-negative", formatMoney(-999.995));
record("two-digits-below", formatMoney(999.994));
record("small-digits-two", formatMoney(12.5));
globalThis.output = output;
'''
    source = "\n".join((
        "let moneyRateCalls = 0;",
        "const app = {compactMoney:false, state:{settings:{money_rate:1, money_symbol:'£', money_decimal_digits:2}}};",
        "const window = {FMODDI18n:{locale:'en-GB'}};",
        "const activeUiLocale = () => window.FMODDI18n?.locale || 'en-GB';",
        prelude,
        formatters,
        betting,
        player_money,
        driver,
    ))
    probe = (
        "const vm=require('vm');"
        "const context={};"
        "vm.runInNewContext(process.argv[1], context);"
        "process.stdout.write(JSON.stringify(context.output));"
    )
    result = subprocess.run(
        ["node", "-e", probe, source],
        check=False, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return json.loads(result.stdout)


class MoneyAbbreviationsFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        cls.runtime = _execute_money_runtime(cls.script)

    def test_compact_money_supports_every_unit_from_k_through_q(self):
        units = self.script.split("const MONEY_ABBREVIATION_UNITS", 1)[1].split(
            "const MONEY_ABBREVIATION_MULTIPLIERS", 1
        )[0]
        for exponent, suffix in (
            (30, "Q"), (27, "R"), (24, "Y"), (21, "Z"), (18, "E"),
            (15, "P"), (12, "T"), (9, "B"), (6, "M"), (3, "K"),
        ):
            self.assertIn(f'[1e{exponent}, "{suffix}"]', units)
        self.assertNotIn('[1e9, "G"]', units)
        for legacy_suffix in ('"Qa"', '"Qi"', '"Sx"', '"Sp"', '"Oc"'):
            self.assertNotIn(legacy_suffix, units)

    def test_compact_money_units_keep_one_decimal_place(self):
        self.assertIn(
            'compact.toLocaleString(activeUiLocale(), {minimumFractionDigits:1, maximumFractionDigits:1})',
            self.script,
        )
        player_money = self.script.split("function compactMoney(value) {", 1)[1].split(
            "function ownedClubMoney(", 1,
        )[0]
        self.assertIn('if (!Number.isFinite(amount) || amount < 0) return "-";', player_money)
        self.assertIn("return formatFullMoney(amount);", player_money)
        self.assertNotIn("toFixed(1)", player_money)

    def test_betting_limit_input_accepts_every_supported_suffix(self):
        self.assertIn("([KMBTPEZYRQ]?)", self.script)
        self.assertIn("MONEY_ABBREVIATION_MULTIPLIERS[match[2]]", self.script)
        self.assertIn("if (unit) return compact(unit[0], unit[1]);", self.script)
        self.assertIn('`${(amount / unit).toFixed(1)}${suffix}`', self.script)

    def test_settings_describe_all_supported_units(self):
        settings = open(ROOT / "web" / "i18n.settings.js", encoding="utf-8").read()
        self.assertIn('"settings.currency.compact_note"', settings)
        self.assertIn(
            "Large amounts use K, M, B, T, P, E, Z, Y, R and Q with one decimal place.",
            settings,
        )

    def test_bank_account_split_uses_compact_money_setting(self):
        bank = self.script.split('function renderBank() {', 1)[1].split(
            '\n}\n\nfunction renderInventory', 1,
        )[0]
        self.assertIn('formatPounds(funding.bank)', bank)
        self.assertIn('formatPounds(funding.wallet)', bank)
        self.assertNotIn('formatFullMoney(funding.bank)', bank)
        self.assertNotIn('formatFullMoney(funding.wallet)', bank)

    def test_large_amounts_stay_abbreviated_without_the_old_setting(self):
        display = self.script.split("const formatFullMoney = ", 1)[1].split(
            "const formatPounds = ", 1,
        )[0]
        signature = self.script.split("function settingsRenderStateSignature", 1)[1].split(
            "function syncSettingsDialogStatus", 1,
        )[0]
        ranking = self.script.split("function worldNationRankingMetric", 1)[1].split(
            "function worldNationRankingProgress", 1,
        )[0]

        self.assertNotIn("if (!app.compactMoney)", display)
        self.assertNotIn("fm-odds-compact-money", self.script)
        self.assertNotIn("app.compactMoney", signature)
        self.assertNotIn('id="compact-money"', self.html)
        self.assertNotIn("compact-money-setting", self.html)
        self.assertNotIn('"#compact-money"', self.script)
        self.assertIn('if (ranking === "asking_price")', ranking)
        self.assertIn("return Number(value).toLocaleString(activeUiLocale());", ranking)
        self.assertNotIn("formatMoney", ranking)
        self.assertNotIn("formatFullMoney", ranking)

        runtime = self.runtime
        self.assertEqual(runtime["full-small"], "£12.50")
        self.assertEqual(runtime["full-negative-small"], "£-12.50")
        self.assertEqual(runtime["full-zero"], "£0.00")
        self.assertEqual(runtime["below-k"], "£999.94")
        self.assertEqual(runtime["small-digits-two"], "£12.50")
        self.assertEqual(runtime["small-digits-zero"], "£13")
        self.assertEqual(runtime["full-1500"], "£1.5K")
        self.assertEqual(runtime["money-1500"], "£1.5K")
        self.assertEqual(runtime["pounds-1500"], "£1.5K")
        self.assertEqual(runtime["global-1500"], "£1.5K")
        self.assertEqual(runtime["k-boundary"], "£1.0K")
        self.assertEqual(runtime["stay-k"], "£999.9K")
        self.assertEqual(runtime["promote-m"], "£1.0M")
        self.assertEqual(runtime["negative-m"], "-£2.5M")
        self.assertEqual(runtime["units"], {
            "K": "£1.0K", "M": "£1.0M", "B": "£1.0B", "T": "£1.0T",
            "P": "£1.0P", "E": "£1.0E", "Z": "£1.0Z", "Y": "£1.0Y",
            "R": "£1.0R", "Q": "£1.0Q",
        })
        self.assertEqual(runtime["promote-p"], "£1.0P")
        self.assertEqual(runtime["history-two"], "£1.56M")
        self.assertEqual(runtime["history-stay"], "£999.95K")
        self.assertEqual(runtime["history-promote"], "£1.00M")
        self.assertEqual(runtime["history-negative"], "-£1.56M")
        self.assertEqual(runtime["axis-shared"], ["£0.3M", "-£1.5M", "£0.0M"])
        self.assertEqual(runtime["axis-k"], "£1.5K")
        self.assertEqual(runtime["axis-q"], "£2.0Q")
        self.assertEqual(runtime["axis-promote"], "£1.0M")
        self.assertEqual(runtime["axis-promote-lower"], "£0.5M")
        self.assertEqual(runtime["axis-small"], {"value": "£12.50", "calls": 2})
        self.assertEqual(runtime["de-large"], "£1,5K")
        self.assertEqual(runtime["de-small"], "£12,50")
        self.assertEqual(runtime["de-negative-small"], "£-12,50")
        self.assertEqual(runtime["de-history"], "-£1,56M")
        self.assertEqual(runtime["de-axis"], "£1,5M")
        self.assertEqual(runtime["converted-large"], "$1.0M")
        self.assertEqual(runtime["converted-small"], "$20.00")
        self.assertEqual(runtime["player-converted"], {"value": "$1.0M", "calls": 1})
        self.assertEqual(runtime["player-unread"], {"value": "-", "calls": 0})
        self.assertEqual(runtime["player-invalid"], "-")
        self.assertEqual(runtime["player-small"], "$800.00")
        self.assertEqual(runtime["parse-m"], 750000)
        self.assertEqual(runtime["parse-k"], 750)
        self.assertEqual(runtime["parse-q"], 5e29)
        self.assertEqual(runtime["parse-invalid"], 0)
        self.assertEqual(runtime["limit-converted"], "3.0M")
        self.assertEqual(runtime["limit-unaligned"], "3002")
        self.assertEqual(runtime["parse-m-gbp"], 1500000)
        self.assertEqual(runtime["limit-gbp"], "1500.0K")
        self.assertEqual(runtime["limit-k"], "1500")
        self.assertEqual(runtime["zero-digits-promote"], "£1.0K")
        self.assertEqual(runtime["zero-digits-promote-negative"], "-£1.0K")
        self.assertEqual(runtime["zero-digits-below"], "£999")
        self.assertEqual(runtime["axis-zero-promote"], "£1.0K")
        self.assertEqual(runtime["axis-zero-shared"], "£0.5K")
        self.assertEqual(runtime["axis-zero-promote-de"], "£1,0K")
        self.assertEqual(runtime["axis-zero-shared-de"], "£0,5K")
        self.assertEqual(runtime["two-digits-promote"], "£1.0K")
        self.assertEqual(runtime["two-digits-promote-negative"], "-£1.0K")
        self.assertEqual(runtime["two-digits-below"], "£999.99")


if __name__ == "__main__":
    unittest.main()
