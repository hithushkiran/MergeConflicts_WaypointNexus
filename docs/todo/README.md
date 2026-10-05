# Waypoint Nexus work queue

This folder is the source of truth for unfinished project work. The old single-file checklist is preserved as [roadmap.md](roadmap.md); this index makes it usable as an ordered queue for people and coding agents.

## Start here

1. Read the repository [README](../../README.md), [foundation handoff](../FOUNDATION_HANDOFF.md), [Figma implementation handoff](../UI_IMPLEMENTATION_HANDOFF.md), and relevant ADRs.
2. Check the **Current focus** section below and inspect the code before choosing a task. The roadmap describes the intended product; it is not evidence that a feature is missing or present.
3. Claim one task in the status board, state its acceptance criteria and files/modules likely to change, then implement only that task and its dependencies.
4. Update the board and task checklist with evidence (commands run, outcome, and any blocker) when done. Do not mark work complete based only on code existing.

## Current focus

The supported Store → Dispatcher → Loader → Driver → offline sync → Store receipt workflow is implemented. Continue T10–T12 from the evidence below and the [UI handoff](../UI_IMPLEMENTATION_HANDOFF.md); code and verification evidence take precedence over stale historical checklist items.

T01–T09 are complete, including driver assignment and outlet-scoped receipt/case review. T10 core screens and the shared shell exist; exact design acceptance is unfinished and needs the missing design ZIP. T11 optional scope is awaiting agreement; no optional integration is approved. T12 fixes expired-auth replay and queue ordering, adds recovery/contrast checks and records real Compose/browser acceptance. See [current verification](../T10_T12_VERIFICATION.md) and [optional scope](../T11_SCOPE.md). T03's synthetic development data remains labeled; official local files take precedence when supplied. Do not assume every unchecked historical roadmap item is still open.

## Order and gates

Follow roadmap dependencies, prioritizing the end-to-end path:

`store order → plan → dispatcher publish → load/shortfall resolution → driver delivery → offline sync → store receipt`

P0 work and its acceptance gate must be complete before starting dependent P0 work. P1 work follows a working P0 path; P2 is optional polish. A failed relevant check blocks dependent tasks until fixed. The roadmap's phases and gates are the detailed requirements; this index does not override project architecture or ADRs.

## Agent coordination

- One owner per task at a time. Parallel work is allowed only for tasks with non-overlapping files and explicit interface agreements.
- Before editing, inspect current implementation, tests, migrations, and git status. Preserve unrelated user changes.
- Do not fabricate behavior, use hard-coded demo results as implementation, bypass validation, or use the client as the authoritative store.
- For stateful workflows, define and enforce valid transitions server-side. PostgreSQL is authoritative; realtime is advisory. Offline commands must persist and be idempotent.
- Keep changes scoped. Add or update relevant tests as part of implementation; report checks run and results. Do not claim a check passed if it was not run.
- Never reset/delete databases, volumes, or user data without explicit authorization. Document any destructive command as a human-operated step.
- If blocked, record the precise blocker, evidence, and smallest decision/input needed. Then work on an independent task only if its dependencies and files are clear.

## Status board

| ID | Workstream | Status | Owner | Depends on | Evidence / blocker |
| --- | --- | --- | --- | --- | --- |
| T01 | Reconcile foundation and development setup | done | Codex | — | Repaired the broken Buildx symlink to `/usr/libexec/docker/cli-plugins/docker-buildx`. Declares HTTPX for the backend TestClient and selects uvloop when available. `docker compose up --build -d` starts db/api/web; API `/health` and `/ready` both return success, with database readiness confirmed. Backend pytest: 8 passed, 1 skipped (optional PostgreSQL integration URL unset). Frontend test (1), typecheck, ESLint, and production build pass. |
| T02 | Authentication, authorization, and API contracts | done | Codex | T01 | DB-backed login/session/logout, development-only password seeding, frontend sign-in/session restore, server-side role guards, and shared API contracts are implemented. Backend: 20 passed, 1 skipped; frontend test, typecheck, lint, and production build pass. Trip assignment scope is deferred to T07 because no assignment field or trip API exists yet. |
| T03 | Store order workflow | done | Codex | T02 | Packaged clearly labeled synthetic development CSVs; Compose ran the idempotent seed on the existing database and live login → create → persisted list passed for `DEMO-OUT001`. No database volume was reset or deleted. Backend: 32 passed, 1 skipped; frontend test, typecheck, lint, and build pass. Official competition data remains Git-ignored and takes priority when supplied. |
| T04 | Planning and eligibility/allocation | done | Codex | T03, T02 | Added deterministic scenario/fleet/calendar/travel/service fixtures; snapshot captures availability, weekly fuel use, calendar, outlet rules, and route/service inputs. Eligibility and CP-SAT enforce temperature, van-only, depot, capacity, time windows, consumed weekly fuel, same-trip depot/brand/district, two trips/day, and operating-day rules. Allocations construct and persist draft trips, sequenced stops, ETAs, utilization, fuel, and deferrals. Supplied Task 2B checker: `FEASIBILITY: PASSED`. Backend: 54 passed, 1 skipped. Existing Compose DB volume was retained; rebuilt API is healthy with DB and web containers running. |
| T05 | Dispatcher review and plan publication | done | Codex | T04 | Dispatcher-only queue and filters, saved candidate/version review with trips/stops/metrics/ETAs/deferrals, and validated idempotent publication are implemented. Publish updates plan/trips/orders and audit history atomically; non-scenario or incomplete order coverage is rejected. Live PostgreSQL demo acceptance: generated V1 for 7 orders (6 served, 1 deferred), published, and confirmed publish replay. Backend: 58 passed, 1 skipped. Frontend: test, typecheck, lint, and production build pass. Compose API and web rebuilt; API readiness confirmed. |
| T06 | Loader, shortfall, hold, and revised manifest | done | Codex | T05 | Added depot scoped loader work, versioned manifests, auditable blocking shortfalls/hold, driver departure guard, dispatcher partial/substitute/reload/defer resolutions, and capacity checked reallocation through a reviewed replacement plan. V1/V2 differences are visible; stale manifests are rejected; acknowledgement gates READY. Backend: 60 passed, 1 skipped; frontend checks pass; Compose migration `a817c4f092e1` applied and API/web health confirmed. Each order is one shipment line because no product catalog exists; driver assignment remains T07. |
| T07 | Driver delivery and proof of delivery | done | Codex | T06 | Added same-depot assignment from the current published plan; only the assigned driver sees a trip after its current manifest is acknowledged. Departure requires READY with no blocking shortfall; stop arrival/completion is ordered, idempotent, audited, and creates timestamped proof of delivery for success or failure. Driver workspace supports receiver, outcome, and notes. Backend: 61 passed, 1 skipped; frontend test, typecheck, lint, and production build pass. Compose migration `b24d32f1e5d9` is current; DB/API are healthy, API readiness returns `ready`, and web returns HTTP 200. Existing database volume retained. Signature/photo upload is unsupported by the current storage setup. |
| T08 | Offline cache, outbox, and idempotent sync | done | Codex | T07 | Added versioned IndexedDB trip/stop/manifest cache and saved delivery drafts; registered an offline app-shell service worker; driver commands persist and replay in order with stable command/idempotency IDs, original event times, capped backoff, conflict blocking, and connection/sync feedback. Frontend: 5 tests pass, typecheck, lint, and production build pass. Backend: 61 passed, 1 skipped, including duplicate POD replay without a second record. Reloaded the app while the web container was stopped and restored the signed-in driver shell from cache; the shared demo DB has no assigned trip, so trip/outbox reload and sync were exercised with persistent IndexedDB fixtures. Compose DB/API healthy, API ready, web HTTP 200; existing database volume retained. |
| T09 | Store receipt and complete golden path | done | Codex | T08 | Outlet-scoped receipt/issue commands, dispatched quantity snapshots, immutable counted quantities, RBAC, audit, replay and dispatcher review implemented. Isolated Compose golden path passes (500→480 kg, V2); browser disconnected reload→delivery→sync→receipt/review passes with one POD per order. Backend 82 passed/1 optional integration skipped; frontend receipt/outbox tests, typecheck/lint/build pass. See `docs/T09_VERIFICATION.md`. |
| T10 | Figma core UI implementation and responsive workflow | in progress | Codex | T09 | Core UI exists; corrected contrast, narrow layout, skip-link focus, missing action label, refresh/loading feedback and misleading driver/live labels. Real viewport/axe checks and core API/browser acceptance pass; exact visual acceptance needs the design ZIP. See `docs/T10_T12_VERIFICATION.md`. |
| T11 | Optional operational panels and backend integrations | open | — | T10 | Candidate feature set presented for agreement; no response/approval yet. All six integrations remain unimplemented, with missing sources/contracts documented in `docs/T11_SCOPE.md`. Deferred/blocked candidates are not completion. |
| T12 | Security, reliability, fresh install, deployment, demo, and submission | in progress | Codex | T10 | Fixed auth replay pause/re-authentication, same-account validation, legacy auth conflict recovery, retry cleanup and monotonic queue ordering. Backend 83 passed/1 optional fixture skipped; frontend 16 passed, typecheck/lint/build pass. API, disconnected-browser and fresh-local-checkout golden paths pass. Remaining release gates/hosting decision are recorded in verification evidence. |

Statuses: `open`, `in progress`, `blocked`, `done`. Update owner/status/evidence in the same change as task progress. Split a row into smaller IDs if it is too large for one reviewable change; retain dependency order.

## Task handoff template

```text
Task ID / title:
Outcome:
In scope:
Out of scope:
Dependencies:
Acceptance criteria:
Relevant paths / interfaces:
Checks to run:
Owner:
```

Completion note:

```text
Status: done | blocked
Changes:
Acceptance evidence:
Checks run and results:
Follow-up / blocker:
```

## Detailed checklist

See [roadmap.md](roadmap.md) for phase-level requirements, specific workflow gates, and the demo/submission checklist. Check off an item only after implementation and verification; update this status board with the corresponding evidence.
