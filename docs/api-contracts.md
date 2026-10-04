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
