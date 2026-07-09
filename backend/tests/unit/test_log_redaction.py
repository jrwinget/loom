"""lite-profile log redaction + rotating file tee (issue #285).

desktop log lines persist on disk and travel inside diagnostics
zips, so every string value must be scrubbed of emails and
home-directory paths at write time. server-profile logging must
stay byte-identical: stdout json, no file, no redaction.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from loom.config import DeploymentProfile, Settings
from loom.main import _configure_logging
from loom.services.log_redaction import redact_sensitive


def _redact(event: dict[str, object]) -> dict[str, object]:
    return dict(redact_sensitive(None, "info", event))


class TestRedactSensitive:
    def test_redacts_email_addresses(self) -> None:
        event = _redact({"event": "login failed for ada@example.org"})
        assert event["event"] == "login failed for <redacted-email>"

    def test_redacts_every_email_in_a_value(self) -> None:
        event = _redact({"users": "a@x.io, b.c+tag@y.co.uk"})
        assert event["users"] == "<redacted-email>, <redacted-email>"

    def test_redacts_current_user_home_path(self) -> None:
        home = str(Path.home())
        event = _redact({"path": f"{home}/evidence/clip.mp4"})
        assert event["path"] == "~/evidence/clip.mp4"

    def test_redacts_generic_linux_home(self) -> None:
        event = _redact({"path": "/home/ada/loom/data"})
        assert event["path"] == "~/loom/data"

    def test_redacts_generic_macos_home(self) -> None:
        event = _redact({"path": "/Users/ada/Library/Logs"})
        assert event["path"] == "~/Library/Logs"

    def test_redacts_generic_windows_home(self) -> None:
        event = _redact({"path": "C:\\Users\\ada\\AppData\\loom"})
        assert event["path"] == "~\\AppData\\loom"

    def test_redacts_nested_dicts_and_lists(self) -> None:
        event = _redact(
            {
                "detail": {
                    "who": "ada@example.org",
                    "files": ["/home/ada/a.mp4", "/home/ada/b.mp4"],
                }
            }
        )
        assert event["detail"] == {
            "who": "<redacted-email>",
            "files": ["~/a.mp4", "~/b.mp4"],
        }

    def test_leaves_non_string_values_alone(self) -> None:
        event = _redact({"count": 3, "ratio": 0.5, "ok": True, "missing": None})
        assert event == {
            "count": 3,
            "ratio": 0.5,
            "ok": True,
            "missing": None,
        }

    def test_leaves_clean_strings_alone(self) -> None:
        event = _redact({"event": "startup complete", "port": "8000"})
        assert event == {"event": "startup complete", "port": "8000"}


@pytest.fixture(autouse=True)
def _reset_structlog() -> Iterator[None]:
    """undo any structlog.configure done by a test in this module."""
    yield
    structlog.reset_defaults()


def _make_settings(tmp_path: Path, profile: DeploymentProfile) -> Settings:
    return Settings(
        secret_key="test-secret-key-that-is-long-enough-for-validation",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'loom.db'}",
        deployment_profile=profile,
        data_dir=tmp_path,
        storage_signing_secret="test-signing-secret",
    )


class TestLiteFileLogging:
    def test_lite_profile_writes_redacted_jsonl(self, tmp_path: Path) -> None:
        _configure_logging(_make_settings(tmp_path, "lite"))
        structlog.get_logger().info(
            "upload rejected",
            user="ada@example.org",
            path="/home/ada/evidence/clip.mp4",
        )

        log_file = tmp_path / "logs" / "backend.jsonl"
        assert log_file.exists()
        line = json.loads(log_file.read_text().splitlines()[-1])
        assert line["event"] == "upload rejected"
        assert line["user"] == "<redacted-email>"
        assert line["path"] == "~/evidence/clip.mp4"

    def test_server_profile_writes_no_file(self, tmp_path: Path) -> None:
        settings = Settings(
            secret_key=("test-secret-key-that-is-long-enough-for-validation"),
            data_dir=tmp_path,
        )
        _configure_logging(settings)
        structlog.get_logger().info("hello", user="ada@example.org")

        assert not (tmp_path / "logs").exists()
