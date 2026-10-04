# Waypoint Nexus

Waypoint Nexus is a four-role delivery orchestration platform for Store Managers, Dispatchers, Loaders, and Drivers. This repository contains the FND-01 foundation for the Tech-Triathlon 2026 Hackathon.

## Approved technology stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, TanStack Query
- Backend: Python 3.12, FastAPI, SQLAlchemy, and PostgreSQL
- Testing: Pytest and Vitest (Playwright later)
- Deployment: Docker Compose

The platform is a modular monolith. It does not use microservices, message brokers, Redis, Celery, Kafka, or separate optimization services.

## Repository structure

```text
frontend/       React application
backend/        FastAPI modular-monolith application
docs/           Project documentation and ADRs
tests/          Cross-cutting test workspace (reserved)
.github/        GitHub collaboration templates
```

## Prerequisites

- Node.js 20 or later with npm
- Python 3.12 or later
- Docker Desktop for the Compose environment

## Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

## Start the backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Run with Docker Compose

From the repository root, create your local configuration and start all services:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

## Database foundation (FND-03)

PostgreSQL is authoritative; Alembic owns schema evolution. Obtain the official, Git-ignored datasets separately at `local-data/outlets.csv` and `local-data/vehicles.csv`. They are mounted read-only for Compose seeding and are never baked into images.

```powershell
cd backend
alembic upgrade head
python -m app.seed
```

The idempotent seed imports 4 roles, Peliyagoda/Kandy depots, 120 outlets, 60 vehicles, and development users: `store.manager@waypoint.local`, `dispatcher@waypoint.local`, `loader@waypoint.local`, and `driver@waypoint.local`. No official calendar is currently available. Reset with `docker compose down -v` (warning: deletes local DB data), then `docker compose up --build`.

When `APP_ENV=development`, seeded users receive a password hash from `DEV_SEED_PASSWORD` only if they do not already have one. Compose supplies `waypoint-local-demo` as a local-only default; replace it in `.env` before sharing a development environment. Production seeding does not set this shared development password.

The versioned API contract is documented in [docs/api-contracts.md](docs/api-contracts.md). Authentication endpoints are `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, and `POST /api/v1/auth/logout`.

Store accounts can create and list outlet-scoped shipment requests from the web dashboard. The Colombo cutoff is configurable with `ORDER_CUTOFF_LOCAL_TIME` (default `16:00`); see the API contract for date eligibility and late-order behavior.

See [the foundation handoff](docs/FOUNDATION_HANDOFF.md) for stable development fixtures and module-owner notes.

Local services:

- Web: http://localhost:5173
- API: http://localhost:8000
- API health: http://localhost:8000/health
- API readiness: http://localhost:8000/ready
- PostgreSQL: `localhost:5432`

Stop the environment with:

```powershell
docker compose down
```

To reset the local database, run the following command. **Warning: it permanently deletes local PostgreSQL data.**

```powershell
docker compose down --volumes
```

## Run tests and checks

```powershell
cd frontend
npm run lint
npm run typecheck
npm run build
npm test
cd ..\backend
pytest
```

## Branch naming

Use `<jira-key>/<short-kebab-case-description>`, for example `FND-01/initial-monorepo`.

## Current implementation status

FND-02 adds a Docker Compose environment with the web, API, and PostgreSQL services. The API exposes `GET /health` for liveness and `GET /ready` for database readiness.

Database schema migrations and deterministic seed data arrive in FND-03. Authentication is available through the versioned endpoints documented in [docs/api-contracts.md](docs/api-contracts.md); order workflows and the route-planning solver are not implemented yet.
