"""tests for the sidecar's orphan-recovery watchdog.

the watchdog is a unix-only safety net for the pyinstaller --onefile
case where the desktop shell kills the bootloader and orphans the
python child. windows uses a job object on the rust side; direct
invocations (no LOOM_SHUTDOWN_TOKEN env) opt out so a backgrounded
sidecar doesn't self-terminate when its launching shell exits.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from loom import __main__ as sidecar_main


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOOM_SHUTDOWN_TOKEN", raising=False)


def test_skips_when_shutdown_token_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """direct ``loom-backend`` invocations don't get a watchdog."""
    monkeypatch.setattr(sys, "platform", "linux")
    thread_cls = MagicMock()
    with patch("loom.__main__.threading.Thread", thread_cls):
        sidecar_main._start_orphan_watchdog()
    thread_cls.assert_not_called()


def test_skips_on_windows_even_with_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """windows is covered by the job object the rust side attaches."""
    monkeypatch.setenv("LOOM_SHUTDOWN_TOKEN", "any")
    monkeypatch.setattr(sys, "platform", "win32")
    thread_cls = MagicMock()
    with patch("loom.__main__.threading.Thread", thread_cls):
        sidecar_main._start_orphan_watchdog()
    thread_cls.assert_not_called()


def test_skips_when_already_orphaned_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ppid==1 at startup means installing the watchdog would just
    exit immediately. respect that and don't install it."""
    monkeypatch.setenv("LOOM_SHUTDOWN_TOKEN", "any")
    monkeypatch.setattr(sys, "platform", "linux")
    thread_cls = MagicMock()
    with (
        patch("loom.__main__.os.getppid", return_value=1),
        patch("loom.__main__.threading.Thread", thread_cls),
    ):
        sidecar_main._start_orphan_watchdog()
    thread_cls.assert_not_called()


def test_starts_daemon_thread_when_env_set_on_unix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOOM_SHUTDOWN_TOKEN", "any")
    monkeypatch.setattr(sys, "platform", "linux")
    thread_instance = MagicMock()
    thread_cls = MagicMock(return_value=thread_instance)
    with (
        patch("loom.__main__.os.getppid", return_value=4321),
        patch("loom.__main__.threading.Thread", thread_cls),
    ):
        sidecar_main._start_orphan_watchdog()
    thread_cls.assert_called_once()
    kwargs = thread_cls.call_args.kwargs
    assert kwargs.get("daemon") is True
    assert kwargs.get("name") == "loom-orphan-watchdog"
    thread_instance.start.assert_called_once()
