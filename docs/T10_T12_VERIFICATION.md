# T10–T12 continuation evidence — 2026-10-05

## Starting state and preservation

- Started from clean `feat/T10`, commit `42e51da`; created the requested `feat/T11`.
  No existing uncommitted work, local T11 branch or T12 implementation claim was
  present. T01–T09 remain complete.
- Read the TODO index/roadmap, UI/foundation handoffs, API contracts, T09 evidence,
  Quick Start, README and persistence ADR before edits.
- The T10 board's `done` claim covered the shell, not complete visual acceptance.
  T10 and T12 now remain in progress with bounded evidence below.
- `.t09-verification/design-exports/` is absent. Figma quota was reported by the
  user; no unavailable Figma/design comparison is claimed as complete. A design
  ZIP containing the role frames, states and intended viewports is needed.
- Docker Desktop was initially stopped. Started it and ran the requested isolated
  Compose command. No prior `waypoint-t09` volume existed here, so Compose created
  its project volume and migrated/seeded it. Existing volumes were preserved.
  A later engine read-only filesystem failure was recovered by restarting Docker
  Desktop; subsequent web-only rebuilds retained the acceptance data. No volume,
  container or cache cleanup was performed.

## T10 work and limits

Core Store, Dispatcher, Loader and Driver workspaces already existed. This change
preserves them and fixes contrast between their dark workflow palette and the
light shared shell. Mobile content wraps, account context can shrink, form fields
fit their containers, and the skip-link now focuses the workspace landmark.
Measured low-contrast shell/receipt text was darkened. The shell describes status
as refreshed server state and local queued work, rather than promising live data.

Store orders, loader trips and dispatcher exceptions have refresh/recovery
controls. Loader loading/failure no longer appears as a successful empty result.
The loader API returns no driver context, so the UI reports unavailable driver
details rather than incorrectly claiming an assigned trip is unassigned.
Exception resolution controls have an accessible action label.

Browser evidence covers 360 px phone, 768 px tablet and 1440 px desktop in the
tested contexts. No page-level horizontal overflow occurred. Login, core role
workspaces, receipt form and receipt result were checked with axe's WCAG A/AA
rules; keyboard skip-link focus was exercised. This is bounded browser acceptance,
not certification of every possible state, assistive technology or device.
Exact frame/layout/font/component matching and visual mismatch inventory remain
pending the design ZIP. The mixed shared-shell/core-workspace palette is preserved
honestly; it is not claimed to reproduce every Figma screen.

## Authentication/offline findings and fix

The backend uses expiring opaque bearer sessions and has no refresh endpoint.
Previously any API error below 500, including `401 INVALID_TOKEN`, became a
persistent `CONFLICT`, permanently blocking later queued actions.

Now a `401` persists `AUTH_REQUIRED`, leaves original command data, event time and
IDs intact, stops automatic retry, and requests sign-in. Same-driver login resumes
the queue. `/auth/me` validates identity and role before each command; token changes
stop replay, and queues retain their owner. Separate users do not share the same
in-flight sync promise. API expiry handling does not invalidate a newer login when
an older request returns late. Unmounted driver retry timers are cleared.

Known legacy conflicts with either exact identity error message are recoverable
without deleting records. Other conflicts, including state/version and permission
failures, remain blocked. Unknown historical messages are not guessed to be auth
failures; they still require review. No backend endpoint, auth architecture,
database schema or IndexedDB schema version changed.

A regression run also found same-millisecond commands could sort by UUID and
replay out of order. New enqueue operations allocate a monotonic persisted queue
position in their existing IndexedDB transaction, including after clock rollback;
the original `occurred_at` retains the actual capture time. Ambiguous order in
already-created historical timestamp ties cannot be reconstructed safely.

## Validation and reproducible acceptance

- Backend: `.venv/Scripts/python.exe -m pytest -q`: **83 passed, 1 skipped**.
  The skip requires a separate official-data PostgreSQL fixture and exact counts;
  it is not suitable for the operational synthetic acceptance database. Added
  expiry-before-POD coverage: rejected command records neither POD nor idempotency
  result; same-driver re-login and duplicate replay create exactly one proof.
  Added cross-driver departure and cross-depot manifest denial checks.
  Pytest temp-directory access needed sandbox escalation. Dependency deprecation
  warnings remain; no dependency migration was introduced.
- Frontend: **16 tests passed**; typecheck, ESLint and production build passed.
  Added expiry/re-authentication, account mismatch, delayed old-token response,
  legacy auth-conflict recovery and monotonic ordering regressions. This checkout
  contained nine frontend tests before edits; the user's reported 28-test baseline
  is not present in this branch. No tests were removed.
- API golden path passed on synthetic planning date `2026-10-08`: Store creates
  320 kg ambient + 180 kg chilled; Dispatcher publishes/assigns; Loader records
  shortage/hold; held departure and stale V1 fail; approved V2 is 480 kg;
  acknowledged driver commands/POD replay and Store receipt/case review succeed.
- Browser preparation uses an unused date and existing supported APIs. Disconnected
  service-worker shell reload, saved receiver draft reload, two delivered stops and
  four queued commands survive reload. Revocation through existing `/auth/logout`
  returns the same `INVALID_TOKEN` path as expiry on reconnect; no DB session edit
  or test-only endpoint is used. Re-authentication drains the queue. Store confirms
  ambient receipt, reports chilled shortage, and Dispatcher reviews/resolves it.
  Original command IDs replay successfully. Backend tests separately exercise
  actual expiry by changing only their isolated in-memory test fixture.
- Final browser run on `2026-10-11` also injected read failures for Store orders,
  Loader trips and Dispatcher exceptions; each surfaced an error and recovered
  through its refresh control. Earlier successful browser workflow used `2026-10-10`.
- Fresh install passed from a new local Git clone with this uncommitted patch
  overlaid, without copying local data, dependencies or virtual environments.
  `waypoint-t12-fresh` created a separate new volume and migrated/seeded using the
  documented Compose startup. Four-role API golden path passed for `2026-10-12`;
  readiness returned `ready`/`ok`, web returned 200. Docker reused valid image
  build cache; this is not a cache-free dependency-download test. Local evidence:
  `.t09-verification/fresh-checkout/.t09-verification/results-fresh.json`.
- Browser accessibility evidence: 14 viewport/state audits, zero axe violations
  after contrast fixes. Screenshots and machine-readable evidence stay ignored
  under `.t09-verification/browser/`; no tokens are written to evidence.
- `git diff --check` passed. Docker acceptance web/API are local only; readiness
  returned `ready` with database `ok`. No public deployment was attempted.
- Read-only PostgreSQL joins through trip stops confirmed all four final browser
  orders (`2026-10-10` and `2026-10-11`) are RECEIVED with CONFIRMED/PARTIAL
  receipts and exactly one POD each, after duplicate command replay.

Reproduce from the repository root (PowerShell), keeping existing volumes:

```powershell
docker compose -p waypoint-t09 -f compose.yaml -f tests/golden-path/compose.yaml up -d
# Rebuild changed web code only when needed:
docker compose -p waypoint-t09 -f compose.yaml -f tests/golden-path/compose.yaml up --build -d --no-deps web
python backend/scripts/verify_golden_path.py --reference-dir .t09-verification/planning --output .t09-verification/results.json --planning-date YYYY-MM-DD
npm.cmd install --prefix .t09-verification/browser-tools playwright axe-core --no-audit --no-fund
python backend/scripts/verify_golden_path.py --reference-dir .t09-verification/planning --output .t09-verification/browser-prepared.json --planning-date ANOTHER-UNUSED-DATE --prepare-only
node tests/golden-path/verify_browser.cjs .t09-verification/browser-prepared.json
```

Replace the date placeholders with unused eligible dates. The configured synthetic
reference declares its operating date explicitly; do not infer an official calendar.
The browser runner requires local Google Chrome and creates real synthetic
operational records only in the isolated stack. Injected network read failures are
acceptance tests, not mocked product services. The isolated URLs are web 5174 and
API readiness `http://localhost:8001/ready`.

Fresh-install reproduction: use a separate checkout containing the proposed
changes, a new project name, and the additional port override. The existing
acceptance stack remains running on its original ports.

```powershell
docker compose -p waypoint-t12-fresh -f compose.yaml -f tests/golden-path/compose.yaml -f tests/golden-path/compose-fresh.yaml up --build -d
python backend/scripts/verify_golden_path.py --api-url http://localhost:8002 --reference-dir .t09-verification/planning --output .t09-verification/results-fresh.json --planning-date UNUSED-ELIGIBLE-DATE
```

## Remaining gates and decisions

- T10 exact design comparison and any resulting visual changes: design ZIP needed.
- T11 optional feature set: agreement still pending; see [scope inventory](T11_SCOPE.md).
  No optional integration is approved, implemented or marked done by deferral.
- T12 exact design-dependent device acceptance, submission/demo video and
  production golden path remain release gates. Fresh local checkout/install and
  tested browser states passed; no universal accessibility/device certification
  or remote Git checkout/network provisioning is claimed.
- Deployment/public URL/HTTPS: requires an agreed hosting target. No hosting
  provider, external infrastructure or public deployment was selected.

## Changed files

- `frontend/src/lib/api.ts`, `api.test.ts`, `driverOffline.ts`, `driverOffline.test.ts`:
  auth recovery, ownership, persistent queue ordering and regression coverage.
- `frontend/src/app/App.tsx`, `StoreReceipts.tsx`, `frontend/src/index.css`,
  `frontend/public/sw.js`: recovery controls, truthful status/context, layout,
  contrast, keyboard focus and shell cache version.
- `backend/tests/test_dispatcher.py`: actual expiry/POD replay and driver/depot
  boundary tests; backend implementation/contracts stay unchanged.
- `tests/golden-path/verify_browser.cjs`, `compose-fresh.yaml`: repeatable browser
  acceptance and separate-port fresh-install support.
- `README.md`, `docs/FOUNDATION_HANDOFF.md`, `docs/QUICK_START.md`,
  `docs/UI_IMPLEMENTATION_HANDOFF.md`, `docs/api-contracts.md`,
  `docs/todo/README.md`, `docs/todo/roadmap.md`, `docs/T11_SCOPE.md`, this evidence
  document: reconciled implementation status, recovery behavior and remaining gates.

Local screenshots/results, temporary browser dependencies and the fresh local
clone remain under ignored `.t09-verification/`. This evidence was recorded before
the implementation/tests and documentation/evidence commits.
