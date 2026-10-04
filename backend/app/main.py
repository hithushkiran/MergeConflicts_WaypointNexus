from fastapi import FastAPI, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.infrastructure.database import database_is_available
from app.modules.identity.routes import router as identity_router
from app.modules.dispatcher.routes import router as dispatcher_router
from app.modules.orders.routes import router as orders_router
from app.modules.loading.routes import dispatcher as shortfall_router, loader as loading_router
from app.modules.delivery.routes import router as delivery_router

settings = get_settings()

app = FastAPI(title="Waypoint Nexus API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(identity_router)
app.include_router(orders_router)
app.include_router(dispatcher_router)
app.include_router(loading_router)
app.include_router(shortfall_router)
app.include_router(delivery_router)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_, error: StarletteHTTPException) -> JSONResponse:
    if isinstance(error.detail, dict) and "code" in error.detail:
        detail = error.detail
    else:
        code = "NOT_FOUND" if error.status_code == status.HTTP_404_NOT_FOUND else "HTTP_ERROR"
        detail = {"code": code, "message": str(error.detail)}
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": detail},
        headers=error.headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_, error: RequestValidationError) -> JSONResponse:
    fields = [
        {"field": ".".join(str(part) for part in issue["loc"] if part != "body"), "message": issue["msg"]}
        for issue in error.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": {
                "code": "VALIDATION_ERROR",
                "message": "The request contains invalid fields.",
                "fields": fields,
            }
        },
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
