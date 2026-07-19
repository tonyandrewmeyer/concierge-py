"""OWASP Application Logging Vocabulary security event emitter.

Concierge runs as root in order to provision charm development and testing
machines: it executes privileged commands, installs snaps and debs, writes
cloud credentials, and changes filesystem ownership. Canonical's SEC0045
(Security Event Logging) standard requires that these actions be recorded
using the OWASP Application Logging Vocabulary.

Events are emitted as structured JSON so that they form a machine-parseable
audit trail that is independent of Concierge's human-readable logging
verbosity (``--verbose``/``--trace``). Each record carries the fields
recommended by the vocabulary: a ``datetime`` timestamp, a ``level``, a
constant ``type`` of ``"security"``, an ``appid`` identifying the process,
the OWASP ``event`` name, and a human-readable ``description``. Per the
vocabulary, the ``event`` field embeds event-specific parameters (such as
the userid) as ``name:arg``.

Structured JSON (rather than OTLP via an owasp-logger library) is used
because Concierge is a short-lived CLI with no existing telemetry pipeline;
records are delivered to the system journal via syslog(3) so the audit
stream stays separate from Concierge's human-readable stderr output.
``journalctl -t concierge`` surfaces the events, and each record's JSON
body can be parsed back out (e.g. ``journalctl -t concierge -o cat | jq .``).
"""

from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
import os
import sys
import threading
from datetime import UTC, datetime
from typing import IO, Any

# Event names from the OWASP Application Logging Vocabulary that Concierge
# emits. Only the subset relevant to Concierge's behaviour is defined here.
# The cheat sheet specifies WARN as the level for each of these events.

# EVENT_SYS_STARTUP records that a system (here, machine provisioning) has
# been started. Emitted when Concierge begins to prepare a machine.
EVENT_SYS_STARTUP = "sys_startup"

# EVENT_SYS_SHUTDOWN records that a system has been shut down. Emitted when
# Concierge restores (decommissions) a previously prepared machine.
EVENT_SYS_SHUTDOWN = "sys_shutdown"

# EVENT_AUTHZ_ADMIN records activity performed with administrative privileges.
# Concierge runs as root, so every privileged command it executes, and the
# writing of cloud credentials, is administrative activity.
EVENT_AUTHZ_ADMIN = "authz_admin"

# EVENT_PRIVILEGE_PERMISSIONS_CHANGED records a change to the permissions or
# ownership of a resource. Emitted when Concierge recursively changes the
# ownership of files and directories it creates.
EVENT_PRIVILEGE_PERMISSIONS_CHANGED = "privilege_permissions_changed"

# The constant value of the "type" field on every security event, identifying
# the record as a security event for downstream tooling.
_SECURITY_TYPE = "security"


class _State:
    """Module-level configuration held on a single mutable object.

    Storing state on an instance rather than as bare module globals lets us
    reassign the destination and appid without needing ``global`` statements
    at every call site.
    """

    lock: threading.Lock = threading.Lock()
    stream: IO[str] | None = None
    handler: logging.Handler | None = None
    appid: str = "concierge"


def _reset_target() -> None:
    """Clear whichever destination is currently configured."""
    _State.stream = None
    if _State.handler is not None:
        with contextlib.suppress(Exception):
            _State.handler.close()
        _State.handler = None


def configure(stream: IO[str], appid: str = "") -> None:
    """Configure the emitter to write records to ``stream``.

    Intended for tests that need to capture the JSON output in a buffer;
    production callers should use :func:`configure_default`. An empty
    ``appid`` leaves the existing value unchanged.
    """
    with _State.lock:
        _reset_target()
        _State.stream = stream
        if appid:
            _State.appid = appid


def configure_default(appid: str) -> None:
    """Wire up the production destination: structured JSON to the system journal.

    Records are emitted via syslog(3), tagged ``"concierge"``, so
    ``journalctl -t concierge`` returns the audit stream without mixing it
    into Concierge's stderr output. If syslog is not reachable (such as a
    stripped-down container without ``/dev/log``) the records fall back to
    :data:`sys.stderr` so they are never silently dropped.
    """
    with _State.lock:
        _reset_target()
        if appid:
            _State.appid = appid
        try:
            handler = logging.handlers.SysLogHandler(
                address="/dev/log",
                # LOG_AUTHPRIV | LOG_WARNING: every event in Concierge's
                # vocabulary subset is WARN per the OWASP cheat sheet; the
                # per-record severity is also carried in the JSON "level".
                facility=logging.handlers.SysLogHandler.LOG_AUTHPRIV,
            )
            handler.ident = "concierge: "
            handler.setLevel(logging.WARNING)
            _State.handler = handler
        except OSError:
            # /dev/log isn't reachable; fall back to stderr so records aren't
            # silently dropped.
            _State.stream = sys.stderr


def user_id() -> str:
    """Return the userid string embedded in OWASP event names.

    The effective UID is used: Concierge runs as root, and ``SUDO_USER`` is
    not consulted because the privilege actually in play is root's. Callers
    compose this with any per-event sub-action, e.g.
    ``f"{user_id()},exec"``.
    """
    return str(os.getuid())


def _now_iso() -> str:
    """Return a UTC timestamp in RFC 3339 form with millisecond precision."""
    return datetime.now(tz=UTC).isoformat(timespec="milliseconds")


def _json_safe(value: Any) -> bool:
    """Return True if ``value`` can be serialised by json.dumps directly."""
    return isinstance(value, (str, int, float, bool, type(None), list, dict, tuple))


def emit(event: str, arg: str, description: str, **attrs: Any) -> None:
    """Record a security event at WARN level.

    Every event in Concierge's OWASP subset (``sys_startup``, ``sys_shutdown``,
    ``authz_admin``, ``privilege_permissions_changed``) is WARN per the
    vocabulary cheat sheet.

    ``event`` is one of the OWASP vocabulary event names. ``arg`` is the
    event's parameter list per the vocabulary schema (e.g. the userid for
    ``sys_startup``; ``"userid,sub_event"`` for ``authz_admin``;
    ``"userid,file"`` for ``privilege_permissions_changed``); it is appended
    to the event name as ``event:arg`` in the JSON record. ``description`` is
    a human-readable summary; ``attrs`` are optional key/value pairs giving
    event-specific context. Callers must not pass secret values (such as
    credential contents) as attrs.
    """
    with _State.lock:
        stream = _State.stream
        handler = _State.handler
        appid = _State.appid
        if stream is None and handler is None:
            # Lazy default: stderr, so audit records are never silently
            # dropped if configure() was never called.
            _State.stream = sys.stderr
            stream = sys.stderr

    event_field = f"{event}:{arg}" if arg else event
    record: dict[str, Any] = {
        "datetime": _now_iso(),
        "level": "WARN",
        "type": _SECURITY_TYPE,
        "appid": appid,
        "event": event_field,
        "description": description,
    }
    for key, value in attrs.items():
        record[key] = value if _json_safe(value) else str(value)

    line = json.dumps(record, default=str)

    if handler is not None:
        log_record = logging.LogRecord(
            name="concierge.securitylog",
            level=logging.WARNING,
            pathname=__file__,
            lineno=0,
            msg=line,
            args=None,
            exc_info=None,
        )
        # Emit must never break the caller: swallow any transport failure.
        with contextlib.suppress(Exception):
            handler.emit(log_record)
        return

    if stream is not None:
        with contextlib.suppress(Exception):
            stream.write(line + "\n")
            stream.flush()
