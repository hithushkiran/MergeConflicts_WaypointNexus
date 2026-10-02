from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(case_sensitive=False)

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://waypoint:waypoint_local_password@db:5432/waypoint_nexus"
    tz: str = "Asia/Colombo"
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
