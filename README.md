# Waypoint Nexus

Waypoint Nexus is a four-role delivery orchestration platform for Store Managers, Dispatchers, Loaders, and Drivers. This repository contains the FND-01 foundation for the Tech-Triathlon 2026 Hackathon.

## Approved technology stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, TanStack Query
- Backend: Python and FastAPI (SQLAlchemy, Alembic, and PostgreSQL are introduced later)
- Testing: Pytest and Vitest (Playwright later)
- Deployment: Docker Compose (implemented in FND-02)

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
- Python 3.11 or later

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

FND-01 supplies the initial repository structure, a frontend development home screen, and a FastAPI health endpoint at `GET /health`.

Docker Compose, database integration, migrations, authentication, and the route-planning solver are not implemented yet.
