from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT = "change-me-in-production"
_MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOOM_")

    database_url: str = "postgresql+asyncpg://loom:loom_dev@localhost:5432/loom"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "loom_minio"
    minio_secret_key: str = "loom_minio_dev"  # noqa: S105
    minio_secure: bool = False
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "loom"
    secret_key: str = _INSECURE_DEFAULT
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    debug: bool = False
    log_level: str = "info"

    # observability
    otel_enabled: bool = False
    otel_service_name: str = "loom-api"
    otel_exporter_endpoint: str = "http://localhost:4317"

    # connection pool settings
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 3600
    db_pool_pre_ping: bool = True
    db_pool_timeout: int = 30

    def validate_secret_key(self) -> None:
        """reject insecure or short secret keys.

        called at startup rather than at construction so that
        tests and module-level imports are not blocked.
        """
        if self.secret_key == _INSECURE_DEFAULT:
            raise ValueError(
                "secret_key is the insecure default. "
                "Set LOOM_SECRET_KEY to a random string of "
                f"at least {_MIN_SECRET_LENGTH} characters."
            )
        if len(self.secret_key) < _MIN_SECRET_LENGTH:
            raise ValueError(
                f"secret_key must be at least "
                f"{_MIN_SECRET_LENGTH} characters, "
                f"got {len(self.secret_key)}."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
