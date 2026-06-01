"""Unit tests for the K8s provider."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from concierge.config.models import (
    ConciergeConfig,
    ConfigOverrides,
    K8sConfig,
    ProviderConfig,
)
from concierge.providers.k8s import K8s


def _make_k8s(*, needs_bootstrap: bool) -> tuple[K8s, AsyncMock, AsyncMock]:
    """Construct a K8s provider with mocked worker and bootstrap check."""
    worker = MagicMock()
    worker.run = AsyncMock()
    worker.run_with_retries = AsyncMock()
    worker.run_exclusive = AsyncMock()
    worker.write_home_file = AsyncMock()
    worker.remove_all_home = AsyncMock()

    config = ConciergeConfig(
        providers=ProviderConfig(k8s=K8sConfig(enable=True, bootstrap=True)),
        overrides=ConfigOverrides(),
    )

    k8s = K8s(worker, config)

    needs_bootstrap_mock = AsyncMock(return_value=needs_bootstrap)
    handle_containerd_mock = AsyncMock()
    k8s._needs_bootstrap = needs_bootstrap_mock  # type: ignore[method-assign]
    k8s._handle_existing_containerd = handle_containerd_mock  # type: ignore[method-assign]

    return k8s, needs_bootstrap_mock, handle_containerd_mock


class TestK8sInit:
    """Tests for K8s._init behaviour around containerd handling."""

    @pytest.mark.asyncio
    async def test_handles_containerd_when_bootstrap_needed(self) -> None:
        """When bootstrap is needed, the existing containerd should be cleared."""
        k8s, _, handle_containerd = _make_k8s(needs_bootstrap=True)

        await k8s._init()

        handle_containerd.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_containerd_when_already_bootstrapped(self) -> None:
        """When the cluster is already bootstrapped, leave /run/containerd alone.

        Otherwise running concierge prepare a second time on an existing k8s
        cluster would break it.
        """
        k8s, _, handle_containerd = _make_k8s(needs_bootstrap=False)

        await k8s._init()

        handle_containerd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bootstraps_when_needed(self) -> None:
        """When bootstrap is needed, a bootstrap command runs before status."""
        k8s, _, _ = _make_k8s(needs_bootstrap=True)

        await k8s._init()

        commands = [call.args[0] for call in k8s.system.run.await_args_list]
        executables_and_args = [(c.executable, tuple(c.args)) for c in commands]
        assert ("k8s", ("bootstrap",)) in executables_and_args
        assert ("k8s", ("status", "--wait-ready", "--timeout", "270s")) in executables_and_args

    @pytest.mark.asyncio
    async def test_no_bootstrap_when_already_bootstrapped(self) -> None:
        """When already bootstrapped, only the readiness check is run."""
        k8s, _, _ = _make_k8s(needs_bootstrap=False)

        await k8s._init()

        commands = [call.args[0] for call in k8s.system.run.await_args_list]
        executables_and_args = [(c.executable, tuple(c.args)) for c in commands]
        assert ("k8s", ("bootstrap",)) not in executables_and_args
        assert ("k8s", ("status", "--wait-ready", "--timeout", "270s")) in executables_and_args
