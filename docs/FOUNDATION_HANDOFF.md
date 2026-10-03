# Foundation handoff

Run `docker compose up --build`; API startup runs Alembic then `python -m app.seed`. Reset locally with `docker compose down -v` (deletes local DB data). Models live in `backend/app/infrastructure/persistence.py`; FastAPI dependencies use `get_db_session` from `infrastructure/database.py`.

Official competition data is read only from Git-ignored `local-data/` and must never be committed. Stable users: `store.manager@waypoint.local` (OUT001), `dispatcher@waypoint.local`, `loader@waypoint.local` (Peliyagoda), `driver@waypoint.local` (Peliyagoda). Demo date: `2026-03-16`; planning-run lookup: snapshot hash `demo-2026-03-16`. Orders: `DEMO-ORD-FRESH-AMBIENT`, `DEMO-ORD-FRESH-CHILLED` (OUT001), `DEMO-ORD-STYLE` (OUT015), `DEMO-ORD-TECH` (OUT021). Useful vehicles include official IDs such as `VEH001`.

Tables: roles, users, depots, outlets, vehicles, orders, planning_runs, plan_versions, trips, trip_stops, deferrals, manifest_checks, shortfalls, delivery_events, proofs_of_delivery, receipts, delivery_issues, audit_events, idempotency_records. Sanu must align the development date with official calendar data before final planning validation because no `calendar.csv` is supplied.

Entity ownership: Gowrishan—Order/Outlet; Sanu—Order, Outlet, Vehicle, PlanningRun, PlanVersion, Trip, TripStop; Sugee—Trip, TripStop, ManifestCheck, Shortfall; Falil—Trip, TripStop, DeliveryEvent, ProofOfDelivery, IdempotencyRecord; Tharu—PlanningRun, PlanVersion, Trip, Deferral, AuditEvent; Hithush—User, Role, infrastructure, migrations, audit, idempotency. No API contracts are defined here.
