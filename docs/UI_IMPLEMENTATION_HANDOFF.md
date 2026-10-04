# Figma UI implementation handoff

This document records the review of the target UI against the current Waypoint Nexus application. It is the implementation brief for teammates working directly or with AI coding agents. It describes current capabilities as observed during the review; verify them against the code before each task because this handoff can become stale.

## Design target

[Open the Waypoint Figma file](https://www.figma.com/design/KNFRtbj8By67rMKqkZzYdw/MergeConflicts_Designathon-%25E2%2580%2594-Waypoint?node-id=1-2&p=f&t=Buczd97Y2TT0stdP-0). The `Screens by role` page includes Store Manager screens S01–S10, Dispatcher screens D01–D04 and G01–G03, Loader screens L01–L07, and Driver screens R01–R04. Treat the role screens and their linked states as the visual target; the current frontend is a temporary workflow UI.

## Current implementation at a glance

- Frontend: React and TypeScript in `frontend/src/app/App.tsx`; current role workspaces are rendered in a single app component and use utility classes. API calls and types are in `frontend/src/lib/api.ts`.
- Backend: FastAPI routes in `backend/app/modules/`; PostgreSQL models and migrations in `backend/app/infrastructure/persistence.py` and `backend/migrations/`.
- Existing operational APIs: authentication; store order eligibility/list/create; dispatcher order queue, planning, saved plans, publish, driver assignment, shortfall list/resolution; loader trip/manifests/checks/acknowledgement; driver assigned trips, depart, arrive, and complete.
- Driver offline cache and outbox are implemented in `frontend/src/lib/driverOffline.ts` and the driver workspace.
- T09 exposes outlet-scoped delivery, receipt and issue APIs, immutable receiving quantities, idempotent commands, and dispatcher issue review/closure. See [T09 verification](T09_VERIFICATION.md).
- T10 is in progress: a shared role shell and the S01–S03 store slice are implemented. Remaining role workspaces retain their temporary workflow UI. See [T10 verification and remaining work](T10_VERIFICATION.md).
- See [API contracts](api-contracts.md) for existing request and response contracts. Do not infer that a database model means a usable API already exists.

## Screen-to-capability map

| Figma area | Existing support | Work needed before presenting as live functionality |
| --- | --- | --- |
| Store S01–S03: orders, create, confirmation, planned/deferred notice | Order eligibility, order list, create, dispatcher plan and order status exist. | Build the screens and role navigation. Store APIs do not yet provide the planned trip/ETA details shown in S03; either add a scoped read API or simplify S03 to available status information. |
| Store S04/S04B/S05: receipt and discrepancy report | T09 outlet-scoped delivery/receipt/issue APIs and functional receiving UI exist. | T10 must finish Figma presentation and responsive visual verification, preserving T09 state transitions, immutable quantities, authorization and replay semantics. |
| Store S06–S10: history, detail, dashboard, profile, settings | Order list and `/auth/me` exist. | History can start from the order list; decide whether detail and dashboard summaries can be derived safely from existing data. Outlet profile and preferences/settings need supporting data and APIs if they remain interactive. |
| Dispatcher D01–D04: confirmed queue, plan, deferral, publish/assignment | Queue/filter, candidate plan, saved versions, publish, driver assignment, deferral decisions and shortfall resolution exist. | Build the screens against current APIs. D03 currently has no separate editable deferral-note command; the planner's reason is authoritative. Manual plan editing is not supported. Keep driver assignment aligned with the published plan/state rules. |
| Dispatcher G01–G03: live routes, shortfall decision, future capacity | Shortfall list/resolution exists. Plan results contain trips and metrics. | Shortfall decision can use current APIs. A live route feed and forward-looking capacity forecast are not present; keep these as out of scope or define new API/data requirements before implementation. |
| Loader L01–L04: route, checklist, exception/hold, revised manifest/release | Loader trip list, manifest versions, load checks, shortfall hold, current manifest acknowledgement, and READY transition exist. | Build the core path now. Current loader list omits some route/driver context shown in Figma; add only fields needed by an agreed screen. Model L04 acknowledgement/READY accurately: there is no separate gate-release command. |
| Loader L05–L07: settings, intercom, telemetry | No operational settings, messaging/intercom, or telemetry APIs/integrations exist. | Defer or remove from the judgeable flow until real sources, ownership, data freshness, and action semantics are agreed. Do not show fabricated live values. |
| Driver R01–R04: route, stop, proof, offline/sync | Assigned trips, ordered stop commands, receiver/outcome/notes POD, and offline cache/outbox/sync exist. | Build the core driver screens now. Photo/signature capture and upload need an agreed storage approach and backend contract; they are not supported currently. |

## Required shared demo story

Use one consistent scenario across role screens and states:

1. Dispatcher publishes an initial manifest with 320 kg dry and 180 kg chilled (500 kg planned total).
2. Loader records 160 kg chilled present, identifies a 20 kg shortfall, and places the trip on dispatch hold.
3. Dispatcher reviews the exception and approves partial fulfillment (or the selected resolution) with a recorded reason.
4. The replacement manifest shows 320 kg dry plus 160 kg chilled (480 kg total); loader verifies and acknowledges that version.
5. The assigned driver departs, records ordered stop outcomes, and syncs any offline commands.
6. Store confirms received quantities or reports the chilled discrepancy; the issue is visible to the appropriate operational role.

Before implementation, reconcile any Figma frame that shows another quantity, status, ETA, driver, or action with this sequence. In particular, keep initial 500 kg and revised 480 kg states distinct. Do not hard-code sample operational data into the product UI to imitate missing APIs.

## Recommended implementation sequence

### T09 — Store receipt and complete golden path

1. Inspect `Receipt`, `DeliveryIssue`, `ProofOfDelivery`, `Order`, and relevant audit/idempotency patterns, plus the Figma S04/S04B/S05 frames.
2. Agree receipt semantics: who may submit, which deliveries/orders are eligible, whether partial receipt is allowed, how duplicate submissions behave, which discrepancy fields are required, and how a case is reviewed/resolved.
3. Document the request/response contract in `docs/api-contracts.md` before frontend wiring. Add outlet-scoped store receipt/read and issue-report/read endpoints only as required by the agreed flow. Enforce authorization and legal state transitions in the backend.
4. Add migrations only if existing tables cannot represent the agreed workflow. Preserve existing data and never reset a shared database as part of this task.
5. Add backend tests for success, scope/role denial, invalid transition, partial quantity, discrepancy, and idempotent retry; connect S04/S04B/S05.
6. Run the full seeded path from store order through planning, loading shortfall, resolution, revised manifest acknowledgement, driver POD, and store receipt. Record the exact checks and results in the T09 board row.

### T10 — Core Figma UI and responsive workflow

1. Inventory the Figma frames, states, interactions, and shared visual rules before replacing the temporary frontend. Keep this handoff and `docs/api-contracts.md` open while planning.
2. Build a shared app shell (brand/header/navigation/account context) and role-aware navigation. Use reusable components for tables/cards, status labels, forms, alerts, loading/empty/error states, and confirmation actions.
3. Implement in operational order: Store order screens (S01–S03), Dispatcher (D01–D04/G02), Loader (L01–L04), Driver (R01–R04), then Store receipt screens (S04/S04B/S05). Keep role authorization server-side; hidden navigation is not security.
4. Bind every displayed value and action to an existing or newly agreed API. Clearly label estimates and timestamps; do not invent live sync, route, forecast, telemetry, or notification data.
5. Make the workflows usable on the screen sizes represented by the role designs, with the driver flow usable on a narrow/mobile display. Preserve accessible labels, keyboard behavior, focus visibility, and status meaning beyond color.
6. Implement remaining store history/dashboard/profile/settings and optional dispatcher panels only after checking the map above and recording any required API work. Do not expand scope by building decorative panels with fake data.
7. Verify each role path using seeded accounts and realistic API state. For visual review, compare the running screen with its corresponding Figma frame at the same viewport and record unresolved mismatches rather than silently changing backend behavior to fit a mock.

### T11 — Optional operational panels and integrations

Before starting each panel, write down its user, authoritative data source, freshness/latency, actions, permissions, failure state, API contract, and acceptance criteria. Prioritize only what the team and judging/demo scope require. Potential work includes live-route status, capacity forecasts, telemetry, station controls, intercom/messaging, store profile/preferences, and photo/signature POD storage.

### T12 — Regression and delivery

Run relevant backend and frontend tests, typecheck/lint/build, then verify the complete golden path in Compose from the seeded environment. Review responsive layouts, role boundaries, error/loading/empty states, fresh-install instructions, and docs. Update this handoff and the TODO evidence as implementation changes.

## How to pick up work (human or AI agent)

1. Start with [Quick Start](QUICK_START.md), then read [the TODO board](todo/README.md), this handoff, and [API contracts](api-contracts.md).
2. Inspect current branch, `git status`, the relevant Figma frame, implementation, tests, and migrations. The Figma and this map are guidance; code and tests are the evidence for current behavior.
3. Claim one task in the TODO board. State the outcome, scope, dependencies, acceptance criteria, likely files, and checks before editing. Avoid overlapping file ownership unless the team explicitly agrees on interfaces.
4. Implement one vertical workflow slice. Keep business rules and authorization in the backend; keep React as a client of documented APIs. Reuse existing behavior instead of duplicating it.
5. Add/adjust focused tests, run checks required by the task, and report commands/results. Do not claim a test or UI state works without verifying it.
6. Update the TODO row and relevant docs in the same change. Record unresolved assumptions as explicit blockers/decisions. Never commit official competition data, credentials, or fabricated live values.

## Decisions still needed

- Confirm the canonical shortfall resolution for the demo (partial fulfillment is assumed above) and whether any exact Figma frame must be changed to match it.
- Receipt/issue lifecycle and dispatcher review/close are defined and implemented in T09; use the existing API contracts rather than reopening those decisions.
- Decide which of the optional operational panels are in the deliverable scope. Do not treat them as prerequisites for the working core golden path.
- Agree whether POD photo/signature is required; if yes, select storage and upload constraints before designing the API.
