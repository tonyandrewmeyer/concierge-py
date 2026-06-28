"""Unit tests for the MicroK8s provider."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.config.models import (
    ConciergeConfig,
    ConfigOverrides,
    ImageRegistryConfig,
    MicroK8sConfig,
    ProviderConfig,
)
from concierge.providers.microk8s import MicroK8s


def _make_microk8s(*, image_registry_url: str = "") -> MicroK8s:
    """Construct a MicroK8s provider with a mocked worker."""
    worker = MagicMock()
    worker.run = AsyncMock(return_value=b"")
    worker.run_with_retries = AsyncMock(return_value=b"")
    worker.snap_channels = AsyncMock(return_value=["1.32-strict/stable"])
    worker.username = MagicMock(return_value="ubuntu")

    config = ConciergeConfig(
        providers=ProviderConfig(
            microk8s=MicroK8sConfig(
                enable=True,
                bootstrap=True,
                channel="1.32-strict/stable",
                image_registry=ImageRegistryConfig(url=image_registry_url),
            )
        ),
        overrides=ConfigOverrides(),
    )
    return MicroK8s(worker, config)


class TestMicroK8sPrepareImageRegistryOrder:
    """The MicroK8s init/wait-ready must run before image-registry stop/start.

    Otherwise `microk8s stop` races with snapd's in-progress
    `service-control` change from the just-completed `snap install microk8s`,
    leaving the cluster wedged.
    """

    @pytest.mark.asyncio
    async def test_wait_ready_before_and_after_stop_start(self) -> None:
        microk8s = _make_microk8s(image_registry_url="https://mirror.example.com")

        # Skip steps that don't matter for ordering and would require more mocking.
        microk8s._install = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_addons = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_non_root_user_control = AsyncMock()  # type: ignore[method-assign]
        microk8s._setup_kubectl = AsyncMock()  # type: ignore[method-assign]

        await microk8s.prepare()

        # run_with_retries is the standalone helper, not a worker method,
        # so the wait-ready calls flow through worker.run instead.
        run_cmds = [
            (c.args[0].executable, tuple(c.args[0].args))
            for c in microk8s.system.run.await_args_list
        ]
        wait_ready = ("microk8s", ("status", "--wait-ready", "--timeout", "270"))
        stop = ("microk8s", ("stop",))
        start = ("microk8s", ("start",))

        wait_ready_indices = [i for i, c in enumerate(run_cmds) if c == wait_ready]
        stop_indices = [i for i, c in enumerate(run_cmds) if c == stop]
        start_indices = [i for i, c in enumerate(run_cmds) if c == start]

        assert len(wait_ready_indices) >= 2, "expected wait-ready before stop and after start"
        assert len(stop_indices) == 1
        assert len(start_indices) == 1

        assert wait_ready_indices[0] < stop_indices[0], "first wait-ready must run before stop"
        assert start_indices[0] < wait_ready_indices[-1], "final wait-ready must run after start"

    @pytest.mark.asyncio
    async def test_wait_ready_runs_even_without_image_registry(self) -> None:
        microk8s = _make_microk8s(image_registry_url="")

        microk8s._install = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_addons = AsyncMock()  # type: ignore[method-assign]
        microk8s._enable_non_root_user_control = AsyncMock()  # type: ignore[method-assign]
        microk8s._setup_kubectl = AsyncMock()  # type: ignore[method-assign]

        await microk8s.prepare()

        run_cmds = [
            (c.args[0].executable, tuple(c.args[0].args))
            for c in microk8s.system.run.await_args_list
        ]
        wait_ready = ("microk8s", ("status", "--wait-ready", "--timeout", "270"))
        assert run_cmds.count(wait_ready) == 1
        # No stop/start without an image registry configured.
        assert ("microk8s", ("stop",)) not in run_cmds
        assert ("microk8s", ("start",)) not in run_cmds
