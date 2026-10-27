# Match intelligence backend refactor implementation plan

> **Historical baseline (2026-10-17):** This record captures the imported baseline and its approved follow-up at that time. Test totals and locale references below describe that historical scope. Since commit `eaf59ad` (2026-10-20), current UI language support is `en-GB` and `zh-CN`; see [`AGENTS.md`](../../../AGENTS.md) and [`I18N_ARCHITECTURE.md`](../../I18N_ARCHITECTURE.md).

> **For agentic workers:** Use superpowers:executing-plans to implement the tasks inline. Steps use checkbox syntax for tracking.

**Goal:** Extract match-intelligence use cases from the HTTP/runtime entrypoint without changing behavior.

**Architecture:** A focused application service receives a typed runtime protocol and explicit callable dependencies. `LocalOddsState` retains the only runtime state and its original facade methods; each call binds the current module-level dependencies to preserve replacement seams. The watch loop stays in the runtime.

**Tech Stack:** Python 3.10+, standard library, pytest.

**Spec:** `docs/superpowers/specs/2026-10-17-backend-intelligence-refactor-design.md`

**Execution update (2026-10-17):** Grok's full 36-file patch was imported once after verifying the three exports match. The user then selected DeepSeek for code tasks. DeepSeek implemented the extraction via file tools; Codex ran verification and integrated documentation/UI previews. An independent read-only review found no material extraction defect.

## Global constraints

- For the service extraction on the imported Grok baseline: no API, UI, persisted-data, pricing, error-message, native-memory, or version-support changes. Later approved follow-ups are recorded separately below.
- Preserve the probe's nonblocking memory lock, throttle ordering, serialized comparison, and scope binding.
- Preserve the purchase's memory-lock-then-state-lock ordering and submission-id retry behavior.
- No live FM connection, Hook installation, product launch, real-account changes, or release build.
- Deliver local changes for review; do not commit or push without a later request.
- UI preview is required if a necessary UI change is introduced; the extraction itself needs no UI changes. The later wallet follow-up includes its own preview.

## Review focus

- A scope switch must keep the existing cache fallback and account identity behavior.
- Calls through the facade must resolve replaced globals at call time, including after an earlier call.
- Lock contention must not make the background probe block a foreground operation.
- Failed clock/probe/purchase operations must retain exception and cleanup behavior.
- Random retries for expired fixtures must use the existing purchase without reselection.

### Task 1: Preserve the existing lifecycle contract

**Files:** Create `tests/test_match_intelligence_application.py`.

**Interfaces:** Exercises the four existing `LocalOddsState` methods with isolated fake locks, state, and collaborators; imports stay compatible after extraction.

- [x] Create an ignored virtual environment and install pytest; attempt the focused baseline (full runtime collection blocked by missing Rust DLL/toolchain; existing frontend checks: 4 passed).
- [x] Add characterization tests for probe gating/throttling/nonblocking locks/error cleanup/version updates, public-status scope/clock/cache isolation, and purchase lock order/random retries/failed writes.
- [x] Run those tests against the original implementation before moving code (29 passed on both the old and imported baselines).

### Task 2: Extract and wire the service

**Files:** Create `src/tools/match_intelligence_application.py`; modify `src/fm_odds_web.py` and the new test file.

**Interfaces:** `MatchIntelligenceApplicationService(runtime, io, *, poll_seconds)` exposes `probe_if_idle(*, force=False)`, `public_status()`, and `purchase(payload)`. `MatchIntelligenceIO` is a frozen dataclass of explicit callables; `MatchIntelligenceRuntime` documents the state/lock/callback requirements without owning their storage.

- [x] Add a failing test that runs the extracted service directly without importing the HTTP entrypoint (expected ModuleNotFoundError before extraction, then passed).
- [x] Move the three use-case bodies with unchanged control flow and message text; replace global access with explicit dependencies.
- [x] Replace the three facade bodies with delegates and add `_match_intelligence_application()` to bind current dependencies on each call. Keep the watcher and pure helper entrypoints.
- [x] Verify direct-service tests, facade replacement compatibility, and existing focused regressions.

### Task 3: Document and review the finished change

**Files:** Update `docs/ARCHITECTURE.md`, `docs/FEATURE_INDEX.md`, and this plan's checkboxes.

**Interfaces:** Documentation identifies the facade, new service, domain providers, and focused tests.

- [x] Update module ownership and align stale runtime documentation with the imported fixed-price/no-free-purchase behavior.
- [x] Attempt the native-dependent regression set; collection is blocked by missing Rust native DLL/toolchain. Run the available boundary, wallet, counseling-domain, activity-frontend, i18n and settings checks: 85 passed. This is not a native/runtime pass.
- [x] Compile changed Python files, check the final diff and unchanged frontend, and request one independent review.
- [x] Resolve any material review findings and rerun affected checks; report the first batch's scope and verification limits.

## Approved follow-ups (2026-10-17)

These follow-ups are separate from the first batch's behavior-preserving service extraction:

- [x] Move the existing wallet button to the right of the Disable FA checkbox and change it to +100B. Each successful click adds and persists exactly 100_000_000_000 to the wallet; the bank is untouched and the legacy 100/500/5000 API amounts remain accepted. Labels and feedback cover all 11 supported locales. Preview: `output/ui-preview/08-wallet-100b.png`.
- [x] Align the stale intelligence-pricing documentation with fixed prices and update the catalog contract to validate all declared supported locales while requiring the base three. Domain catalogs may embed additional supported translations alongside the separate locale packs. Missing keys, empty values and placeholder mismatches remain errors; HTML semantic-key resolution is checked in all 11 locales, including documented English fallback.
- [x] Verify the affected isolated tests: 102 passed, including 13 catalog-contract cases. This does not establish complete translation coverage or native/HTTP/live-game integration; missing Rust native libraries still block full-runtime collection.

No commit, push, packaging, product launch or live account/save changes are included. DeepSeek passed a short connection check but its implementation and text-proposal attempts failed with transport errors, so Codex implemented the catalog correction. Qoder supplied a documentation proposal; Codex corrected target paths and wording before integration.
