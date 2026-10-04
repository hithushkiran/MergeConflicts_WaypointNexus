# Waypoint Nexus — Team Quick Start

This guide gets a teammate from a fresh checkout to the running app and its checks. Docker Compose is the recommended setup because it starts the web app, API, database, migrations, and development seed together.

## Requirements

- Git
- Docker Desktop (or Docker Engine with the Compose plugin)
- Node.js 20+ and npm (for frontend development outside Docker)
- Python 3.12+ (for backend development outside Docker)

## Start the whole app

From the repository root:

```sh
cp .env.example .env
docker compose up --build -d
```

PowerShell users can create the environment file with:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Compose runs database migrations and the idempotent development seed when the API starts. Check service status and logs if startup takes a moment:

```sh
docker compose ps
docker compose logs -f api
```

Open the web app at <http://localhost:5173>. The API is at <http://localhost:8000>; its liveness and database readiness checks are <http://localhost:8000/health> and <http://localhost:8000/ready>.

## Sign in

On a fresh local database, use one of the seeded accounts with the development password configured in `.env` (`waypoint-local-demo` by default):

| Role | Email |
| --- | --- |
| Store Manager | `store.manager@waypoint.local` |
| Dispatcher | `dispatcher@waypoint.local` |
| Loader | `loader@waypoint.local` |
| Driver | `driver@waypoint.local` |

The password is set when a development user is first seeded. Changing `DEV_SEED_PASSWORD` later does not replace an existing password hash. Keep this shared development credential local; do not use it for a deployed environment.

## Run checks

Frontend checks:

```sh
cd frontend
npm install
npm test
npm run lint
npm run typecheck
npm run build
```

Backend checks (Linux/macOS):

```sh
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
```

Backend checks (PowerShell):

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

## Stop the app and protect local data

Stop containers while keeping the database volume:

```sh
docker compose down
```

Avoid `docker compose down -v` unless you intentionally want to permanently delete the local database and its seeded or created data. Demo CSVs in `backend/demo-data/` are synthetic. Official competition data belongs in the ignored `local-data/` directory and should not be committed.

## Find your way around

- `frontend/` — React and TypeScript web app
- `backend/app/` — FastAPI application and business modules
- `backend/tests/` — backend tests
- `backend/demo-data/` — synthetic local fixtures
- `docs/api-contracts.md` — versioned API contracts
- `docs/todo/README.md` and `docs/todo/roadmap.md` — work queue and roadmap
- `docs/FOUNDATION_HANDOFF.md` — foundation and module handoff notes

