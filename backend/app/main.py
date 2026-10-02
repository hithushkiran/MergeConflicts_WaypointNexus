from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.infrastructure.database import database_is_available

settings = get_settings()

app = FastAPI(title="Waypoint Nexus API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the application's liveness status."""
    return {"status": "ok"}


@app.get("/ready")
def readiness_check(response: Response) -> dict[str, str]:
    """Report whether the API can establish a database connection."""
    if database_is_available():
        return {"status": "ready", "database": "ok"}

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "not_ready", "database": "unavailable"}
