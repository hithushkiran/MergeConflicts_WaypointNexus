# T09 — receipt and golden-path acceptance

T09 keeps the modular monolith, PostgreSQL authority, aggregate shipment lines,
configured planning references and existing offline outbox. The S04/S04B/S05
receipt content is integrated into the current store workspace; the shared role
shell and complete Figma visual rebuild remain T10. Figma's inconsistent sample
quantities are replaced with real order, manifest and receiving values. Intake
uses units; displayed weight equivalents are explicitly proportional estimates.

Receipt semantics and case transitions are in [API contracts](api-contracts.md).
Stores choose confirmation (including approved partial intake) or a discrepancy
case. Case review remains pending until a dispatcher starts review and resolves
the recorded outcome with a reason. No replacement delivery, refund, messaging,
photo upload or product catalog is implied by resolution.

## Scope and checks

- Backend: receipt module, delivery quantity snapshot, additive Alembic migration.
- Frontend: receiving comparison/form/result and dispatcher receiving-case inbox.
- Tests: success, partial/zero receipt, invalid fields, scope/role rejection,
  transitions, stable replay, duplicate prevention, legacy and historical quantities.
- Complete acceptance: API-created 320 kg ambient + 180 kg chilled orders,
  publication, 20 kg chilled shortfall, blocked departure, 480 kg manifest V2,
  stale V1 rejection, acknowledgement, driver POD/replay, receipt and case review.

## Reproduce with isolated Compose data

The existing planner requires explicit scenario references covering every confirmed
order for a date. The acceptance runner supplies synthetic references using the
actual references returned by store order creation. It does not change the planner
or bypass coverage validation. The fixture declares an operating day and only
one available refrigerated van so the 500 kg story stays on one compatible trip.

From the repository root (PowerShell):

```powershell
New-Item -ItemType Directory -Force .t09-verification/planning
docker compose -p waypoint-t09 -f compose.yaml -f tests/golden-path/compose.yaml up --build -d
backend/.venv/Scripts/python.exe backend/scripts/verify_golden_path.py --reference-dir .t09-verification/planning --output .t09-verification/results.json
```

The separate project uses API 8001, web 5174 and PostgreSQL 5434, plus a separate
database volume. Synthetic role credentials are the Quick Start's defaults.
The existing application volume and ignored official `local-data/` are untouched.
Results contain IDs and acceptance evidence, never bearer tokens. The runner
creates operational records; use this isolated project only. A later run must
use an unused eligible `--planning-date YYYY-MM-DD` because the preceding date's
orders have already progressed. Stop it without removing the database:

```powershell
docker compose -p waypoint-t09 -f compose.yaml -f tests/golden-path/compose.yaml down
```

The runner checks server sync with stable offline command IDs and duplicate POD
replay. Actual browser offline reload/outbox behavior is additionally covered by
the T08 IndexedDB tests and a browser acceptance check; the HTTP runner alone does
not simulate a disconnected browser.

## Verified on 2026-10-04

- Before edits: original Compose stack db/api healthy, web HTTP 200, health/readiness
  OK and all four normal seeded accounts signed in. Existing data retained.
- Backend regression: 82 passed, one optional pre-existing PostgreSQL integration
  test skipped because its environment variable was unset.
- Frontend: receiving presentation and IndexedDB regression tests, typecheck,
  lint (zero warnings) and production build pass.
- Fresh isolated PostgreSQL migrated to `c38e72f104a6` and seeded without manual SQL
  writes. API runner passed for 2026-10-06; evidence is locally ignored at
  `.t09-verification/results.json`.
- Browser journey prepared with the same runner, `--planning-date 2026-10-07
  --prepare-only`. While only the isolated API was stopped, cached trips and a
  saved receiver draft survived reload; the restored draft enabled delivery.
  Two delivered stops and three pending updates survived another reload. API
  reconnect drained the queue. This tests API-disconnected operation; web remained
  available. Full shell-disconnected reload was covered in T08.
- The store browser confirmed 32 ambient units and submitted a missing-quantity
  case for 16/18 chilled units. Dispatcher browser started review and resolved the
  recorded partial intake. PostgreSQL read-only verification found both orders
  RECEIVED, receipts CONFIRMED/PARTIAL and one POD per order.
- The browser check found and fixed draft fallback in driver completion controls;
  shell cache version was advanced without touching IndexedDB commands.
- Figma S04/S04B/S05 supplied receipt content, colors and the four bundled icons.
  Exact shared shell, all-role pages and responsive polish remain T10.

To prepare another browser run, add an unused eligible date and `--prepare-only`
to the runner command. Sign in as driver, stop just this isolated project's API,
reload, complete the stops, reload again, restart API and sync. Then sign in as
store manager to confirm/report intake and dispatcher to review any case.
