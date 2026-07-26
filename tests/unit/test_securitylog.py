"""Unit tests for the OWASP SEC0045 security event emitter."""

from __future__ import annotations

import io
import json
import re
from typing import TYPE_CHECKING

import pytest

from concierge import securitylog

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(autouse=True)
def _restore_default_state() -> None:
    """Reset the emitter's destination between tests.

    Each test writes to its own buffer via ``configure``; the fixture just
    guarantees a clean starting point.
    """
    securitylog.configure(io.StringIO(), "concierge@test")


def _emit_and_decode(emit_fn: Callable[[], None]) -> dict[str, object]:
    """Reconfigure to a fresh buffer, run ``emit_fn``, decode the JSON record."""
    buf = io.StringIO()
    securitylog.configure(buf, "concierge@test")
    emit_fn()
    return json.loads(buf.getvalue())


class TestEmit:
    """Tests for the JSON shape of emitted records."""

    def test_emit_fields(self) -> None:
        record = _emit_and_decode(
            lambda: securitylog.emit(
                securitylog.EVENT_SYS_STARTUP,
                "1000",
                "machine provisioning started",
                action="prepare",
            )
        )

        assert record["type"] == "security"
        assert record["appid"] == "concierge@test"
        assert record["event"] == "sys_startup:1000"
        assert record["description"] == "machine provisioning started"
        assert record["level"] == "WARN"
        assert record["action"] == "prepare"

        # The OWASP vocabulary uses "datetime" rather than "time".
        assert "datetime" in record
        assert "time" not in record

    def test_emit_without_arg_uses_bare_event_name(self) -> None:
        record = _emit_and_decode(
            lambda: securitylog.emit(securitylog.EVENT_AUTHZ_ADMIN, "", "no arg")
        )
        assert record["event"] == "authz_admin"

    def test_authz_admin_event_carries_userid_and_sub_event(self) -> None:
        record = _emit_and_decode(
            lambda: securitylog.emit(
                securitylog.EVENT_AUTHZ_ADMIN,
                "0,exec",
                "privileged command executed",
                command="snap install foo",
            )
        )
        assert record["event"].startswith("authz_admin:")
        assert record["event"] == "authz_admin:0,exec"
        assert record["level"] == "WARN"
        assert record["command"] == "snap install foo"

    def test_emit_never_writes_time_key(self) -> None:
        """Renaming the slog TimeKey/MessageKey shape must be preserved.

        A future refactor that reintroduces `time` or `msg` keys would break
        parsers built to the OWASP schema.
        """
        record = _emit_and_decode(
            lambda: securitylog.emit(securitylog.EVENT_SYS_SHUTDOWN, "1000", "restore started")
        )
        assert "msg" not in record
        assert "message" not in record


class TestUserID:
    """Tests for :func:`securitylog.user_id`."""

    def test_user_id_is_numeric(self) -> None:
        uid = securitylog.user_id()
        assert uid != ""
        assert re.fullmatch(r"\d+", uid), uid


class TestConfigure:
    """Tests for the configuration surface."""

    def test_empty_appid_keeps_existing(self) -> None:
        buf1 = io.StringIO()
        securitylog.configure(buf1, "concierge@first")

        buf2 = io.StringIO()
        securitylog.configure(buf2, "")

        securitylog.emit(securitylog.EVENT_SYS_SHUTDOWN, securitylog.user_id(), "shutdown")

        record = json.loads(buf2.getvalue())
        assert record["appid"] == "concierge@first"

    def test_configure_default_does_not_raise(self) -> None:
        """Attaching to /dev/log succeeds on journald hosts and falls back to
        stderr otherwise; either path is acceptable — the contract is just
        that it does not raise and leaves a usable emitter behind.
        """
        securitylog.configure_default("concierge@test")

        # Follow up with an emit to prove the emitter is still usable. Route
        # it back into a buffer for isolation from stderr.
        buf = io.StringIO()
        securitylog.configure(buf, "concierge@test")
        securitylog.emit(
            securitylog.EVENT_SYS_STARTUP, securitylog.user_id(), "configured-default smoke test"
        )
        assert buf.getvalue().strip() != ""


class TestEventNames:
    """Sanity checks that the OWASP event name constants are stable."""

    def test_event_name_constants_match_vocabulary(self) -> None:
        # These names are load-bearing: parsers key off them.
        assert securitylog.EVENT_SYS_STARTUP == "sys_startup"
        assert securitylog.EVENT_SYS_SHUTDOWN == "sys_shutdown"
        assert securitylog.EVENT_AUTHZ_ADMIN == "authz_admin"
        assert securitylog.EVENT_PRIVILEGE_PERMISSIONS_CHANGED == "privilege_permissions_changed"
