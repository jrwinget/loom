import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_DEFAULT = "change-me-in-production"
_MIN_SECRET_LENGTH = 32
_CORS_ALLOWED_SCHEMES = {"http", "https", "tauri"}

DeploymentProfile = Literal["server", "lite"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOOM_")

    # server = dockerized postgres + minio + temporal (default).
    # lite  = sqlite + local filesystem + in-process worker; used
    # by the Tauri desktop shell (see docs/desktop-lite.md).
    deployment_profile: DeploymentProfile = "server"

    # root directory for lite-profile data (originals, derivatives,
    # sqlite db). resolved at startup; unused for server profile.
    data_dir: Path | None = None

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
    # vite dev server (both spellings — `tauri dev` loads the bundle
    # from 127.0.0.1:3000 while `pnpm dev` web uses localhost:3000) plus
    # the two production tauri webview origins: `tauri://localhost` on
    # macOS/linux, `http://tauri.localhost` on windows. the tauri entries
    # are inert under server-profile deploys because no public browser
    # ever sends those values as `Origin`; server operators who set
    # LOOM_CORS_ORIGINS replace the whole list anyway.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "tauri://localhost",
        "http://tauri.localhost",
    ]

    # signing secret for lite-profile loopback presigned urls. must be
    # persisted per-install (e.g. via tauri-plugin-store) so it stays
    # stable across launches but differs between installs. unused in
    # server profile, which uses minio's own signing path.
    storage_signing_secret: str | None = None
    # absolute origin the lite sidecar serves signed asset-stream urls
    # from. the desktop webview loads <video>/<img>/<object> src from
    # here, so it must be the sidecar's loopback bind (not a relative
    # path, which would resolve against tauri://localhost). unused on
    # server, where minio returns its own https presigned urls.
    lite_public_base_url: str = "http://127.0.0.1:8000"
    debug: bool = False
    log_level: str = "info"

    # optional Ed25519 private key (PEM) for detached bundle
    # signatures on court exports. leave unset to skip signing.
    bundle_signing_key: str | None = None

    # observability
    otel_enabled: bool = False
    otel_service_name: str = "loom-api"
    otel_exporter_endpoint: str = "http://localhost:4317"

    # bind address for the temporal worker's prometheus endpoint
    # (host:port). empty disables exposure entirely. exposing metrics
    # is server-profile only; the lite profile runs workflows in-process
    # and has no separate worker container to scrape.
    worker_metrics_addr: str = "0.0.0.0:9100"

    # per-launch shared secret for POST /admin/shutdown. the desktop
    # shell generates this in main.rs, passes it to the sidecar via
    # this env var (LOOM_SHUTDOWN_TOKEN), then sends it back with the
    # shutdown request on app close. unset on server-profile deploys
    # so the endpoint returns 404 there; an external attacker who
    # discovered the route would only see a missing-endpoint response.
    shutdown_token: str | None = None

    # connection pool settings
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 3600
    db_pool_pre_ping: bool = True
    db_pool_timeout: int = 30

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors_origins(cls, value: list[str]) -> list[str]:
        """reject wildcards and malformed origins.

        a malformed value silently disables browser protections,
        so we fail loud at startup rather than in the browser.
        """
        cleaned: list[str] = []
        for raw in value:
            origin = raw.strip()
            if not origin:
                raise ValueError("cors_origins entries must be non-empty")
            if origin == "*":
                raise ValueError(
                    "cors_origins may not be '*' — list each origin"
                )
            parsed = urlparse(origin)
            if parsed.scheme not in _CORS_ALLOWED_SCHEMES or not parsed.netloc:
                raise ValueError(
                    f"cors_origins entry {origin!r} must be an absolute "
                    "http(s) URL with no path (e.g. https://app.example.com)"
                )
            if parsed.path not in ("", "/"):
                raise ValueError(
                    f"cors_origins entry {origin!r} must not include a path"
                )
            # normalize: strip trailing slash so the middleware sees an
            # exact-match origin regardless of how the operator wrote it.
            cleaned.append(f"{parsed.scheme}://{parsed.netloc}")
        return cleaned

    @property
    def is_lite(self) -> bool:
        """true when running as a single-user desktop install."""
        return self.deployment_profile == "lite"

    def resolved_data_dir(self) -> Path:
        """absolute path of the lite-profile data directory.

        defaults to ``~/.loom/data`` when data_dir is unset; the
        directory is NOT created here so callers can decide when.
        """
        if self.data_dir is not None:
            return self.data_dir.expanduser().resolve()
        return (Path.home() / ".loom" / "data").resolve()

    def validate_deployment_profile(self) -> None:
        """sanity-check lite-only configuration at startup."""
        if not self.is_lite:
            return
        if not self.database_url.startswith(("sqlite+", "sqlite:")):
            raise ValueError(
                "lite profile requires a sqlite database_url "
                "(e.g. sqlite+aiosqlite:///~/.loom/data/loom.db)"
            )
        if not self.storage_signing_secret:
            raise ValueError(
                "lite profile requires LOOM_STORAGE_SIGNING_SECRET "
                "(a random per-install value) to sign loopback "
                "presigned urls. The Tauri shell generates this on "
                "first run via tauri-plugin-store."
            )

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

    def validate_production_settings(self) -> None:
        """fail-fast when default dev credentials are used
        in a server-profile, non-debug deployment.

        debug mode and the lite profile bypass these checks:
        debug is dev-only by definition, and lite uses local
        sqlite + filesystem so neither minio nor postgres
        credentials apply.
        """
        if self.debug or self.is_lite:
            return
        failures: list[str] = []
        if "loom:loom_dev@" in self.database_url:
            failures.append(
                "database_url uses default dev credentials "
                "('loom:loom_dev'). Set LOOM_DATABASE_URL to a "
                "production connection string."
            )
        if self.minio_access_key == "loom_minio":
            failures.append(
                "minio_access_key is the default dev value. "
                "Set LOOM_MINIO_ACCESS_KEY (and MINIO_ROOT_USER "
                "in compose) to a unique value."
            )
        if self.minio_secret_key == "loom_minio_dev":  # noqa: S105
            failures.append(
                "minio_secret_key is the default dev value. "
                "Set LOOM_MINIO_SECRET_KEY (and MINIO_ROOT_PASSWORD "
                "in compose) to a strong random value."
            )
        if failures:
            raise ValueError(
                "production credential validation failed:\n  - "
                + "\n  - ".join(failures)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
