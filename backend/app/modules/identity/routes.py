from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.persistence import AuthSession, Role, User
from app.modules.identity.schemas import LoginRequest, LoginResponse, UserProfile
from app.modules.identity.security import create_bearer_token, hash_bearer_token, verify_password


router = APIRouter(prefix="/api/v1/auth", tags=["identity"])
bearer_scheme = HTTPBearer(auto_error=False)
ROLE_MAP = {"STORE_MANAGER": "STORE"}


@dataclass(frozen=True)
class Principal:
    user: User
    role: str
    session: AuthSession


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None,
    )


def profile_for(user: User, role: Role) -> UserProfile:
    return UserProfile(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=ROLE_MAP.get(role.code, role.code),
        outlet_id=user.outlet_id,
        depot_code=user.depot_code,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)) -> LoginResponse:
    result = db.execute(
        select(User, Role)
        .join(Role, Role.id == User.role_id)
        .where(func.lower(User.email) == payload.email)
    ).first()
    if result is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "Email or password is incorrect.")

    user, role = result
    if not user.active or not verify_password(payload.password, user.password_hash):
        raise api_error(status.HTTP_401_UNAUTHORIZED, "INVALID_CREDENTIALS", "Email or password is incorrect.")

    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=get_settings().auth_session_ttl_hours)
    token = create_bearer_token()
    db.add(AuthSession(user_id=user.id, token_hash=hash_bearer_token(token), expires_at=expires_at))
    db.commit()
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=profile_for(user, role),
    )


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise api_error(status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_REQUIRED", "A bearer token is required.")

    now = datetime.now(UTC)
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == hash_bearer_token(credentials.credentials),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    if session is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", "The bearer token is invalid or expired.")

    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", "The bearer token is invalid or expired.")
    role = db.get(Role, user.role_id)
    if role is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", "The bearer token is invalid or expired.")
    return Principal(user=user, role=ROLE_MAP.get(role.code, role.code), session=session)


def require_roles(*allowed_roles: str):
    allowed = frozenset(allowed_roles)

    def guard(principal: Principal = Depends(get_current_principal)) -> Principal:
        if principal.role not in allowed:
            raise api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "This role cannot perform the requested operation.")
        return principal

    return guard


@router.get("/me", response_model=UserProfile)
def current_user(principal: Principal = Depends(get_current_principal)) -> UserProfile:
    return UserProfile(
        id=str(principal.user.id),
        email=principal.user.email,
        display_name=principal.user.display_name,
        role=principal.role,
        outlet_id=principal.user.outlet_id,
        depot_code=principal.user.depot_code,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db_session)) -> Response:
    principal.session.revoked_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
