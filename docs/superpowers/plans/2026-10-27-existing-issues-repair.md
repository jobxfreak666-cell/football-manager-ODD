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

- [x] Confirm actual wallet/domain/archive transaction and native rollback boundaries, including the zero-intimacy production path.
- [x] Reproduce real rollback/refund failure modes; implement compensation that retains the original cause and truthful outcome.
- [x] Handle applicable archive failures without claiming success for lost records or inventing new relationship effects.
- [x] Run focused counseling/account/archive tests; independently review and commit.

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

## Task 2 verification

- Fixed `unlocked`/zero-intimacy production counseling never needs a relationship archive. Unsupported nonzero callbacks are rejected before native writes.
- Initial failure regressions reproduced 13 failures with 30 passing cases. Post-replace commit regressions then reproduced 6 failures with 1 passing case. Projection failures reproduced 4 additional failures; live frontend behavior regressions reproduced 12 failures with 4 passing cases. The final combined counseling/account/archive/frontend/locale selection passed 234 tests and 7 subtests (`build/counseling-repair-final-validation.log`).
- Native write attempts, including a partially failed last write, are restored in reverse order and read back. An incomplete restore stops refund; refund exceptions preserve both causes and report an unknown refund result.
- Independent review caught a post-replace save failure boundary. The domain now verifies this session's UUID, counseling state, cooldown and progress directly from the primary container under account locks. Confirmed commits keep native effects and payment; confirmed absence permits compensation; unreadable or inconsistent state returns `commit_unknown` without compensation.
- Confirmed business success survives failed economy/welfare projections, including a persistent signature fault. The response keeps the counseling result and flags `state_refresh_required`; the active wheel preserves missing views and remains completed even if subsequent rendering fails. The frontend/locale selection passed 113 tests and both JavaScript syntax checks.
- The active batch blocks the three nonretryable uncertain outcomes without claiming completion, excludes them from individual/batch actions and quotes, and labels the unresolved batch for checking. All 24 real-source Node behavior cases passed. This is not a persistent pending-operation guard. Final independent review found no remaining actionable issue in this change.

## Task 3 integration evidence

- PR10 (`66ffda2`) merged without source conflicts. Its changed-file/frontend/training selection passed 451 tests and 2 subtests; JavaScript syntax passed. Two pre-existing assertions also failed on the dev baseline: an absent `fundingPaymentSplit(total)` call and a global count of three waits when four live helpers exist. Tests now verify the actual cart funding call and each bounded polling helper; independent review found no weakening or actionable issue.
- PR11 (`3f1cc70`) merged without conflicts. The existing native/training CI selection plus account, HTTP and counseling regressions passed 609 tests and 29 subtests (`build/pr11-native-integration-validation.log`). The native sources are unchanged; this run used the existing source-matched DLLs.
- These are compensation/error-classification guarantees, not durable idempotency, automatic refund recovery, cross-process token validation or atomic FM/account state.
