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

The database role code `STORE_MANAGER` maps to API role `STORE`; the other API roles are `DISPATCHER`, `LOADER`, and `DRIVER`. Store accounts are scoped to their `outlet_id`, and depot users are scoped to their `depot_code`. Missing scope is not treated as unrestricted access. Driver-to-trip assignment enforcement will be applied when trip assignment is part of the domain schema.

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

`GET /api/v1/loader/trips` lists published trips at the loader's depot and lazily creates the initial manifest V1 from the published stop sequence and order unit counts. Each order is one shipment line because the current domain has no product catalog. The trip response reports the driver as unassigned until T07 adds trip assignment. `GET /api/v1/loader/trips/{trip_id}/manifest` returns the current version and lines; `GET /api/v1/loader/trips/{trip_id}/manifests` returns the version history for comparison.

`POST /api/v1/loader/trips/{trip_id}/checks` accepts `{ "manifest_version": 1, "lines": [{ "order_id": "...", "status": "LOADED|MISSING|DAMAGED|SUBSTITUTE", "quantity": 1, "notes": "..." }] }`. Quantity is loaded units for `LOADED` and `SUBSTITUTE`, and affected units for `MISSING` and `DAMAGED`. Missing/damaged quantities create blocking shortfalls and put the trip on `DISPATCH_HOLD`; the event records actor/time and is visible to dispatchers at `GET /api/v1/dispatcher/shortfalls`. A replaced version is rejected with `409 STALE_MANIFEST`.

Dispatchers resolve an open item with `POST /api/v1/dispatcher/shortfalls/{shortfall_id}/resolve`, supplying a required reason and one of `PARTIAL_FULFILLMENT`, `SUBSTITUTE`, `RELOAD_FOUND`, `DEFER`, or `REALLOCATION`. Reallocation also requires `target_trip_id`; the server reruns the saved planning scenario with the affected order fixed to that vehicle/trip slot. The optimizer rechecks vehicle eligibility, capacity, fuel, route grouping, and delivery windows and returns a DRAFT replacement plan. The shortfall remains on hold until a dispatcher reviews and publishes that plan. Publishing supersedes the old plan, resolves the linked issue, and creates revised manifest versions for the replacement trips. Other unresolved blocking shortfalls prevent publication. For the current version, loader acknowledgement is `POST /api/v1/loader/manifests/{manifest_id}/acknowledge`. A trip becomes `READY` only after all current manifest quantities are accounted for, the version is acknowledged, and no blocking shortfall remains. `POST /api/v1/driver/trips/{trip_id}/depart` returns `409 DEPARTURE_BLOCKED` for a held trip; successful driver assignment/departure remains T07 work.

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
- Offline sync commands carry a stable `command_id` in addition to the idempotency key. The server records one result per command and duplicate sync must not repeat the side effect.
- Event records use `{ "event_id": "uuid", "event_type": "...", "occurred_at": "...", "aggregate_type": "...", "aggregate_id": "...", "actor_id": "uuid|null", "payload": {} }`. Database state remains authoritative; event delivery is advisory.

## API error example

```json
{
  "detail": {
    "code": "FORBIDDEN",
    "message": "This role cannot perform the requested operation."
  }
}
```
