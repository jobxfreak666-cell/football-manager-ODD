# Activity Centre Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Activity Centre floor navigation with four modules, remove the unopened eligibility-review placeholder, and explain intelligence availability accurately.

**Architecture:** Keep the existing centre IDs, ownership, purchases, individual activity prices, cooldowns and account records. Use module names and icon tabs in the frontend, retaining the legacy saved floor preference only as a read fallback. Intelligence selection and purchase algorithms stay unchanged.

**Tech Stack:** Existing JavaScript/CSS, bilingual catalogues, Python domain code, isolated Node/pytest regressions.

**Spec:** User request in this chat on 2026-10-28: use the Training Ground module pattern; remove the unopened international review room; inspect intelligence selection. Preserve the preceding wallet +100B and training-card fixes.

## Global Constraints

- Windows runtime, en-GB and zh-CN only, visible font sizes at least 13px.
- No live FM, Hook, real account or save operations. User performs live validation.
- Preserve purchases, balances, cooldowns, history and existing deleted features.
- Do not commit or push without a new request. No generated bundle edits.

## Review Focus

- Old saved module/room choices must resolve to a valid view without another payment.
- Module switching must update the selected tab and panel together.
- Qualification review must disappear from both its directory and metadata.
- Locked modules must retain existing purchase behavior and amounts.
- Intelligence copy must match the actual candidate evidence and random-match selection.

## Tasks

- [x] Frontend (`src/web/app.js`, `src/web/app.css`): rename navigation state to activityModule, migrate the local preference by fallback, replace numbered floor tabs with icon module tabs, remove review placeholder and its special-case rendering; verify actual rendered module navigation and retained activity actions.
- [x] Copy (`src/web/i18n.facilities.js`): module terminology, remove review copy, correct intelligence timing/probability hint and candidate-scan action wording; run affected bilingual checks.
- [x] Backend display (`src/tools/club_economy.py`, `tests/test_activity_centre_backend.py`): replace floor labels in user-facing exceptions only; prove cooldown and purchase behavior is preserved.
- [x] Update affected existing frontend expectations, feature index and architecture; run focused activity, counseling, international/intelligence, locale and prior fix1 regressions. Independently review the final diff.
- [x] Refresh the complete local test package using the full main baseline plus all current completed fixes; record source patch hashes and package verification, preserving older packages.

Final evidence: 322 focused tests and 8 subtests passed; 7065 CSS rules parsed without errors. Independent review findings were fixed and rechecked. The complete `fix2` ZIP passed archived-module, embedded-resource, native ABI/integrity, data/config isolation, CRC and per-file hash checks. No product or live FM process was started. Local source changes remain uncommitted and unpushed.
