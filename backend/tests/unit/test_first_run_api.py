"""tests for the /first-run onboarding endpoints."""

import re
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import Select

from loom.config import Settings, get_settings
from loom.dependencies import get_db_session
from loom.models.audit import AuditLogEntry
from loom.models.user import User
from loom.security.auth import decode_token, verify_password
from loom.security.rate_limit import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """clear the in-memory rate limiter between tests.

    slowapi's default MemoryStorage is process-global, so tests
    that hit the same endpoint accumulate hits across the session.
    """
    limiter.reset()


def _make_existing_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = UUID("01912345-6789-7abc-8def-0123456789ab")
    user.email = "existing@example.com"
    user.display_name = "Existing"
    user.role = "admin"
    user.is_active = True
    user.password_hash = "hash"
    user.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    user.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return user


class _StatusSession:
    """mock async session that simulates the users-table contract.

    the real /complete handler issues one INSERT...SELECT...WHERE
    NOT EXISTS; the stub tracks whether a user has been inserted
    and reports rowcount accordingly so the TOCTOU fix can be
    exercised without a live database.
    """

    def __init__(self, *, user_count: int) -> None:
        self._user_count = user_count
        self.added: list[object] = []

    def _bump_user_count(self) -> None:
        self._user_count += 1

    async def execute(self, stmt: Select[Any]) -> MagicMock:
        sql = str(stmt).lower()
        result = MagicMock()
        if sql.startswith("insert into users"):
            # atomic insert: 0 rows if a user already exists, 1 otherwise
            inserted = 0 if self._user_count > 0 else 1
            result.rowcount = inserted
            if inserted:
                self._bump_user_count()
            return result
        # count(*) and other reads
        result.scalar_one.return_value = self._user_count
        return result

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None


@pytest_asyncio.fixture
def settings() -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        access_token_expire_minutes=15,
        refresh_token_expire_days=7,
        database_url="sqlite+aiosqlite:///",
    )


def _build_app(session: _StatusSession, cfg: Settings) -> Any:
    """build a FastAPI app wired to a mock db session."""
    get_settings.cache_clear()

    with patch("loom.config.get_settings", return_value=cfg):
        from loom.main import create_app

        application = create_app()

    async def override_db() -> Any:
        yield session

    application.dependency_overrides[get_db_session] = override_db
    # skip audit writes + revocation checks
    application.state.db_session_factory = None
    return application


async def test_status_returns_first_run_required_when_no_users(
    settings: Settings,
) -> None:
    """GET /first-run/status reports True when no users exist."""
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    with patch(
        "loom.api.v1.first_run.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/first-run/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["first_run_required"] is True
    assert body["deployment_profile"] == "server"
    # server profile: data_dir should be null
    assert body["data_dir"] is None


async def test_status_returns_false_when_users_exist(
    settings: Settings,
) -> None:
    """GET /first-run/status reports False when a user exists."""
    session = _StatusSession(user_count=1)
    app = _build_app(session, settings)

    with patch(
        "loom.api.v1.first_run.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/first-run/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["first_run_required"] is False


async def test_status_includes_data_dir_on_lite_profile(
    settings: Settings,
) -> None:
    """lite profile: data_dir is populated from settings."""
    lite_settings = Settings(
        secret_key=settings.secret_key,
        database_url="sqlite+aiosqlite:///:memory:",
        deployment_profile="lite",
        storage_signing_secret="test-signing-secret",
    )
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    with patch(
        "loom.api.v1.first_run.get_settings",
        return_value=lite_settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.get("/api/v1/first-run/status")

    body = resp.json()
    assert body["deployment_profile"] == "lite"
    assert isinstance(body["data_dir"], str)
    assert body["data_dir"].endswith("data") or "/.loom/" in body["data_dir"]


async def test_complete_creates_admin_and_returns_tokens(
    settings: Settings,
) -> None:
    """POST /first-run/complete succeeds when no users exist."""
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "Admin Example",
    }

    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/first-run/complete",
                json=payload,
            )

    assert resp.status_code == 201
    body = resp.json()
    assert "user_id" in body
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    # an explicit audit entry ties the action to the new user_id
    audit_entries = [
        obj for obj in session.added if isinstance(obj, AuditLogEntry)
    ]
    assert len(audit_entries) == 1
    entry = audit_entries[0]
    assert entry.action == "user.bootstrap.create"
    assert entry.resource_type == "users"
    assert str(entry.resource_id) == body["user_id"]
    assert entry.actor_id is None

    # access token encodes the user's role
    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        decoded = decode_token(body["access_token"])
    assert decoded["role"] == "admin"
    assert decoded["sub"] == body["user_id"]


class _CapturingSession(_StatusSession):
    """stub session that captures compiled INSERT params."""

    def __init__(self, *, user_count: int) -> None:
        super().__init__(user_count=user_count)
        self.insert_params: dict[str, Any] = {}

    async def execute(self, stmt: Any) -> MagicMock:
        sql = str(stmt).lower()
        if sql.startswith("insert into users"):
            self.insert_params = dict(stmt.compile().params)
        return await super().execute(stmt)


async def test_complete_hashes_password_before_insert(
    settings: Settings,
) -> None:
    """the handler must hash the password before handing it off.

    regression guard: an earlier implementation inserted via the
    ORM so a refactor could plausibly skip the hash step.
    """
    session = _CapturingSession(user_count=0)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "Admin Example",
    }

    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/first-run/complete",
                json=payload,
            )

    assert resp.status_code == 201
    values = list(session.insert_params.values())
    # plaintext must never reach the insert
    assert payload["admin_password"] not in values
    # exactly one argon2 hash was bound, and it verifies
    hashes = [
        v for v in values if isinstance(v, str) and v.startswith("$argon2")
    ]
    assert len(hashes) == 1
    assert verify_password(payload["admin_password"], hashes[0])


async def test_complete_returns_409_when_user_already_exists(
    settings: Settings,
) -> None:
    """POST /first-run/complete returns 409 if any user exists."""
    session = _StatusSession(user_count=1)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "Admin Example",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/first-run/complete",
            json=payload,
        )

    assert resp.status_code == 409
    # no audit entry written when the insert is rejected
    assert [o for o in session.added if isinstance(o, AuditLogEntry)] == []


async def test_complete_second_call_loses_race(
    settings: Settings,
) -> None:
    """second /complete against the same state returns 409.

    simulates the outcome of the TOCTOU fix: the first INSERT...
    WHERE NOT EXISTS flips users_count to 1; the second call's
    subquery sees the existing row and inserts 0 rows.
    """
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    payload_a = {
        "admin_email": "a@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "A",
    }
    payload_b = {
        "admin_email": "b@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "B",
    }

    with patch(
        "loom.security.auth.get_settings",
        return_value=settings,
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            first = await ac.post(
                "/api/v1/first-run/complete",
                json=payload_a,
            )
            second = await ac.post(
                "/api/v1/first-run/complete",
                json=payload_b,
            )

    assert first.status_code == 201
    assert second.status_code == 409


async def test_complete_rejects_short_password(
    settings: Settings,
) -> None:
    """POST /first-run/complete rejects passwords under 12 chars."""
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "short",
        "admin_full_name": "Admin Example",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        resp = await ac.post(
            "/api/v1/first-run/complete",
            json=payload,
        )

    assert resp.status_code == 422
    assert session.added == []


async def test_complete_returns_eight_recovery_codes(
    settings: Settings,
) -> None:
    """POST /first-run/complete returns 8 plaintext recovery codes."""
    session = _StatusSession(user_count=0)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "Admin Example",
    }

    with patch("loom.security.auth.get_settings", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/first-run/complete",
                json=payload,
            )

    assert resp.status_code == 201
    body = resp.json()
    codes = body["password_recovery_codes"]
    assert isinstance(codes, list)
    assert len(codes) == 8
    # display format: four hyphen-separated groups of 5 hex chars.
    group = r"[0-9a-f]{5}"
    code_pattern = re.compile(rf"^{group}-{group}-{group}-{group}$")
    for code in codes:
        assert code_pattern.match(code), f"unexpected code shape: {code!r}"
    # uniqueness: no duplicates within a single batch
    assert len(set(codes)) == 8


async def test_complete_persists_hashed_codes_not_plaintext(
    settings: Settings,
) -> None:
    """the INSERT must bind sha256 hashes, never the plaintext codes."""
    session = _CapturingSession(user_count=0)
    app = _build_app(session, settings)

    payload = {
        "admin_email": "admin@example.com",
        "admin_password": "supersecret-password-12",
        "admin_full_name": "Admin Example",
    }

    with patch("loom.security.auth.get_settings", return_value=settings):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            resp = await ac.post(
                "/api/v1/first-run/complete",
                json=payload,
            )

    assert resp.status_code == 201
    body = resp.json()
    plaintext_codes: list[str] = body["password_recovery_codes"]

    # the column is bound via a literal in an INSERT...SELECT, so the
    # param key is auto-named (param_N). scan the bound values for the
    # one matching our expected shape: comma-joined 64-char hex digests.
    sha_csv = re.compile(r"^[0-9a-f]{64}(,[0-9a-f]{64})*$")
    candidates = [
        v
        for v in session.insert_params.values()
        if isinstance(v, str) and sha_csv.fullmatch(v)
    ]
    assert len(candidates) == 1, (
        f"expected exactly one sha256-csv bound value, got {candidates!r}"
    )
    bound = candidates[0]

    # plaintext (with or without hyphens) must not appear in the stored value
    for code in plaintext_codes:
        assert code not in bound
        assert code.replace("-", "") not in bound

    # exactly 8 comma-separated 64-char sha256 hex digests
    stored = bound.split(",")
    assert len(stored) == 8
