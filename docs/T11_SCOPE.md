# T11 optional scope decision

No optional integration has been approved or implemented in this continuation.
The user was asked to agree the required feature set. The recommendation is to
defer the six areas below and prioritize core acceptance/reliability; no response
has been received, so that recommendation is not recorded as agreed scope.

| Candidate | Available authority | Missing support / current disposition |
| --- | --- | --- |
| Live tracking | Persisted trip/stop status on explicit API reads | No GPS feed or live route integration; pending scope/source agreement. Do not label snapshots as live tracking. |
| Forecasts | Saved plan metrics and configured planning references | No authoritative future-demand/capacity forecast integration or contract; pending agreement. |
| Telemetry | None | Device/provider feed, freshness and access rules absent; blocked by integration/source selection. |
| Intercom | None | Messaging/service integration, delivery guarantees and retention absent; blocked by integration/source selection. |
| Editable settings | `/auth/me` supports read-only account context | No preference/profile write contracts, persistence policy or agreed controls; pending requirements. |
| Photo/signature upload | Existing receiver, outcome, notes and event-time POD | No upload/storage service, retention limits or backend contract; blocked by storage/constraints decision. |

These are unfinished candidates, not completed deliverables. Existing shortfall
resolution, receipt review and offline recovery use the supported core APIs and
do not imply telemetry, messaging, forecasts or file storage.

Before implementing any accepted candidate, record and agree:

1. Authoritative source, ownership and freshness.
2. Roles, permissions and resource scope.
3. User-visible actions and valid transitions.
4. Loading, failure, retry and empty behavior.
5. API schema, errors, idempotency and integration boundary.
6. Persistence, retention and recovery behavior.
7. Measurable acceptance criteria.
8. Test strategy, including provider failure and permission denial.

Authentication/outbox hardening is independently authorized by the continuation
request. It uses existing login/session/driver contracts and is tracked under T12;
it does not require selection of an optional feature or an authentication redesign.
