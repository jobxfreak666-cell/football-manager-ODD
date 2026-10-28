# League Standings Catalog Implementation Plan

**Scope update (user, 2026-10-28):** The user replaced loaded-league filtering with native league reputation descending order. Search/replacement and refreshed discovery remain in scope. Previous loaded-mode/hierarchy investigation below is historical, not an unfinished acceptance requirement. Current defaults use native catalog reputation, keep later manual replacements in a new save-scoped preference bucket, and do not migrate legacy auto-filled lists. The user also explicitly authorized read-only memory inspection of their running FM26; no memory write, Hook or save/account operation is authorized.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the 积分榜 page search every competition in the running FM database and replace what it displays, explain explicitly why a competition has no table, and pick up competitions added to the save without a code change.

**Architecture:** Add a read-only `league_catalog` payload beside the existing `league_standings` payload. The catalog enumerates the native `competition` pointer table through the existing `DatabaseIndex`/`Reader` plumbing the way `preview_cup_odds` already does, joins each competition against the standings already published in the same request, and states a reason when no table can be built. The standings payload keeps its shape and ownership unchanged; the web layer joins the two by `competition_id` and never infers competition type.

**Tech Stack:** Python 3.10 domain code (`src/tools/`), the existing `LocalOddsState` state endpoint (`src/fm_odds_web.py`), plain ES2020 in `src/web/app.js` with the existing bilingual catalogue files, and focused `pytest`/Node regressions.

**Spec:** User request in this chat on 2026-10-28, three acceptance criteria:

1. The default 积分榜 range must be the leagues the player selected in FM (Playable and View-Only) plus their real lower divisions.
2. The selector needs a search box over every competition in the game, to replace the competition currently displayed.
3. A competition added in FM must appear in the FMODD selector.

Criteria 2 and 3 are met by this plan. Criterion 1 is **not** met: see "Known gap" below.

## Global Constraints

- Windows runtime only. No live FM process, hook install, save/account change or executable launch without explicit user authorization; the only live work authorized in this change was a read-only probe of an already-running FM26.
- Use the active `GameLayout` for every version-dependent offset. Preserve object identity checks, expected-old-value checks, readback and rollback. A layout without an offset yields `None`, never a guessed value.
- Do not hand-edit generated asset bundles; `src/web/` is served directly.
- User-visible copy in en-GB and zh-CN only. Visible font size at least 13px.
- Focused tests only; no automatic full-suite run, service restart or release build.
- The worktree already carries 22 uncommitted files from the previous task. No `git reset`, `git checkout --`, `git clean`, `git stash` or `git apply`.
- Do not commit or push without a new user request.

## Review Focus

- `league_standings` keeps its published shape exactly; nothing is repurposed, no field is added to it.
- `standings_available` is the only signal for "has a table". `standings_reason` explains why the native formatter did not produce one and may be non-null even when a reconstructed table exists.
- Empty is never silent: a competition either shows a table or shows an explicit reason in the board.
- 8095 catalog rows must never all reach the DOM.
- Selection storage is per save, and the legacy layout-keyed preference still seeds it once.
- The catalog build performs no memory write, no save write and no account change; a failed native read degrades to an explicit `unavailable` payload instead of raising.

## Known gap: the FM league selection is still unreadable

Criterion 1 needs the set of leagues the player loaded in FM, with their Playable / View-Only mode and their parent-child hierarchy. No such native container has been located, so this plan does not attempt it and no offset was guessed.

What was checked and rejected as evidence:

- `DatabaseIndex.addresses("competition", ...)` gives identity-verified competition objects, but the table is the full universe of competitions, not the loaded subset.
- `competition_formats` only describes competitions that already produced a schedule or result, so a loaded league with no played fixture is absent from it.
- Reputation, name shape, "has an actual competition", and "has stages" all correlate with being a senior league without meaning "this save loaded it".
- The native stage-marker path cannot classify league vs cup either: across all 8095 FM26 rows, 6700 have no actual and 1131 no stages, and the classified remainder is 116 league / 53 group / 12 cup / 83 unknown, with 西班牙足球甲级联赛 (id=67) and 葡萄牙足球超级联赛 (id=60) both landing in unknown.

Per the project rule that a guess must never become a contract, the default range stays what the code can defend, and the gap is documented rather than papered over. Closing it needs a save-scoped native container for the loaded-league set plus its mode and hierarchy, verified read-only on a real save first.

## Tasks

- [x] Backend (`src/tools/competition_catalog.py`): enumerate the native competition table read-only, read reputation per layout, join against the same request's standings, and publish a fixed six-key payload whose entries carry `standings_available`, `standings_source` and a reason code from a documented, precedence-ordered table that mirrors the real `league_standings` branches. Degrade to `unavailable` on any read failure. Publish it as `league_catalog` beside `league_standings` in `src/fm_odds_web.py` without touching the standings payload.
- [x] Read-only probe (`scripts/probe_competition_catalog.py`): measure cold versus warm scan cost, the read delta, the reputation distribution and the reason distribution, with a `--no-game` path for the degraded payload. No memory write, no hook, no save access.
- [x] Backend regression (`tests/test_competition_catalog.py`): synthetic reader and output only. Proves full enumeration, every reason code reachable, precedence order, sort order, cache reuse and invalidation on table-token change, scope isolation, degradation on failure, and that `public_league_standings` keeps its shape.
- [x] Frontend (`src/web/app.js`, `src/web/app.css`): searchable picker over the catalog replacing the flat `<select>`, matching name, short name and id in both locales; unavailable entries stay selectable and are marked; explicit unavailable notice in the board; DOM capped so the full catalog never renders; save-scoped selection storage with a one-time migration from the layout-keyed key; and an exact fallback to the old behaviour when the catalog is absent.
- [x] Copy (`src/web/i18n.*.js`): picker, search, empty-result, refine hint and one label per reason code, each in en-GB and zh-CN.
- [x] Frontend regression (`tests/test_league_frontend.py`): executes the real `app.js` helpers under Node for search matching, unavailable-but-selectable, the save-scoped key plus migration, and the no-catalog fallback.
- [x] Documentation (`docs/RUNTIME_CONTRACTS.md`, `docs/ARCHITECTURE.md`, `docs/FEATURE_INDEX.md`, `docs/guides/PRODUCT_GUIDE.md`): publish the contract, the ownership split, the picker behaviour, the save-scoped storage, the league/cup limitation and the fact that most catalog entries have no table. Record the unreadable FM selection as the remaining gap for criterion 1.

Final evidence: recorded in the hand-off at the end of this change. No FMODD service, no live FM write and no real account or save was touched; the user performs live validation.
