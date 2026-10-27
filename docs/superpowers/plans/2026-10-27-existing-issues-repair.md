# Existing Issues Repair Plan

**Goal:** Resolve the actionable items in the user's 2026-10-27 issue inventory one at a time, preserving the integrated development baseline.

**Architecture:** Keep existing runtime/application/domain ownership. Apply narrow fixes with failing behavior regressions, verify and save each item independently, then integrate the reviewed cleanup branches and run the relevant combined gates.

**Tech stack:** Windows, Python, vanilla JavaScript, pytest and Node behavior tests.

## Scope and decisions

- Baseline is `5eed72b`, including PR1–PR9 and the repaired legacy settlement replay guard. Preserve both previously pushed commits.
- Treat direct wallet cheating as a development tool: remove `/api/cheat-balance` from frozen builds and reject direct frozen-runtime facade calls; hide its two settings controls in release builds.
- Preserve normal wallet recharge/transfer and the existing FA/god-mode gameplay settings. Their release availability is not inferred to be a new defect.
- Preserve fixed counseling outcomes and zero intimacy points. Do not create relationship changes merely to populate an archive.
- Preserve only en-GB and zh-CN, four training modules, fixed intelligence pricing and all authorised deletions.
- Integrate PR10 (`66ffda2`), PR11 (`3f1cc70`) and PR12 (`04249f2`) locally after behavior fixes are verified. Do not confuse content-merge success with integration-test success.
- Do not start FM/app executables, install hooks or use real saves/accounts. Prepare a concrete live verification proposal only after source repairs are reviewable.
- The runtime remains Windows-only. Investigate actual reproducible test failures; do not invent the unnamed historical Linux 19 failures or claim Windows passes prove Linux results.

## Tasks

### 1. Wallet release boundary

- [x] Add failing tests for frozen HTTP registration/facade and development behavior, and for release/dev control visibility.
- [x] Gate the route and facade, use existing version-driven settings rendering, preserve all legitimate account operations.
- [x] Run focused account, dispatch, wallet and settings checks; independently review and commit.

### 2. Counseling compensation

- [ ] Confirm actual wallet/domain/archive transaction and native rollback boundaries, including the zero-intimacy production path.
- [ ] Reproduce real rollback/refund failure modes; implement compensation that retains the original cause and truthful outcome.
- [ ] Handle applicable archive failures without claiming success for lost records or inventing new relationship effects.
- [ ] Run focused counseling/account/archive tests; independently review and commit.

### 3. Cleanup integration

- [ ] Refresh and integrate the three approved cleanup branches in order, preserving this chat's fixes and retired features.
- [ ] Run changed frontend/locale/backend tests and the existing CI gate selections; review and commit each integration.

### 4. Tests and remaining warnings

- [ ] Run the supported Windows suite in isolated data to identify current failures and repair their causes without weakening behavior checks.
- [ ] Reproduce any available Linux-only failures with a genuine Linux runtime; otherwise record the missing environment and exact verification limitation.
- [ ] Remove verified unused training imports/locals without changing behavior; run related checks.

### 5. Acceptance

- [ ] Independent final review, combined verification and clean Git status.
- [ ] Record per-item outcome, remaining platform/live verification constraints, and concrete steps requiring user authorisation.
- [ ] Publish only within the user's explicit remote authorisation; local fixes and integration are reviewable first.

## Initial evidence

- Working tree clean at `5eed72b`.
- PR10/11/12 and the integration branch have no pairwise content conflicts in prior merge-tree checks.
- Existing native DLLs are available and were source-matched earlier in this chat.
- This machine exposes Python 3.14 and 3.12; no Docker command was found and WSL did not provide a usable installed distribution inventory.

## Task 1 verification

- HTTP/facade regression first reproduced 3 failures and 1 development pass; frontend runtime visibility regression failed before the fix.
- Account/dispatch/wallet/settings/visibility selection: 56 passed, 3 subtests passed; Node syntax passed. Independent review found no blocking or material issue.
