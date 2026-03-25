from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOOM_")

    database_url: str = "postgresql+asyncpg://loom:loom_dev@localhost:5432/loom"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "loom_minio"
    minio_secret_key: str = "loom_minio_dev"  # noqa: S105
    minio_secure: bool = False
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "loom"
    secret_key: str = "change-me-in-production"  # noqa: S105
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    debug: bool = False
    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()
