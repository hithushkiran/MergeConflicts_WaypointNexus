from fastapi import FastAPI

app = FastAPI(title="Waypoint Nexus API")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the application's liveness status."""
    return {"status": "ok"}
