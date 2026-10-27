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

- [x] Refresh and integrate the three approved cleanup branches in order, preserving this chat's fixes and retired features.
- [x] Run changed frontend/locale/backend tests and the existing CI gate selections; review and commit each integration.

### 4. Tests and remaining warnings

- [x] Run the supported Windows suite in isolated data to identify current failures and repair their causes without weakening behavior checks.
- [ ] Execute the configured portable Linux matrix on a genuine Linux worker; supplied-log analysis and Windows validation are complete, remote execution awaits publication.
- [x] Remove verified unused training imports/locals without changing behavior; run related checks.

### 5. Acceptance

- [x] Independent final review, combined verification and clean Git status.
- [x] Record per-item outcome, remaining platform/live verification constraints, and concrete steps requiring user authorisation.
- [x] Keep this round's new changes local pending explicit remote publication authorisation; previously authorised `99eab35` and `5eed72b` remain pushed.

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
- PR12 (`04249f2`) merged without conflicts. The existing frontend/locale CI selection plus page hierarchy, commerce, wallet visibility and counseling behavior passed 256 tests and 8 subtests (`build/pr12-frontend-integration-validation.log`). Four changed JavaScript files passed syntax checks. All three merges are local; remote PRs/shared branches were not changed.

## Task 4 verification

- Pyflakes identified 13 remaining unused imports/locals in the web facade and training modules after PR11. The focused scan now exits 0 without warnings (`build/existing-issues-training-lint-final.log`). Account binding and numeric/SKU validation remain in place.
- Training/archive/API/task/future-transfer regressions passed 433 tests and 11 subtests; independent review found no lost validation or side effect (`build/training-warning-cleanup-validation.log`).
- The user will provide the historical Linux failure log later and explicitly asked to continue other repairs first. No runnable Linux environment was found locally; those 19 unnamed failures remain deferred, not claimed fixed.
- The first full Windows run found 4 failures with 3601 passes and 269 subtests. Three tests opened `web/*` relative to an assumed `src` working directory; a fresh Python import test omitted the source path and failed with `ModuleNotFoundError: tools`. Four test files now resolve source paths explicitly and run the pure-import check from a temporary directory with absolute `PYTHONPATH`. All 433 original assertion nodes and the complete pure-import subprogram are unchanged. The four files passed 104 tests from both repository-root and `src` working directories.
- Final isolated full Windows run: **3605 passed, 269 subtests passed**, exit 0, 57.83s (`build/existing-issues-windows-final.log` and `.xml`). No failed or skipped tests were reported. Independent final review found no actionable integration regression (`build/existing-issues-final-review.md`).

## Remaining verification and publication

- The user supplied the original Linux log: 20 failures, 1048 passes and 114 collection errors on dev `2dc8f27`, Python 3.10.22. The follow-up below records the repairs and platform boundaries; a genuine Linux execution is still pending. Windows results do not establish Linux results.
- Live FM verification is performed by the user. After initially authorising an FM26 test copy, the user explicitly took over actual verification; no app/FM launch, hook installation or real save/account operation was performed by this agent.
- Counseling uncertain-state blocking is in the active wheel only. It is not durable idempotency, cross-process native-token validation or automatic recovery/refund after a crash; unresolved states need reconciliation.
- All three cleanup branch heads, dev `e37b907`, PR8 `807ee63`, PR9 `2dc8f27`, `99eab35` and `5eed72b` are ancestors of the integrated local HEAD. Remote PR/shared-branch state was not modified in this round.

## Linux log and Python 3.10 follow-up

- The supplied 20 failure IDs were matched individually to the final Windows Python 3.10 JUnit output: all 20 are present and pass (`build/linux-original20-windows310-status.txt`). The 114 collection errors are Windows native imports in modules, not 114 executed failures.
- Two obsolete platform-independent assertions were already repaired in `ba5c05c` without weakening cart-funding or polling behavior.
- `22fb5d4`: pre-3.12 tokenization represents a complete f-string as `STRING`; the audit now detects its f/F prefix. Actual Python 3.10.22 first reproduced 12 failures/6 passes, then passed all 18 audit cases; Python 3.14 also passed 18.
- `bb31027`: normalize XML source separators using host-compatible paths and keep the safe-root guard. POSIX/Windows path-semantics cases first reproduced 3 failures; both interpreters now pass all 23 portrait tests, including traversal rejection.
- `9bf0932`: four pure name tests locally isolate the unrelated active-game identity lookup. All 17 name tests pass on both interpreters, with zero game-session imports in the tripwire probe. Seven Web integration cases and the Windows-session mutex case remain Windows-only; no POSIX mutex or fake WinDLL was introduced.
- `054ef21`: a fresh canteen-service import test had removed `SYSTEMROOT`, preventing Windows Python 3.10 hash-randomness initialization. Single-variable probes confirmed the cause; restoring only this variable preserves empty PATH and native-free import assertions. Both interpreters pass all 19 canteen tests.
- Additional temporary-directory cleanup failures were reproduced using Python standard library alone. They are local filesystem transients, not game/business assertion failures. A test-only bounded empty-root finalisation handles only matching Windows error 145, never recursively deletes new files, propagates other/nonempty/exhausted errors, and reports each recovery as a visible warning. Seven behavior cases and independent review cover this boundary.
- Final complete isolated Windows runs: **Python 3.10.22: 3631 passed, 269 subtests passed, 4 visible cleanup-recovery warnings, 55.00s**; **Python 3.14.4: 3631 passed, 269 subtests passed, 56.25s**. Both exit 0 with no failed or skipped tests (`build/linux-followup-windows310-acceptance.log/.xml`, `build/linux-followup-windows314-acceptance.log/.xml`).
- CI preserves the existing Windows check names and native builds, then executes the full suite. A new Ubuntu Python 3.10/3.13 matrix positively selects portable helpers and two atomic-write cases. YAML and selected paths were validated locally; the exact portable selection passed 174 tests on Windows Python 3.10. Remote CI and actual Linux execution have not occurred because these new changes remain local.
- These are compensation/error-classification guarantees, not durable idempotency, automatic refund recovery, cross-process token validation or atomic FM/account state.
