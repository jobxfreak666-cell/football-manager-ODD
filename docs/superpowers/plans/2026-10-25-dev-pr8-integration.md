# Dev and PR8 Integration Plan

**Goal:** Integrate PR8 into the complete PR1–PR7 development baseline without reviving retired features.

**Architecture:** Merge `origin/main` (`807ee63`) into a branch based on `origin/football-manager-odd-dev` (`e37b907`). Keep the development branch's application services and four training modules; adapt PR8's scoped intelligence refresh and media-centre removal to those boundaries.

**Tech stack:** Windows, Python application services, vanilla JavaScript/CSS, pytest and Node-based isolated frontend tests.

## Approved specification

- Preserve all completed PR1–PR7 features, fixes, team-training transactions and migrations.
- Keep player, position, staff and team training. The removed equipment picker is superseded; do not restore it or its obsolete tests.
- Keep fixed GBP intelligence prices of 40M / 60M / 80M and existing random-purchase rules.
- Keep only en-GB and zh-CN; retain deleted locale packs.
- Remove the unavailable media-centre entry and its three rooms from the active activity-centre projection.
- Add an explicit action that searches for available intelligence and refreshes candidate fixtures, preserving scope checks and bounded probing.
- Verify the current player-detail expand/collapse interaction and fix only an observed equivalent fault.
- No live FM operations, hook installation, save/account changes, or application launch. Static and mock evidence cannot establish live-game correctness.

## Interfaces and review focus

- `POST /api/activity/intelligence/refresh` consumes `data_scope_id` and returns an intelligence projection plus the same scope.
- The application service owns probing, refresh validation and projection orchestration; `LocalOddsState` remains the runtime/IO owner and thin facade.
- Reject changed save scopes, unknown game time and locked/busy states without publishing stale candidates.
- Keep manual and background probes single-flight; forced probes may rescan within existing bounded limits.
- A refresh failure must preserve visible results and release the action's busy state.
- Keep bilingual strings and fixed-price purchase behavior consistent across backend and frontend.

## Execution

### Task 1: Backend adaptation

Ownership: `src/fm_odds_web.py`, `src/tools/match_intelligence_application.py`, `src/tools/club_economy.py`, `src/tools/preview_cup_odds.py`, and related backend tests.

- [x] Adapt PR8 refresh/probe regression tests to the dev application-service boundary and observe the expected failures.
- [x] Implement scoped explicit refresh and single-flight probing through the application service, preserving fixed prices.
- [x] Resolve media-centre projection changes and run focused intelligence/application/activity tests.

### Task 2: Frontend adaptation

Ownership: `src/web/app.js`, `src/web/app.css`, `src/web/i18n.facilities.js`, and related frontend/locale tests.

- [x] Adapt behavior tests for the refresh action and stale response handling.
- [x] Port the media-centre removal, refresh action and only the two retained translations.
- [x] Verify current training-detail selection and collapse behavior; do not restore the equipment picker.
- [x] Run the focused frontend/locale tests and Node syntax checks.

### Task 3: Integration acceptance

Ownership: documentation, integration verification and Git merge resolution.

- [x] Update architecture, feature index, runtime contracts and changelog to describe final semantics.
- [x] Run affected regression suites and the existing frontend CI gate using isolated data.
- [x] Obtain an independent review of the integrated result and address material findings.
- [x] Verify no unresolved conflicts, retired locale files or equipment-picker artifacts remain; preserve both histories and create the local integration follow-up commit.

## Initial evidence

- Remote heads verified as `e37b907` and `807ee63` on 2026-10-25.
- Baseline: `python -m pytest tests/test_match_intelligence_application.py tests/test_training_roster_attributes_frontend.py -q` — 43 passed.
- This plan records the user's approved decision; execution is already authorised.

## Upstream reconciliation — 2026-10-27

- Dev advanced to `2dc8f27` (PR9), which already merges PR8 and ports its guarded probe.
- Adopted that completed integration as HEAD while preserving local work; both `e37b907` and `807ee63` are verified ancestors.
- The remaining local change completes application-service ownership, rejects stale/invalid refresh contexts, retains candidates during refresh/error, and fixes current training-detail collapse.
- Native test DLLs were reused from the existing `5ea8` checkout after byte-for-byte comparison of all four tracked native source files; no native source changed. DLLs and isolated test data stay outside Git.
- Native/training baseline checks: 97 passed + 9 subtests, then 446 passed + 20 subtests. Final affected checks follow after implementation stabilises.

## Backend acceptance

- Intelligence/application/activity: 126 passed; background polling/API/settlement/pending-search/evidence: 127 passed.
- Account/counselling/canteen/medical application services: 58 passed.
- The pending-result-search test now resolves its two existing resource paths from `__file__` under `src/`, preserving all assertions.

## Pre-review verification — 2026-10-27

- Combined 41-file selection covering both existing CI test lists plus affected intelligence, API, settlement and application-service regressions: **1112 passed, 37 subtests passed in 30.91s**, no exclusions.
- Node syntax checks passed for `app.js` and `i18n.facilities.js`; the four affected Python modules parse with the Python 3.10 syntax grammar. Test execution used Python 3.14.4.
- No unresolved merge entries, retired language packs or old equipment-picker selectors remain. The four training/domain modules and preserved counselling/canteen/medical services are unchanged from the approved `e37b907` baseline.
- These are isolated automated checks, not live FM or desktop WebView verification. No test package was built during this integration.

## Independent review and repair

- Review found a failed cross-date GET could schedule an immediate render/reload loop while preserving the old projection (P1). The frontend owner is adding a behavioral reproduction and an explicit-retry recovery path.
- Review found `public_status()` could race a scoped candidate/cache publication because it did not use the runtime lock (P2). The backend owner is reproducing the interleaving and aligning public projection with the existing runtime lock.
- Both findings were reproduced before repair and now pass their behavioral regressions. The 1112-test evidence above predates these repairs; the independent repair re-review passed with no related material findings.

## Post-repair verification — 2026-10-27

- Re-ran the same 41-file selection after both repairs: **1116 passed, 37 subtests passed in 30.63s**, no exclusions.
- The two added frontend cases prove repeated renders stop automatic GET retries after failure for both an old-date projection and the initial empty projection; explicit GET/POST retry remains usable.
- Two real-thread/event cases prove public GET cannot overwrite a later refresh or another account cache. The public projection uses the runtime RLock across snapshot and publication.
- Node and Python syntax checks, whitespace checks and both-history ancestry checks passed.

## Final acceptance

- Independent full-change review identified two concrete boundary defects, both repaired with red/green regressions. A fresh independent reviewer then confirmed P1 and P2 resolved with no related regression.
- Integration is saved as a local follow-up on PR9; both approved histories remain reachable. No push, release, test-package build or live-game verification is included in this step.
