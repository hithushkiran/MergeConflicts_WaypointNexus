# Waypoint Nexus — Detailed Product Roadmap

This is the detailed requirements checklist referenced by [`README.md`](README.md). Use the queue and status board there to select and assign work. This roadmap is not a live status report: unchecked items need verification against the repository before being treated as open.

## Priority hierarchy

| Priority | Meaning                                      | Agent behavior                    |
| -------- | -------------------------------------------- | --------------------------------- |
| **P0**   | Required for the judgeable end-to-end system | Must complete and verify          |
| **P1**   | Important supporting functionality           | Only after P0 is stable           |
| **P2**   | Polish / nonessential                        | Only if everything else is stable |

The core system the agent should optimize for is:

**Store Order → Planning → Dispatcher Review → Publish → Loading → Shortfall → Dispatcher Resolution → Revised Manifest → Driver → Offline Delivery → Sync → Store Receipt**

---

# PHASE 0 — Understand Before Coding

### 0.1 Inspect the existing repository

* [ ] Inspect frontend structure.
* [ ] Inspect backend structure.
* [ ] Inspect database setup.
* [ ] Inspect existing routes/API.
* [ ] Inspect existing components/pages.
* [ ] Inspect existing tests.
* [ ] Inspect Docker configuration.
* [ ] Inspect environment configuration.
* [ ] Identify what is already implemented.
* [ ] Do **not** rewrite working code unnecessarily.

### 0.2 Establish the architecture

Confirm:

```text
Frontend
    ↓
REST API
    ↓
Business services
    ↓
PostgreSQL
```

Realtime/WebSocket functionality should be an accelerator, **not the authoritative source of state**.

### 0.3 Establish the core state model

Before implementing workflows, define the important states:

```text
ORDER
  → CONFIRMED
  → PLANNED
  → DEFERRED
  → DELIVERED
  → RECEIVED

PLAN
  → DRAFT
  → PUBLISHED
  → REVISED

TRIP
  → PLANNED
  → LOADING
  → DISPATCH_HOLD
  → READY
  → IN_TRANSIT
  → COMPLETED

DELIVERY
  → PENDING
  → DELIVERED
  → FAILED
```

The exact existing project model should take precedence if already defined.

### Gate 0

Do not proceed until:

* [ ] Project builds.
* [ ] Existing tests pass.
* [ ] Local development environment starts.
* [ ] Database connects.
* [ ] Agent understands existing architecture.
* [ ] No unnecessary destructive refactor is planned.

---

# PHASE 1 — F0 FOUNDATION

**Priority: P0**

This is the first actual implementation phase.

## 1.1 Repository/development setup

* [ ] Ensure frontend builds.
* [ ] Ensure backend builds.
* [ ] Establish shared configuration.
* [ ] Establish development scripts.
* [ ] Establish `.gitignore`.
* [ ] Establish `.env.example`.
* [ ] Document local startup.

### Verify

```text
frontend starts
backend starts
database starts
```

---

## 1.2 Docker Compose

* [ ] PostgreSQL container.
* [ ] Backend container.
* [ ] Frontend container.
* [ ] Health checks.
* [ ] Environment variables.
* [ ] Database connectivity.
* [ ] One-command startup.

### Gate

Run:

```bash
docker compose up
```

and verify the complete stack starts successfully.

**If this fails, stop. Do not continue.**

---

# PHASE 2 — DATABASE

**Priority: P0**

Build the minimum complete domain model.

## 2.1 Core entities

* [ ] Users
* [ ] Roles
* [ ] Outlets
* [ ] Vehicles
* [ ] Depots
* [ ] Orders
* [ ] Plans
* [ ] Trips
* [ ] Stops
* [ ] Loading records
* [ ] Shortfalls
* [ ] Deliveries
* [ ] Receipts
* [ ] Audit events
* [ ] Sync/idempotency records

## 2.2 Database migrations

* [ ] Migration system configured.
* [ ] Initial migration created.
* [ ] Fresh database migration tested.
* [ ] Reset/rebuild tested.

## 2.3 Seed data

Create deterministic data for:

* [ ] Dispatcher
* [ ] Loader
* [ ] Driver
* [ ] Store
* [ ] Depots
* [ ] Vehicles
* [ ] Outlets
* [ ] Orders
* [ ] Golden-path scenario
* [ ] Shortfall scenario
* [ ] Deferred-order scenario

### Gate

Destroy the database.

Recreate it.

Run migrations.

Run seed.

Verify all expected data exists.

**Only continue when a completely fresh database works.**

---

# PHASE 3 — AUTHENTICATION + RBAC

**Priority: P0**

## 3.1 Authentication

* [ ] Login endpoint.
* [ ] Login UI.
* [ ] Session/token handling.
* [ ] Logout.
* [ ] Protected routes.

## 3.2 Roles

Implement:

```text
STORE
DISPATCHER
LOADER
DRIVER
```

## 3.3 Authorization

Verify:

* [ ] Store cannot access dispatcher operations.
* [ ] Dispatcher cannot impersonate driver/store.
* [ ] Loader can access loading workflow.
* [ ] Driver can access assigned trip.
* [ ] Unauthorized API requests return correct errors.

### Gate

Create automated authorization tests.

**Do not proceed until RBAC tests pass.**

---

# PHASE 4 — SHARED API CONTRACTS

**Priority: P0**

Before building the individual interfaces:

* [ ] Define API response structure.
* [ ] Define API error structure.
* [ ] Define IDs.
* [ ] Define enums.
* [ ] Define state transitions.
* [ ] Define pagination where needed.
* [ ] Define event structure.
* [ ] Define idempotency structure.

Document the contracts.

### Gate

Frontend can consume backend APIs without ad-hoc response handling.

---

# PHASE 5 — STORE ORDER CREATION

**Priority: P0**

This is the first real business workflow.

## 5.1 Store dashboard

* [ ] Store login.
* [ ] Store dashboard.
* [ ] Order list.
* [ ] Order status.
* [ ] Loading state.
* [ ] Error state.
* [ ] Empty state.

## 5.2 Order creation

* [ ] Product/order form.
* [ ] Quantity.
* [ ] Requested date.
* [ ] Validation.
* [ ] Submit.
* [ ] Order reference.

## 5.3 Cutoff

* [ ] Cutoff calculation.
* [ ] Colombo timezone handling.
* [ ] Late-order handling.
* [ ] Next eligible run.
* [ ] Explanation to user.

### Gate 1 — ORDER

The agent should be able to:

```text
Login as Store
      ↓
Create order
      ↓
Order persists in database
      ↓
Order appears in dashboard
```

Run this from a **fresh seeded environment**.

If it fails, fix it before continuing.

---

# PHASE 6 — PLANNING FOUNDATION

**Priority: P0**

Now implement the most technically important backend component.

## 6.1 Planning snapshot

Collect:

* [ ] Orders
* [ ] Vehicles
* [ ] Depots
* [ ] Capacity
* [ ] Weight
* [ ] Volume
* [ ] Temperature requirements
* [ ] Access restrictions
* [ ] Delivery windows
* [ ] Fuel constraints
* [ ] Travel/service information

Create a deterministic snapshot.

---

# PHASE 7 — ELIGIBILITY ENGINE

**Priority: P0**

Implement hard constraints independently from the optimizer.

Check:

* [ ] Depot compatibility.
* [ ] Vehicle availability.
* [ ] Weight capacity.
* [ ] Volume capacity.
* [ ] Temperature compatibility.
* [ ] Access restrictions.
* [ ] Delivery window.
* [ ] Fuel.
* [ ] Trip constraints.

Every rejection must have a reason.

Example:

```text
DEFERRED
reason:
  VEHICLE_CAPACITY_EXCEEDED
```

rather than:

```text
DEFERRED
reason:
  FAILED
```

### Gate

Create constraint tests.

Examples:

* [ ] Too much weight.
* [ ] Too much volume.
* [ ] Wrong temperature vehicle.
* [ ] Vehicle unavailable.
* [ ] Delivery window impossible.
* [ ] Fuel impossible.

**Do not build the UI around the planner until these tests work.**

---

# PHASE 8 — OPTIMIZATION / ALLOCATION

**Priority: P0**

Implement the OR-Tools allocation component.

## 8.1 Vehicle assignment

* [ ] Assign orders to eligible vehicles.
* [ ] Respect capacity.
* [ ] Respect temperature.
* [ ] Respect access.
* [ ] Respect delivery windows.

## 8.2 Trip construction

* [ ] Create trips.
* [ ] Create stops.
* [ ] Create stop sequence.
* [ ] Calculate utilization.
* [ ] Calculate ETA.
* [ ] Track fuel-related constraints.

## 8.3 Deferral

If not all orders can be served:

* [ ] Mark deferred.
* [ ] Generate reason.
* [ ] Preserve deterministic output.

## 8.4 Timeout/no solution

* [ ] Detect optimizer timeout.
* [ ] Return best feasible result where available.
* [ ] Return diagnostics.
* [ ] Never silently relax hard constraints.

### Gate 2 — PLANNING

The agent should be able to run:

```text
Seeded orders
      ↓
Planning snapshot
      ↓
Eligibility
      ↓
Optimization
      ↓
Vehicle/trip allocation
      ↓
Served/deferred orders
      ↓
Constraint reasons
```

This is a **major P0 checkpoint**.

---

# PHASE 9 — DISPATCHER

**Priority: P0**

Now expose planning to the dispatcher.

## 9.1 Dispatcher queue

* [ ] Orders awaiting planning.
* [ ] Filters.
* [ ] Depot.
* [ ] Brand.
* [ ] District.
* [ ] Temperature.
* [ ] Access.
* [ ] Delivery window.
* [ ] Prior deferral.

## 9.2 Candidate plan

Display:

* [ ] Served orders.
* [ ] Deferred orders.
* [ ] Vehicles.
* [ ] Trips.
* [ ] Stops.
* [ ] Utilization.
* [ ] ETA.
* [ ] Fuel.
* [ ] Warnings.
* [ ] Deferral reasons.

## 9.3 Publish

* [ ] Validate plan.
* [ ] Publish plan.
* [ ] Create version.
* [ ] Prevent accidental modification of published version.
* [ ] Audit publication.

### Gate 3 — PLAN PUBLISHED

Verify:

```text
Store order
     ↓
Planner
     ↓
Dispatcher
     ↓
Review
     ↓
Publish V1
```

No manual database manipulation should be necessary.

---

# PHASE 10 — LOADER

**Priority: P0**

## 10.1 Trip list

* [ ] Assigned trips.
* [ ] Vehicle.
* [ ] Driver.
* [ ] Departure.
* [ ] Plan version.

## 10.2 Manifest

* [ ] Stop sequence.
* [ ] Products.
* [ ] Quantities.
* [ ] Load sequence.
* [ ] Manifest version.

## 10.3 Loading verification

Support:

```text
LOADED
MISSING
DAMAGED
SUBSTITUTE
```

Record:

* [ ] Quantity.
* [ ] Notes.
* [ ] Actor.
* [ ] Timestamp.

---

# PHASE 11 — SHORTFALL + DISPATCH HOLD

**Priority: P0**

This is one of the most important recovery workflows for the demo.

## 11.1 Shortfall

* [ ] Loader reports missing/damaged quantity.
* [ ] Persist shortfall.
* [ ] Determine whether it is blocking.

## 11.2 Blocking shortfall

If blocking:

```text
Trip
 ↓
DISPATCH_HOLD
```

* [ ] Driver cannot depart.
* [ ] Dispatcher sees exception.
* [ ] Audit event created.

### Gate 4 — RECOVERY TRIGGER

Demonstrate:

```text
Published Manifest V1
       ↓
Loader finds shortage
       ↓
Shortfall created
       ↓
Trip = DISPATCH_HOLD
       ↓
Driver departure blocked
       ↓
Dispatcher notified
```

**Do not proceed until this works.**

---

# PHASE 12 — DISPATCHER EXCEPTION RESOLUTION

**Priority: P0**

Dispatcher must be able to resolve the shortfall.

Support the required resolution path(s):

* [ ] Partial fulfillment.
* [ ] Substitute.
* [ ] Reallocation.
* [ ] Reload found.
* [ ] Defer.

Every resolution must have a reason.

---

# PHASE 13 — REVISED MANIFEST

**Priority: P0**

Implement manifest versioning.

Example:

```text
Manifest V1
    ↓
Shortfall
    ↓
Dispatcher resolution
    ↓
Manifest V2
```

* [ ] Create V2.
* [ ] Compare V1 vs V2.
* [ ] Highlight differences.
* [ ] Reject stale V1.
* [ ] Loader acknowledges V2.
* [ ] Departure readiness updates.

### Gate 5 — RECOVERY COMPLETE

The complete recovery workflow must work:

```text
V1
 ↓
Loading
 ↓
Shortfall
 ↓
HOLD
 ↓
Dispatcher resolution
 ↓
V2
 ↓
Loader acknowledgement
 ↓
READY
```

---

# PHASE 14 — DRIVER WORKSPACE

**Priority: P0**

Only now build the driver experience.

## 14.1 Trip

* [ ] Trip summary.
* [ ] Vehicle.
* [ ] Driver.
* [ ] Stops.
* [ ] Outlet information.
* [ ] Delivery windows.
* [ ] Instructions.

## 14.2 Stop workflow

Implement:

```text
READY
 ↓
START TRIP
 ↓
ARRIVED
 ↓
DELIVERED
```

and failure handling:

```text
ARRIVED
 ↓
FAILED
 ↓
REASON
```

## 14.3 Departure gate

Driver must not depart when:

```text
DISPATCH_HOLD
```

Driver must receive only the current acknowledged manifest.

---

# PHASE 15 — PROOF OF DELIVERY

**Priority: P0**

Implement:

* [ ] Receiver.
* [ ] Outcome.
* [ ] Timestamp.
* [ ] Notes.
* [ ] Signature/photo reference if supported.
* [ ] Validation.

### Gate 6 — ONLINE DELIVERY

Verify:

```text
Driver
 ↓
Trip
 ↓
Stop
 ↓
Arrive
 ↓
Deliver
 ↓
POD
 ↓
Delivery completed
```

---

# PHASE 16 — OFFLINE CACHE

**Priority: P0**

This should be treated as a separate engineering milestone rather than a UI feature.

Implement IndexedDB/local persistence for:

* [ ] Trip.
* [ ] Stops.
* [ ] Manifest version.
* [ ] Delivery drafts.
* [ ] Schema version.

### Test

```text
Open trip
 ↓
Turn network OFF
 ↓
Reload browser
 ↓
Trip still available
```

If this doesn't work, stop.

---

# PHASE 17 — OFFLINE OUTBOX

**Priority: P0**

Implement:

* [ ] Command queue.
* [ ] Pending status.
* [ ] Retry.
* [ ] Backoff.
* [ ] Persistence after reload.
* [ ] Connectivity indicator.

Example:

```text
OFFLINE
 ↓
Driver marks delivered
 ↓
Command stored locally
 ↓
Pending
```

---

# PHASE 18 — IDEMPOTENT SYNC

**Priority: P0**

This is critical.

Every offline command should have something like:

```text
command_id
idempotency_key
```

Implement:

* [ ] Server acknowledgement.
* [ ] Duplicate detection.
* [ ] Retry.
* [ ] Sync error.
* [ ] Conflict handling.

### Critical test

Do this:

```text
OFFLINE
 ↓
Deliver
 ↓
Reconnect
 ↓
Sync
 ↓
Sync again
```

Expected:

```text
ONE delivery
```

Not:

```text
TWO deliveries
```

### Gate 7 — OFFLINE RECOVERY

The agent must pass:

```text
Open trip
 ↓
Go offline
 ↓
Reload
 ↓
Complete delivery
 ↓
Reconnect
 ↓
Sync
 ↓
Server accepts once
 ↓
Duplicate sync is ignored
```

---

# PHASE 19 — STORE RECEIPT

**Priority: P0**

Connect driver completion back to store.

Implement:

* [ ] Delivered status.
* [ ] Quantity comparison.
* [ ] Store receipt.
* [ ] Receiver.
* [ ] Timestamp.
* [ ] Duplicate receipt prevention.

### Gate 8 — COMPLETE GOLDEN PATH

The entire application must now support:

```text
STORE
  Create Order
       ↓
DISPATCHER
  Generate Plan
       ↓
  Review Plan
       ↓
  Publish V1
       ↓
LOADER
  Load Manifest
       ↓
  Discover Shortfall
       ↓
DISPATCHER
  Resolve Shortfall
       ↓
  Publish V2
       ↓
LOADER
  Acknowledge V2
       ↓
DRIVER
  Start Trip
       ↓
  Go Offline
       ↓
  Deliver
       ↓
  Reconnect
       ↓
  Sync
       ↓
STORE
  Confirm Receipt
```

**This is the most important checkpoint in the entire project.**

---

# PHASE 20 — AUDITABILITY

**Priority: P1**

Once the golden path works:

* [ ] Actor.
* [ ] Timestamp.
* [ ] Action.
* [ ] Entity.
* [ ] Reason.
* [ ] Plan version.
* [ ] Correlation ID.

Record major actions.

Examples:

```text
ORDER_CREATED
PLAN_GENERATED
PLAN_PUBLISHED
SHORTFALL_CREATED
TRIP_HELD
PLAN_REVISED
MANIFEST_ACKNOWLEDGED
DELIVERY_COMPLETED
SYNC_COMPLETED
RECEIPT_CONFIRMED
```

---

# PHASE 21 — REALTIME

**Priority: P1**

Only after REST/state transitions are reliable.

Implement realtime events for:

* [ ] Plan published.
* [ ] Deferral.
* [ ] Shortfall.
* [ ] Manifest revision.
* [ ] Departure.
* [ ] Delivery.
* [ ] Receipt.

Important rule:

> WebSocket failure must not corrupt the application state.

REST/database state remains authoritative.

---

# PHASE 22 — PRIORITY / FAIRNESS

**Priority: P1**

Implement the planner's explainable priority policy.

Include:

* [ ] Prior deferral.
* [ ] Time since service.
* [ ] Outlet priority.
* [ ] Deterministic tie-breaking.
* [ ] Explainable score components.

Test deterministic output.

Same input should produce the same result.

---

# PHASE 23 — OPERATIONS DASHBOARD

**Priority: P1**

Dispatcher dashboard:

* [ ] Service rate.
* [ ] Deferrals.
* [ ] Vehicle utilization.
* [ ] Fuel.
* [ ] Exceptions.
* [ ] Sync backlog.
* [ ] Repeated deferral.

Do not spend significant time on visualization polish before the P0 workflow is stable.

---

# PHASE 24 — MANUAL PLANNING ADJUSTMENT

**Priority: P1**

Implement:

* [ ] Move order.
* [ ] Move vehicle.
* [ ] Resequence stop.
* [ ] Defer.
* [ ] Restore.

Every manual operation must pass the independent hard-constraint validator.

The agent must never allow the UI to create an invalid plan simply because the user manually changed it.

---

# PHASE 25 — ERROR / FAILURE STATES

**Priority: P1**

Every major screen needs:

* [ ] Loading state.
* [ ] Empty state.
* [ ] Error state.
* [ ] Retry.
* [ ] Permission denied.
* [ ] Offline state where relevant.
* [ ] Stale version state.
* [ ] Conflict state where relevant.

---

# PHASE 26 — RESPONSIVE VERIFICATION

**Priority: P1**

Verify the intended device contexts:

### Dispatcher

Desktop/large screen.

### Loader

Tablet/shared terminal.

### Driver

Phone.

### Store

Desktop/phone.

Especially test:

```text
360px width
```

for driver workflows.

---

# PHASE 27 — SECURITY TEST

**Priority: P0/P1**

Before release:

* [ ] Authentication.
* [ ] Role authorization.
* [ ] Store scope.
* [ ] Depot scope.
* [ ] Driver scope.
* [ ] Unauthorized API access.
* [ ] Input validation.
* [ ] Invalid state transitions.
* [ ] Duplicate commands.
* [ ] Duplicate receipt.
* [ ] Stale manifest.

---

# PHASE 28 — FULL AUTOMATED TEST SUITE

**Priority: P0**

The agent should now run:

### Backend

* [ ] Unit tests.
* [ ] Constraint tests.
* [ ] Planner tests.
* [ ] API tests.
* [ ] Auth tests.
* [ ] Idempotency tests.
* [ ] State-transition tests.

### Frontend

* [ ] Build.
* [ ] Type check.
* [ ] Lint.
* [ ] Component/workflow tests.

### Integration

* [ ] Store → Planner.
* [ ] Planner → Dispatcher.
* [ ] Dispatcher → Loader.
* [ ] Loader → Dispatcher.
* [ ] Dispatcher → Loader revision.
* [ ] Loader → Driver.
* [ ] Driver → Store.
* [ ] Offline → Sync.

---

# PHASE 29 — FRESH INSTALL TEST

**Priority: P0**

This should be treated as a hard release gate.

Delete the local environment.

Then execute only the documented process:

```bash
git clone ...
docker compose up
```

Then:

* [ ] Migration works.
* [ ] Seed works.
* [ ] Four accounts work.
* [ ] Golden path works.
* [ ] No manual DB changes.
* [ ] No undocumented setup.
* [ ] No missing environment variables.

If a developer cannot reproduce it from the README, the release is not ready.

---

# PHASE 30 — DEPLOYMENT

**Priority: P0**

* [ ] Production backend.
* [ ] Production frontend.
* [ ] Production database.
* [ ] Environment variables.
* [ ] Migration.
* [ ] Seed.
* [ ] Health endpoint.
* [ ] Public URL.
* [ ] HTTPS if applicable.
* [ ] Verify production golden path.

---

# PHASE 31 — DEMO HARDENING

**Priority: P0**

Now stop adding features.

Run the exact judge workflow repeatedly.

### Demo Run #1

```text
Store → Order
```

### Demo Run #2

```text
Order → Planning → Publish
```

### Demo Run #3

```text
Publish → Load → Shortfall → Hold
```

### Demo Run #4

```text
Resolution → V2 → Driver
```

### Demo Run #5

```text
Driver → Offline → Delivery → Sync
```

### Demo Run #6

```text
Store → Receipt
```

### Demo Run #7

Run **everything from a clean reset**.

---

# PHASE 32 — SUBMISSION

**Priority: P0**

Final checklist:

* [ ] Public deployed URL.
* [ ] GitHub repository.
* [ ] README.
* [ ] Setup instructions.
* [ ] Seed credentials.
* [ ] Architecture documentation.
* [ ] Data model documentation.
* [ ] Docker Compose.
* [ ] `.env.example`.
* [ ] AI disclosure.
* [ ] Demo script.
* [ ] Demo video.
* [ ] Final regression test.
* [ ] Fresh-install verification.

---

# What the Coding Agent Should NOT Do

Give the agent these rules explicitly.

### Rule 1 — Never parallelize unfinished P0 work

Bad:

```text
Planner 30%
Store 50%
Driver 20%
Dashboard 40%
```

Good:

```text
Foundation       100% ✓
       ↓
Database         100% ✓
       ↓
Auth             100% ✓
       ↓
Store Order      100% ✓
       ↓
Planner          100% ✓
       ↓
Dispatcher       100% ✓
```

---

### Rule 2 — Never move forward with failing tests

The agent should follow:

```text
Implement
   ↓
Test
   ↓
FAIL?
 ┌───┴───┐
YES     NO
 ↓       ↓
FIX    VERIFY
 ↓       ↓
TEST    NEXT
```

---

### Rule 3 — Never fake functionality

For example, don't implement a planner that simply returns hardcoded trips because the UI needs something to display.

Temporary fixtures are acceptable **only during development**, and must be explicitly replaced before the relevant P0 gate.

---

### Rule 4 — Database is authoritative

Don't make the frontend the source of truth for:

* orders
* plans
* manifests
* trip state
* deliveries
* receipts

---

### Rule 5 — Offline commands must be idempotent

This is non-negotiable.

```text
command A
command A
command A
```

must not produce three deliveries.

---

### Rule 6 — Don't polish prematurely

Do not spend an hour making a dashboard beautiful while:

```text
POST /orders
```

is broken.

---

# Recommended Agent Execution Queue

If you want to give the coding agent a **single concise ordered queue**, use this:

```text
01. Inspect repository and existing implementation
02. Establish architecture and state model
03. Fix development/build setup
04. Docker Compose
05. Database schema
06. Migrations
07. Deterministic seed data
08. Authentication
09. RBAC
10. Shared API contracts

11. Store dashboard
12. Store order creation
13. Order cutoff/confirmation
14. Verify Store → Order

15. Planning snapshot
16. Eligibility engine
17. Hard-constraint validator
18. OR-Tools allocation
19. Deferral engine
20. Planner timeout/no-solution handling
21. Verify Planning independently

22. Dispatcher queue
23. Dispatcher candidate plan
24. Plan validation
25. Plan publication/versioning
26. Verify Order → Planning → Publish

27. Loader trip list
28. Versioned manifest
29. Loading verification
30. Shortfall
31. DISPATCH_HOLD
32. Dispatcher exception inbox
33. Shortfall resolution
34. Revised manifest
35. Loader acknowledgement
36. Verify V1 → Shortfall → HOLD → V2

37. Driver trip workspace
38. Driver state machine
39. Departure gate
40. Proof of delivery
41. Verify online delivery

42. IndexedDB offline cache
43. Offline outbox
44. Idempotent synchronization
45. Sync/recovery UX
46. Verify offline delivery → sync

47. Driver → Store delivery integration
48. Store receipt
49. Verify complete golden path

50. Audit trail
51. Realtime updates
52. Priority/fairness
53. Manual planning adjustment
54. Operations dashboard
55. Error/loading/empty states
56. Responsive/mobile hardening

57. Security regression
58. Automated test suite
59. Full integration test
60. Fresh-install test
61. Production deployment
62. Production golden-path test
63. README/docs
64. AI disclosure
65. Demo preparation
66. Final regression
67. Submission
```

## The most important instruction to put at the top of the agent prompt

> **Work strictly from the ordered TODO list. Complete one item at a time. After every P0 item, run the relevant tests and verify the acceptance criteria. Do not proceed to the next item if the current item is broken. After completing a milestone, run the complete preceding workflow to ensure that new changes have not regressed existing functionality. Prioritize a working end-to-end golden path over feature breadth or UI polish. Do not implement P1/P2 functionality while any P0 milestone is failing.**

This is the approach I would use for your four-day constraint: **build vertically toward the judgeable golden path first, then harden it, then add P1 functionality.** It also aligns with the implementation plan's principle that the project should optimize for an **integrated judge-ready workflow rather than the number of individually completed screens**.
