"""My group page fixes from the 2026-10-18 visual review."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "src" / "web"
APP_CSS = (WEB / "app.css").read_text(encoding="utf-8")
DARK_CSS = (WEB / "dark-theme.css").read_text(encoding="utf-8")
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")


def test_metric_rows_size_to_content_and_numbers_do_not_split():
    assert "grid-auto-rows: 1fr;" not in APP_CSS
    assert "  grid-auto-rows: auto;\n" in APP_CSS
    metric_value_style = APP_CSS.split(".owned-club-row-metrics dd {", 1)[1].split("}", 1)[0]
    assert "overflow-wrap: normal;" in metric_value_style
    assert "overflow-wrap: anywhere;" not in metric_value_style
    assert ".owned-club-row-metrics dd > strong { white-space: nowrap; }" in APP_CSS
    assert ".owned-acquisition-comparison{display:grid;grid-template-columns:1fr;" in APP_CSS
    assert APP_CSS.count(".owned-acquisition-change-stack{display:flex;flex-wrap:wrap;gap:0 6px}") == 1
    assert ".owned-acquisition-change,.owned-acquisition-percent{font-size:13px;font-weight:900;white-space:nowrap}" in APP_CSS
    assert ".owned-acquisition-change-stack {" not in APP_CSS


def test_my_group_cards_use_approved_strip_layout_b():
    grid = APP_CSS.split(".my-club-grid {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: minmax(0, 1fr);" in grid
    assert ".my-club-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }" not in APP_CSS
    assert APP_CSS.count('grid-template-areas:"name metrics form actions"') == 1
    assert APP_CSS.count(".my-club-grid>.owned-club-row-card>dl.owned-club-row-metrics>div:nth-child(-n+6){flex:1 1 calc((100% - 30px)/6)") == 1
    assert APP_CSS.count(".owned-club-row-form>div>span{display:grid;place-items:center;min-width:25px;height:25px;") == 1


def test_long_club_name_wraps_instead_of_being_truncated():
    assert ".owned-club-row-identity h2 {\n  margin: 0;\n  overflow: visible;" in APP_CSS
    assert "white-space: normal;\n  overflow-wrap: anywhere;" in APP_CSS
    assert '<h2 title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</h2>' in APP_JS


def test_recent_form_is_solid_squares_in_both_themes():
    for css in (APP_CSS, DARK_CSS):
        for result in ("win", "draw", "loss"):
            assert f".owned-club-row-form > div > .world-form-{result} {{ background:" in css
    assert "color: #fff;" in APP_CSS


def test_sell_confirm_button_is_red_only_with_danger_class():
    assert ".fmodd-confirm-dialog.is-danger .fmodd-confirm-actions #fmodd-confirm-ok { border-color: #a63d36; background: #a63d36;" in APP_CSS
    assert ':root[data-theme="dark"] .fmodd-confirm-dialog.is-danger .fmodd-confirm-actions #fmodd-confirm-ok { border-color: #c4473e;' in DARK_CSS
    assert APP_JS.count('classList.add("is-danger")') == 1


def test_summary_titles_and_command_names_wrap_instead_of_overlapping_or_truncating():
    assert ".my-clubs-summary dt { white-space: normal;" in APP_CSS
    assert ".portfolio-command-copy strong { color: #1d4c3b; font-size: 13px; overflow: visible; text-overflow: clip; white-space: normal;" in APP_CSS


def test_players_without_asking_price_show_dash():
    assert 'const askingPriceLabel = Number(askingPrice) > 0 ? compactMoney(askingPrice) : "-";' in APP_JS
    assert '${Number(player.asking_price) > 0 ? compactMoney(player.asking_price) : "-"}' in APP_JS


def test_stale_sell_message_exists_in_both_retained_catalogs():
    world = (WEB / "i18n.world.js").read_text(encoding="utf-8")
    assert '"portfolio.sell.stale":["Data was refreshed. Please sell again", "数据已刷新，请重新出售"]' in world
