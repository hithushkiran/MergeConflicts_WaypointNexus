# API contracts

This document is the shared contract for the REST API and frontend. It describes the conventions new endpoints must follow. The API currently exposes `/health`, `/ready`, and the authentication endpoints listed below.

## Base conventions

- API routes use the `/api/v1` prefix. Health probes stay at `/health` and `/ready`.
- Request and response bodies use JSON with `snake_case` field names.
- Timestamps are RFC 3339 UTC values (for example `2026-10-04T12:30:00Z`). Business cutoff calculations use `Asia/Colombo`.
- Operational entity IDs are UUIDs. Official outlet and vehicle identifiers remain their stable source IDs, such as `OUT001` and `VEH001`.
- Successful responses return the resource shape directly. Collection responses use `{ "items": [], "next_cursor": null }` when paginated; `limit` defaults to 50 and is capped at 100.
- Errors use `{ "detail": { "code": "...", "message": "...", "fields": [] } }`. Each field entry has `field` and `message`; omit `fields` when there are no field-specific validation details. Never include secrets, SQL, or connection strings.
- Use standard HTTP status codes: `400` malformed command, `401` missing/invalid authentication, `403` authenticated but not allowed, `404` absent or out-of-scope resource, `409` version/state/idempotency conflict, `422` invalid fields, and `500` unexpected server error.

## Authentication

Login is `POST /api/v1/auth/login` with `{ "email": "...", "password": "..." }`. Success returns a short-lived opaque bearer token, its expiry, and the public user profile:

```json
{
  "access_token": "opaque-token",
  "token_type": "bearer",
  "expires_at": "2026-10-04T13:30:00Z",
  "user": {
    "id": "uuid",
    "email": "dispatcher@example.test",
    "display_name": "Dispatcher",
    "role": "DISPATCHER",
    "outlet_id": null,
    "depot_code": null
  }
}
```

Send the token as `Authorization: Bearer <access_token>`. `GET /api/v1/auth/me` returns the same public profile. `POST /api/v1/auth/logout` revokes the current session and returns `204 No Content`. Password hashes and token hashes are never returned. Invalid credentials use the same `401 INVALID_CREDENTIALS` response whether the email is unknown or the password is wrong.

The database role code `STORE_MANAGER` maps to API role `STORE`; the other API roles are `DISPATCHER`, `LOADER`, and `DRIVER`. Store accounts are scoped to their `outlet_id`, and depot users are scoped to their `depot_code`. Missing scope is not treated as unrestricted access. Drivers can access only trips assigned to their account.

Authorization dependencies are provided for protected route handlers through `require_roles(...)` in the identity module. Every future operational route must declare its allowed roles and enforce outlet/depot/assignment scope in the handler or service. Authentication endpoints are intentionally available to all roles; `/me` and `/logout` require a valid session.

## Store orders

`GET /api/v1/store/orders/eligibility` returns the current cutoff and earliest eligible delivery date. `GET /api/v1/store/orders` returns the signed-in store's orders as `{ "items": [], "next_cursor": null }`. Both require the `STORE` role and an assigned outlet; callers cannot choose an outlet in the request.

`POST /api/v1/store/orders` creates a confirmed shipment request and requires an `Idempotency-Key`. The body contains `requested_delivery_date`, `temperature_requirement` (`AMBIENT`, `CHILLED`, or `FROZEN`), positive `units`, `weight_kg`, `volume_m3`, and optional `notes`. The server takes `outlet_id` from the authenticated account. Replaying the same key and request returns the original order; a different request with that key returns `409 IDEMPOTENCY_KEY_REUSED`.

The configurable `ORDER_CUTOFF_LOCAL_TIME` defaults to 16:00 in `Asia/Colombo`. Before or at the cutoff, orders may be requested for the current calendar date; after it, the next eligible date is the following calendar date. The official business calendar is not present, so weekends and holidays are not skipped. A date earlier than the next eligible date returns `422 ORDER_DATE_TOO_SOON` with the eligible date and explanation. Stored and returned timestamps use UTC.

## Dispatcher planning and publication

All dispatcher routes require a `DISPATCHER` bearer session. `GET /api/v1/dispatcher/orders` returns confirmed orders with outlet rules and accepts optional exact-match filters: `planning_date`, `depot`, `brand`, `district`, `temperature` (`AMBIENT`, `CHILLED`, `FROZEN`), `access`, `delivery_window` (`restricted` or `none`), and `prior_deferral` (`true` or `false`).

`POST /api/v1/dispatcher/plans` accepts `{ "planning_date": "YYYY-MM-DD" }` and requires an `Idempotency-Key`. It creates and persists a draft plan version from the configured planning scenario. The scenario must exist for that date, its orders must all be confirmed, and it must account for every confirmed order on that date; a mismatch returns `409 SCENARIO_ORDER_COVERAGE_MISMATCH`. Missing or invalid reference inputs return a structured `422` error. The response includes order decisions and deferral reasons, draft trips, ordered stops, ETA, capacity utilization, fuel, and diagnostics. Repeating the same key and date returns the original draft; reusing the key with another date returns `409 IDEMPOTENCY_KEY_REUSED`. `GET /api/v1/dispatcher/plans?planning_date=YYYY-MM-DD` lists saved versions, and `GET /api/v1/dispatcher/plans/{plan_version_id}` reloads a reviewable version from PostgreSQL.

To publish, call `POST /api/v1/dispatcher/plans/{plan_version_id}/publish` with an `Idempotency-Key` and optional `{ "reason": "..." }`. The server revalidates complete one-time order coverage, current order states, and trip delivery windows. On success it changes the plan to `PUBLISHED`, trips to `PLANNED`, served orders to `PLANNED`, and deferred orders to `DEFERRED`, and writes an audit event in the same transaction. Repeating the same key and command returns the saved result; reusing the key for another command returns `409 IDEMPOTENCY_KEY_REUSED`. Publishing an already published version returns `409 PLAN_NOT_DRAFT`; published versions have no edit endpoint.

## Loading and shortfall recovery

`GET /api/v1/loader/trips` lists published trips at the loader's depot and lazily creates the initial manifest V1 from the published stop sequence and order unit counts. Each order is one shipment line because the current domain has no product catalog. `GET /api/v1/loader/trips/{trip_id}/manifest` returns the current version and lines; `GET /api/v1/loader/trips/{trip_id}/manifests` returns the version history for comparison.

`POST /api/v1/loader/trips/{trip_id}/checks` accepts `{ "manifest_version": 1, "lines": [{ "order_id": "...", "status": "LOADED|MISSING|DAMAGED|SUBSTITUTE", "quantity": 1, "notes": "..." }] }`. Quantity is loaded units for `LOADED` and `SUBSTITUTE`, and affected units for `MISSING` and `DAMAGED`. Missing/damaged quantities create blocking shortfalls and put the trip on `DISPATCH_HOLD`; the event records actor/time and is visible to dispatchers at `GET /api/v1/dispatcher/shortfalls`. A replaced version is rejected with `409 STALE_MANIFEST`.

Dispatchers resolve an open item with `POST /api/v1/dispatcher/shortfalls/{shortfall_id}/resolve`, supplying a required reason and one of `PARTIAL_FULFILLMENT`, `SUBSTITUTE`, `RELOAD_FOUND`, `DEFER`, or `REALLOCATION`. Reallocation also requires `target_trip_id`; the server reruns the saved planning scenario with the affected order fixed to that vehicle/trip slot. The optimizer rechecks vehicle eligibility, capacity, fuel, route grouping, and delivery windows and returns a DRAFT replacement plan. The shortfall remains on hold until a dispatcher reviews and publishes that plan. Publishing supersedes the old plan, resolves the linked issue, and creates revised manifest versions for the replacement trips. Other unresolved blocking shortfalls prevent publication. For the current version, loader acknowledgement is `POST /api/v1/loader/manifests/{manifest_id}/acknowledge`. A trip becomes `READY` only after all current manifest quantities are accounted for, the version is acknowledged, and no blocking shortfall remains.

Dispatchers list active drivers with `GET /api/v1/dispatcher/drivers` and assign one with `POST /api/v1/dispatcher/trips/{trip_id}/assign` and `{ "driver_id": "uuid" }`. The trip must belong to the current published plan, the driver and vehicle must share a depot, and the driver cannot already have another active trip. Drivers list their assigned, ready or active trips with `GET /api/v1/driver/trips`. The response includes stop details and the current acknowledged manifest version and lines. Driver commands are `POST /api/v1/driver/trips/{trip_id}/depart`, `POST /api/v1/driver/stops/{stop_id}/arrive`, and `POST /api/v1/driver/stops/{stop_id}/complete`; each requires `Idempotency-Key` and accepts optional `X-Command-Id` for queued offline commands. Queued requests carry their original timezone-aware `occurred_at`; the API records it as the event/POD time and records server receipt time separately. Stop arrival and completion must follow route sequence. Completion body is `{ "outcome": "DELIVERED|FAILED", "receiver_name": "...", "notes": "...", "occurred_at": "..." }`; a receiver is required for delivery and a reason is required for failure. A repeated key and matching command returns the saved result without another POD record.

## Store delivery receipt and discrepancy (T09)

The Figma S04/S04B/S05 workflow operates on shipment orders, not a product catalog. Quantities are integer **units**. Original order units, dispatched units from the acknowledged manifest, and store-counted units remain distinct; a revised partial manifest does not overwrite the original request. Weight equivalents displayed by the UI are proportional estimates, not measured receiving weights. Driver completion snapshots the acknowledged manifest and dispatched quantity in its delivery event. Existing deliveries without that snapshot use their acknowledged manifest as a legacy fallback.

All store reads and commands require `STORE` and a nonempty account outlet; callers cannot choose an outlet. An absent/out-of-scope order is `404 ORDER_NOT_FOUND`. `GET /api/v1/store/deliveries` lists successful deliveries and their receipt/issue state as `{ "items": [], "next_cursor": null }`. `GET /api/v1/store/orders/{order_id}/delivery` returns order/outlet/vehicle/driver context, POD time/receiver/notes, manifest ID/version, original and dispatched units, receipt and issue. Only a server-recorded successful POD and `DELIVERED`/`RECEIVED` order are eligible; unsynced driver work and failed deliveries cannot be received. `GET /api/v1/store/orders/{order_id}/receipt` reads the saved receipt; absent receipts return `404 RECEIPT_NOT_FOUND`. `GET /api/v1/store/issues` lists the account outlet's cases, including resolved ones.

`POST /api/v1/store/orders/{order_id}/receipt` requires `Idempotency-Key` and `{ "receiver_name": "...", "received_quantity": 16, "notes": "..." }`. Receiver is nonblank (max 120), quantity is an integer from zero through dispatched units, and optional notes are max 1000. Confirming fewer units than dispatched requires an explanatory note. Receipt status is `CONFIRMED` when counted units equal original order units, otherwise `PARTIAL`. Both acknowledge the actual quantity and transition the order `DELIVERED → RECEIVED`. A store can acknowledge an approved partial delivery without opening a case.

Alternatively, `POST /api/v1/store/orders/{order_id}/issues` atomically records a `DISPUTED` receipt and an `OPEN` case, leaving the order `DELIVERED` pending review. Body includes the receipt fields plus `issue_type` (`MISSING_QUANTITY`, `DAMAGED`, `WRONG_ITEM`, `OTHER`), positive `affected_quantity`, and required nonblank `notes`. For missing quantity, affected units must equal original order units minus counted units (including an approved loading shortfall). Other affected quantities cannot exceed dispatched units. The response includes the saved receipt and issue; IDs are the tracking references. One receiving decision and at most one case can be created per order. Receipt facts are immutable. After a confirmation, further reports are rejected; this flow asks the manager to choose confirm or report during intake.

`GET /api/v1/dispatcher/delivery-issues` requires `DISPATCHER`, lists cases with quantity comparison, receipt/order/outlet context, and supports optional `status=OPEN|IN_REVIEW|RESOLVED`. A dispatcher with no depot scope is the central operations role; a depot-scoped dispatcher sees only its depot. `POST /api/v1/dispatcher/delivery-issues/{issue_id}/review` requires `Idempotency-Key` and `{ "status": "IN_REVIEW|RESOLVED", "reason": "..." }` (nonblank, max 1000). Transitions are `OPEN → IN_REVIEW → RESOLVED`; direct close and reopening are rejected. Resolution records the dispatcher, time and reason, finalizes the disputed receipt to `CONFIRMED`/`PARTIAL`, and changes the order to `RECEIVED` without changing counted quantities. Closing a case acknowledges its recorded outcome; it does not invent a replacement delivery or credit action.

Receipt, issue, order transition, audit and idempotency result commit atomically. PostgreSQL order row locks and the unique receipt/order constraint prevent concurrent duplicate intake. Same actor/key/command/body returns the original response, even after review; key reuse with another request is `409 IDEMPOTENCY_KEY_REUSED`. A new key after intake is `409 RECEIPT_ALREADY_RECORDED`. Invalid delivery/receipt/review transitions are `409`; invalid quantities or missing explanations are `422`. Audit actions are `RECEIPT_CONFIRMED`, `DELIVERY_ISSUE_REPORTED`, `DELIVERY_ISSUE_REVIEWED`, and `DELIVERY_ISSUE_RESOLVED`, including actor, UTC time, reason, order, manifest version and command correlation.

## Roles and current workflow states

The API must check authorization on the server for every protected route. Frontend route hiding is only a usability aid. A user cannot select or override their role in a request.

Initial domain state values from the product roadmap:

| Entity | Values |
| --- | --- |
| Order | `CONFIRMED`, `PLANNED`, `DEFERRED`, `DELIVERED`, `RECEIVED` |
| Plan | `DRAFT`, `PUBLISHED`, `REVISED` |
| Trip | `PLANNED`, `LOADING`, `DISPATCH_HOLD`, `READY`, `IN_TRANSIT`, `COMPLETED` |
| Delivery | `PENDING`, `DELIVERED`, `FAILED` |

Every command that changes workflow state validates its transition on the server and returns `409 CONFLICT` for a stale version or illegal transition. A module may add a state only with documented transition and migration implications.

## Idempotency and events

- Mutating commands that may be retried accept an `Idempotency-Key` header (1–128 characters). Replaying the same key and same command returns the original result; reusing a key for a different command returns `409 IDEMPOTENCY_KEY_REUSED`.
- Offline sync commands carry a stable `X-Command-Id` in addition to the idempotency key. The server records that ID with the idempotency result; retries preserve the key so duplicate sync cannot repeat the side effect.
- Event records use `{ "event_id": "uuid", "event_type": "...", "occurred_at": "...", "aggregate_type": "...", "aggregate_id": "...", "actor_id": "uuid|null", "payload": {} }`. Database state remains authoritative; event delivery is advisory.

## Known UI gaps (not yet API contracts)

The Figma screen map and implementation sequence are maintained in [`UI_IMPLEMENTATION_HANDOFF.md`](UI_IMPLEMENTATION_HANDOFF.md). The following capabilities are not defined by this contract and must not be represented as live API-backed behavior until a task adds and documents their contracts:

- Store pre-delivery ETA/plan details. T09 exposes successful delivery details and receipt/issue operations as documented above.
- Live route monitoring, future-capacity forecasts, telemetry, station controls, and intercom/messaging. Agree data source, freshness, permissions, failure behavior, and acceptance criteria before proposing endpoints.
- Photo/signature proof-of-delivery upload. Current driver proof supports receiver, outcome, notes, and event times; file storage and upload are not implemented.
- Editable dispatcher plans, store preferences/profile updates, or a separate gate-release command. Current APIs do not offer these actions; screens should reflect existing state transitions unless a new task defines and implements them.

This section is a gap inventory, not a promise or substitute contract. Add concrete schemas and behavior here when the responsible task is accepted; do not invent endpoint shapes in frontend code.

## API error example

```json
{
  "detail": {
    "code": "FORBIDDEN",
    "message": "This role cannot perform the requested operation."
  }
}
```
