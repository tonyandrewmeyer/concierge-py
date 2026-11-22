"""Tests that --skip-snap-refresh reaches the snap handlers that install snaps."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from concierge.config.models import (
    ConciergeConfig,
    ConfigOverrides,
    K8sConfig,
    MicroK8sConfig,
    ProviderConfig,
)
from concierge.juju.handler import JujuHandler
from concierge.providers.k8s import K8s
from concierge.providers.microk8s import MicroK8s


def _config(skip: bool) -> ConciergeConfig:
    return ConciergeConfig(
        providers=ProviderConfig(
            k8s=K8sConfig(enable=True, channel="1.32-classic/stable"),
            microk8s=MicroK8sConfig(enable=True, channel="1.32-strict/stable"),
        ),
        overrides=ConfigOverrides(skip_snap_refresh=skip),
    )


def _worker() -> MagicMock:
    worker = MagicMock()
    worker.run = AsyncMock(return_value=b"")
    return worker


@pytest.mark.parametrize("skip", [True, False])
@pytest.mark.asyncio
async def test_k8s_install(skip: bool) -> None:
    k8s = K8s(_worker(), _config(skip))
    with patch("concierge.providers.k8s.SnapHandler") as handler_class:
        handler_class.return_value.prepare = AsyncMock()
        await k8s._install()

    assert handler_class.call_args.kwargs["skip_refresh_if_current"] is skip


@pytest.mark.parametrize("skip", [True, False])
@pytest.mark.asyncio
async def test_microk8s_install(skip: bool) -> None:
    microk8s = MicroK8s(_worker(), _config(skip))
    with patch("concierge.providers.microk8s.SnapHandler") as handler_class:
        handler_class.return_value.prepare = AsyncMock()
        await microk8s._install()

    assert handler_class.call_args.kwargs["skip_refresh_if_current"] is skip


@pytest.mark.parametrize("skip", [True, False])
@pytest.mark.asyncio
async def test_juju_install(skip: bool) -> None:
    juju = JujuHandler(_worker(), _config(skip), [])
    with patch("concierge.juju.handler.SnapHandler") as handler_class:
        handler_class.return_value.prepare = AsyncMock()
        await juju._install()

    assert handler_class.call_args.kwargs["skip_refresh_if_current"] is skip
