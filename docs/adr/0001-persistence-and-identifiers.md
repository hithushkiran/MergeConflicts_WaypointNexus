# ADR 0001: Persistence and identifiers

PostgreSQL is the authoritative operational datastore and Alembic is the authoritative schema mechanism. Official outlet and vehicle IDs remain stable; operational records use UUIDs. Competition CSVs stay outside Git. Seed/import operations are deterministic and idempotent. FND-03 supplies persistence only; module owners implement workflow behavior later.
