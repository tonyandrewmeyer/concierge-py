"""Unit tests for the SnapHandler."""

import asyncio
import dataclasses
import io
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.packages import snap_handler as snap_handler_module
from concierge.packages.snap_handler import SnapHandler, channel_satisfied, normalise_channel
from concierge.system.dryrun import DryRunWorker
from concierge.system.models import InstalledSnapInfo, Snap, SnapInfo

if TYPE_CHECKING:
    from concierge.system.command import Command


def _make_handler(snap: Snap, snap_info: SnapInfo) -> tuple[SnapHandler, MagicMock]:
    worker = MagicMock()
    worker.snap_info = AsyncMock(return_value=snap_info)
    worker.snap_installed_info = AsyncMock(return_value=InstalledSnapInfo())
    worker.run = AsyncMock()
    worker.run_exclusive = AsyncMock()
    handler = SnapHandler(worker, [snap])
    return handler, worker


def _commands(worker: MagicMock) -> list[Command]:
    return [call.args[0] for call in worker.run.await_args_list]


def _install_args(worker: MagicMock) -> list[str]:
    commands = _commands(worker)
    assert len(commands) == 1
    return commands[0].args


class TestSnapHandlerRevision:
    """Tests for how SnapHandler passes the snap revision through to snap install."""

    @pytest.mark.asyncio
    async def test_revision_only(self) -> None:
        """A revision-only snap should produce a --revision argument."""
        handler, worker = _make_handler(
            Snap(name="juju", revision="30000"),
            SnapInfo(installed=False, classic=False),
        )

        await handler.prepare()

        assert _install_args(worker) == ["install", "juju", "--revision", "30000"]

    @pytest.mark.asyncio
    async def test_channel_and_revision(self) -> None:
        """Both --channel and --revision should appear when both are set.

        Snap installs the specified revision and uses the channel only for
        tracking after install.
        """
        handler, worker = _make_handler(
            Snap(name="juju", channel="3.6/stable", revision="30000"),
            SnapInfo(installed=False, classic=False),
        )

        await handler.prepare()

        assert _install_args(worker) == [
            "install",
            "juju",
            "--channel",
            "3.6/stable",
            "--revision",
            "30000",
        ]


class TestSnapHandlerInstall:
    """Tests for SnapHandler._install_snap."""

    @pytest.mark.asyncio
    async def test_active_snap_is_refreshed(self) -> None:
        """An installed and active snap should be refreshed, not enabled."""
        handler, worker = _make_handler(
            Snap(name="hello-world", channel="latest/stable"),
            SnapInfo(installed=True, classic=False, active=True),
        )

        await handler.prepare()

        actions = [(c.executable, c.args[0]) for c in _commands(worker)]
        assert ("snap", "refresh") in actions
        assert ("snap", "enable") not in actions
        assert ("snap", "install") not in actions

    @pytest.mark.asyncio
    async def test_disabled_snap_is_enabled_then_refreshed(self) -> None:
        """A disabled-but-installed snap must be enabled before refresh.

        Otherwise `snap refresh` will fail because snapd refuses to refresh a
        disabled snap, and we must not fall back to `snap install` because the
        snap is already on disk.
        """
        handler, worker = _make_handler(
            Snap(name="hello-world", channel="latest/stable"),
            SnapInfo(installed=True, classic=False, active=False),
        )

        await handler.prepare()

        actions = [(c.executable, c.args[0], c.args[1]) for c in _commands(worker)]
        assert ("snap", "enable", "hello-world") in actions
        assert ("snap", "refresh", "hello-world") in actions
        # Crucially, install must NOT be used for a snap that is already on disk.
        assert ("snap", "install", "hello-world") not in actions

        # Enable must come before refresh.
        enable_index = actions.index(("snap", "enable", "hello-world"))
        refresh_index = actions.index(("snap", "refresh", "hello-world"))
        assert enable_index < refresh_index

    @pytest.mark.asyncio
    async def test_not_installed_snap_is_installed(self) -> None:
        """A snap that is not on the system is installed (not enabled or refreshed)."""
        handler, worker = _make_handler(
            Snap(name="hello-world", channel="latest/stable"),
            SnapInfo(installed=False, classic=False, active=False),
        )

        await handler.prepare()

        actions = [(c.executable, c.args[0]) for c in _commands(worker)]
        assert ("snap", "install") in actions
        assert ("snap", "enable") not in actions
        assert ("snap", "refresh") not in actions


def _snap_log_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == snap_handler_module.__name__]


class TestSnapHandlerLogging:
    """Tests for the version, revision and tracking details in snap log lines."""

    @pytest.mark.asyncio
    async def test_install_logs_new_details(self, caplog: pytest.LogCaptureFixture) -> None:
        handler, worker = _make_handler(
            Snap(name="juju", channel="3/stable"), SnapInfo(installed=False)
        )
        worker.snap_installed_info.return_value = InstalledSnapInfo(
            installed=True, active=True, tracking_channel="3/stable", revision="31", version="3.6"
        )

        with caplog.at_level(logging.INFO):
            await handler.prepare()

        assert _snap_log_messages(caplog) == [
            "Installed snap [revision=31 snap=juju tracking=3/stable version=3.6]"
        ]
        worker.snap_installed_info.assert_awaited_once_with("juju")

    @pytest.mark.asyncio
    async def test_refresh_logs_new_and_previous_details(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handler, worker = _make_handler(
            Snap(name="juju", channel="3/stable"),
            SnapInfo(
                installed=True,
                active=True,
                tracking_channel="2.9/stable",
                revision="20",
                version="2.9",
            ),
        )
        worker.snap_installed_info.return_value = InstalledSnapInfo(
            installed=True, active=True, tracking_channel="3/stable", revision="31", version="3.6"
        )

        with caplog.at_level(logging.INFO):
            await handler.prepare()

        assert _snap_log_messages(caplog) == [
            "Refreshed snap [from.revision=20 from.tracking=2.9/stable from.version=2.9 "
            "revision=31 snap=juju tracking=3/stable version=3.6]"
        ]

    @pytest.mark.asyncio
    async def test_enable_logs_details(self, caplog: pytest.LogCaptureFixture) -> None:
        handler, _ = _make_handler(
            Snap(name="juju"),
            SnapInfo(
                installed=True,
                active=False,
                tracking_channel="3/stable",
                revision="31",
                version="3.6",
            ),
        )

        with caplog.at_level(logging.INFO):
            await handler.prepare()

        assert (
            "Enabled disabled snap [revision=31 snap=juju tracking=3/stable version=3.6]"
            in _snap_log_messages(caplog)
        )

    @pytest.mark.asyncio
    async def test_lookup_failure_still_logs_previous_details(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handler, worker = _make_handler(
            Snap(name="juju"),
            SnapInfo(
                installed=True,
                active=True,
                tracking_channel="3/stable",
                revision="30",
                version="3.5",
            ),
        )
        worker.snap_installed_info.side_effect = RuntimeError("snapd is down")

        with caplog.at_level(logging.INFO):
            await handler.prepare()

        assert _snap_log_messages(caplog) == [
            "Refreshed snap [from.revision=30 from.tracking=3/stable from.version=3.5 snap=juju]"
        ]

    @pytest.mark.asyncio
    async def test_lookup_is_bounded(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(snap_handler_module, "SNAP_LOG_LOOKUP_TIMEOUT", 0.01)
        handler, worker = _make_handler(Snap(name="juju"), SnapInfo(installed=False))

        async def hang(_: str) -> InstalledSnapInfo:
            await asyncio.sleep(10)
            return InstalledSnapInfo()

        worker.snap_installed_info.side_effect = hang

        with caplog.at_level(logging.INFO):
            await handler.prepare()

        assert _snap_log_messages(caplog) == ["Installed snap [snap=juju]"]

    @pytest.mark.asyncio
    async def test_lookup_skipped_when_info_disabled(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        handler, worker = _make_handler(Snap(name="juju"), SnapInfo(installed=False))

        with caplog.at_level(logging.WARNING):
            await handler.prepare()

        worker.snap_installed_info.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_lookup_skipped_in_dry_run(self, caplog: pytest.LogCaptureFixture) -> None:
        real = MagicMock()
        real.snap_info = AsyncMock(return_value=SnapInfo(installed=False))
        real.snap_installed_info = AsyncMock()
        real.run = AsyncMock()
        handler = SnapHandler(DryRunWorker(real, out=io.StringIO()), [Snap(name="juju")])

        with caplog.at_level(logging.INFO):
            await handler.prepare()

        real.snap_installed_info.assert_not_awaited()
        assert _snap_log_messages(caplog) == ["Installed snap [snap=juju]"]


class TestSnapHandlerPrepareSnap:
    """Tests for SnapHandler.prepare_snap, which reuses details looked up by the caller."""

    @pytest.mark.asyncio
    async def test_does_not_look_up_snap_again(self) -> None:
        handler, worker = _make_handler(
            Snap(name="lxd", channel="5.21/stable", connections=["lxd:foo"]),
            SnapInfo(installed=False),
        )

        await handler.prepare_snap(handler.snaps[0], SnapInfo(installed=False, classic=True))

        worker.snap_info.assert_not_awaited()
        args = [c.args for c in _commands(worker)]
        assert args == [
            ["install", "lxd", "--channel", "5.21/stable", "--classic"],
            ["connect", "lxd:foo"],
        ]


class TestChannelSatisfied:
    """Tests for channel normalisation and comparison."""

    @pytest.mark.parametrize(
        ("channel", "expected"),
        [
            ("", ""),
            ("stable", "latest/stable"),
            ("edge", "latest/edge"),
            ("edge/fix", "latest/edge/fix"),
            ("3", "3/stable"),
            ("3/stable", "3/stable"),
            ("latest/stable", "latest/stable"),
            ("1.32-classic/stable", "1.32-classic/stable"),
            ("3/edge/fix", "3/edge/fix"),
        ],
    )
    def test_normalise_channel(self, channel: str, expected: str) -> None:
        assert normalise_channel(channel) == expected

    @pytest.mark.parametrize(
        ("wanted", "tracking", "expected"),
        [
            ("", "", True),
            ("", "3/stable", True),
            ("3/stable", "", False),
            ("stable", "latest/stable", True),
            ("3", "3/stable", True),
            ("3/stable", "3/edge", False),
            ("3.6/stable", "3/stable", False),
        ],
    )
    def test_channel_satisfied(self, wanted: str, tracking: str, expected: bool) -> None:
        assert channel_satisfied(wanted, tracking) is expected


def _make_skip_handler(
    snap: Snap, local: InstalledSnapInfo, *, skip: bool = True
) -> tuple[SnapHandler, MagicMock]:
    worker = MagicMock()
    worker.snap_info = AsyncMock(return_value=SnapInfo(**dataclasses.asdict(local)))
    worker.snap_installed_info = AsyncMock(return_value=local)
    worker.run = AsyncMock()
    return SnapHandler(worker, [snap], skip_refresh_if_current=skip), worker


class TestSnapHandlerSkipRefresh:
    """Tests for leaving snaps alone that are already on the requested channel."""

    @pytest.mark.asyncio
    async def test_current_snap_is_left_alone(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="juju", channel="3/stable", connections=["juju:ssh-keys"]),
            InstalledSnapInfo(installed=True, active=True, tracking_channel="3/stable"),
        )

        await handler.prepare()

        worker.snap_info.assert_not_awaited()
        assert [c.args for c in _commands(worker)] == [["connect", "juju:ssh-keys"]]

    @pytest.mark.asyncio
    async def test_normalised_channel_counts_as_current(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="charmcraft", channel="stable"),
            InstalledSnapInfo(installed=True, active=True, tracking_channel="latest/stable"),
        )

        await handler.prepare()

        worker.snap_info.assert_not_awaited()
        assert _commands(worker) == []

    @pytest.mark.asyncio
    async def test_no_channel_requested_counts_as_current(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="jhack"),
            InstalledSnapInfo(installed=True, active=True, tracking_channel=""),
        )

        await handler.prepare()

        assert _commands(worker) == []

    @pytest.mark.asyncio
    async def test_disabled_current_snap_is_enabled(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="juju", channel="3/stable"),
            InstalledSnapInfo(installed=True, active=False, tracking_channel="3/stable"),
        )

        await handler.prepare()

        assert [c.args for c in _commands(worker)] == [["enable", "juju"]]

    @pytest.mark.asyncio
    async def test_different_channel_is_refreshed(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="juju", channel="3.6/stable"),
            InstalledSnapInfo(installed=True, active=True, tracking_channel="3.5/stable"),
        )

        await handler.prepare()

        worker.snap_info.assert_awaited_once()
        assert _install_args(worker) == ["refresh", "juju", "--channel", "3.6/stable"]

    @pytest.mark.asyncio
    async def test_local_file_snap_is_moved_to_requested_channel(self) -> None:
        """A snap installed from a file has no tracking channel."""
        handler, worker = _make_skip_handler(
            Snap(name="juju", channel="3/stable"),
            InstalledSnapInfo(installed=True, active=True, tracking_channel=""),
        )

        await handler.prepare()

        assert _install_args(worker) == ["refresh", "juju", "--channel", "3/stable"]

    @pytest.mark.asyncio
    async def test_not_installed_snap_is_installed(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="juju", channel="3/stable"), InstalledSnapInfo()
        )

        await handler.prepare()

        assert _install_args(worker) == ["install", "juju", "--channel", "3/stable"]

    @pytest.mark.asyncio
    async def test_pinned_revision_is_still_refreshed(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="juju", channel="3/stable", revision="30000"),
            InstalledSnapInfo(installed=True, active=True, tracking_channel="3/stable"),
        )

        await handler.prepare()

        worker.snap_info.assert_awaited_once()
        assert _install_args(worker)[:2] == ["refresh", "juju"]

    @pytest.mark.asyncio
    async def test_not_skipped_unless_enabled(self) -> None:
        handler, worker = _make_skip_handler(
            Snap(name="juju", channel="3/stable"),
            InstalledSnapInfo(installed=True, active=True, tracking_channel="3/stable"),
            skip=False,
        )

        await handler.prepare()

        assert _install_args(worker) == ["refresh", "juju", "--channel", "3/stable"]

    @pytest.mark.asyncio
    async def test_snapd_failure_is_an_error(self) -> None:
        handler, worker = _make_skip_handler(Snap(name="juju"), InstalledSnapInfo())
        worker.snap_installed_info.side_effect = RuntimeError("snapd is down")

        with pytest.raises(RuntimeError):
            await handler.prepare()

        assert _commands(worker) == []


class TestSnapHandlerDefaultChannel:
    """Tests for the default channel, which only applies to fresh installs."""

    @pytest.mark.parametrize(
        ("snap", "installed", "expected"),
        [
            pytest.param(
                Snap(name="k8s", default_channel="1.32-classic/stable"),
                False,
                ["install", "k8s", "--channel", "1.32-classic/stable", "--classic"],
                id="fresh install uses the default channel",
            ),
            pytest.param(
                Snap(name="k8s", default_channel="1.32-classic/stable"),
                True,
                ["refresh", "k8s", "--classic"],
                id="installed snap stays on its tracking channel",
            ),
            pytest.param(
                Snap(
                    name="k8s",
                    channel="1.34-classic/stable",
                    default_channel="1.32-classic/stable",
                ),
                False,
                ["install", "k8s", "--channel", "1.34-classic/stable", "--classic"],
                id="explicit channel wins over the default on install",
            ),
            pytest.param(
                Snap(
                    name="k8s",
                    channel="1.34-classic/stable",
                    default_channel="1.32-classic/stable",
                ),
                True,
                ["refresh", "k8s", "--channel", "1.34-classic/stable", "--classic"],
                id="explicit channel wins over the default on refresh",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_default_channel(self, snap: Snap, installed: bool, expected: list[str]) -> None:
        handler, worker = _make_handler(
            snap,
            SnapInfo(
                installed=installed,
                active=installed,
                tracking_channel="1.33-classic/stable" if installed else "",
                classic=True,
            ),
        )

        await handler.prepare()

        assert _install_args(worker) == expected
        # Confinement is looked up on the channel that would be installed from.
        worker.snap_info.assert_awaited_once_with("k8s", snap.channel or snap.default_channel)
