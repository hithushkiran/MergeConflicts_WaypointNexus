from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_database_engine() -> Engine:
    """Create the shared SQLAlchemy engine without defining application tables."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_database_engine(), autoflush=False, autocommit=False)


def get_db_session():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def database_is_available() -> bool:
    """Perform the minimum connectivity check required by the readiness endpoint."""
    try:
        with get_database_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
