"""Unit tests for core plan module."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from concierge.config.models import (
    ConciergeConfig,
    ConfigOverrides,
    HostConfig,
    JujuConfig,
    K8sConfig,
    LXDConfig,
    ProviderConfig,
    SnapConfig,
)
from concierge.core.plan import Plan, _get_snap_channel_override, do_action


class MockExecutable:
    """Mock Executable for testing."""

    def __init__(self) -> None:
        self.prepare = AsyncMock()
        self.restore = AsyncMock()


class TestDoAction:
    """Tests for do_action function."""

    @pytest.mark.asyncio
    async def test_do_action_prepare(self) -> None:
        """Test do_action with prepare action."""
        executable = MockExecutable()
        await do_action(executable, "prepare")
        executable.prepare.assert_awaited_once()
        executable.restore.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_do_action_restore(self) -> None:
        """Test do_action with restore action."""
        executable = MockExecutable()
        await do_action(executable, "restore")
        executable.restore.assert_awaited_once()
        executable.prepare.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_do_action_invalid(self) -> None:
        """Test do_action with invalid action."""
        executable = MockExecutable()
        with pytest.raises(ValueError, match="Unknown action"):
            await do_action(executable, "invalid")


class TestGetSnapChannelOverride:
    """Tests for _get_snap_channel_override function."""

    def test_charmcraft_override(self) -> None:
        """Test getting charmcraft channel override."""
        config = ConciergeConfig(overrides=ConfigOverrides(charmcraft_channel="latest/edge"))
        channel = _get_snap_channel_override(config, "charmcraft")
        assert channel == "latest/edge"

    def test_snapcraft_override(self) -> None:
        """Test getting snapcraft channel override."""
        config = ConciergeConfig(overrides=ConfigOverrides(snapcraft_channel="latest/edge"))
        channel = _get_snap_channel_override(config, "snapcraft")
        assert channel == "latest/edge"

    def test_rockcraft_override(self) -> None:
        """Test getting rockcraft channel override."""
        config = ConciergeConfig(overrides=ConfigOverrides(rockcraft_channel="latest/edge"))
        channel = _get_snap_channel_override(config, "rockcraft")
        assert channel == "latest/edge"

    def test_no_override(self) -> None:
        """Test getting channel override for snap with no override."""
        config = ConciergeConfig()
        channel = _get_snap_channel_override(config, "charmcraft")
        assert channel == ""

    def test_other_snap_no_override(self) -> None:
        """Test getting channel override for non-craft snap."""
        config = ConciergeConfig(overrides=ConfigOverrides(charmcraft_channel="latest/edge"))
        channel = _get_snap_channel_override(config, "jq")
        assert channel == ""


class TestPlanInit:
    """Tests for Plan initialization."""

    def test_plan_init_basic(self) -> None:
        """Test basic Plan initialization."""
        config = ConciergeConfig()
        system = Mock()
        plan = Plan(config, system)

        assert plan.config == config
        assert plan.system == system
        assert plan.snaps == []
        assert plan.debs == []
        assert isinstance(plan.providers, list)

    def test_plan_init_with_snaps(self) -> None:
        """Test Plan initialization with snaps in config."""
        config = ConciergeConfig(
            host=HostConfig(
                snaps={
                    "charmcraft": SnapConfig(channel="latest/stable"),
                    "jq": SnapConfig(channel="latest/edge"),
                }
            )
        )
        system = Mock()
        plan = Plan(config, system)

        assert len(plan.snaps) == 2
        snap_names = [snap.name for snap in plan.snaps]
        assert "charmcraft" in snap_names
        assert "jq" in snap_names

        # Find charmcraft snap and check channel
        charmcraft = next(s for s in plan.snaps if s.name == "charmcraft")
        assert charmcraft.channel == "latest/stable"

    def test_plan_init_with_snap_connections(self) -> None:
        """Test Plan initialization with snap connections."""
        config = ConciergeConfig(
            host=HostConfig(
                snaps={
                    "jhack": SnapConfig(
                        channel="latest/stable", connections=["jhack:dot-local-share-juju"]
                    )
                }
            )
        )
        system = Mock()
        plan = Plan(config, system)

        assert len(plan.snaps) == 1
        jhack = plan.snaps[0]
        assert jhack.name == "jhack"
        assert jhack.connections == ["jhack:dot-local-share-juju"]

    def test_plan_init_with_snap_channel_override(self) -> None:
        """Test Plan initialization with snap channel override."""
        config = ConciergeConfig(
            host=HostConfig(snaps={"charmcraft": SnapConfig(channel="latest/stable")}),
            overrides=ConfigOverrides(charmcraft_channel="latest/edge"),
        )
        system = Mock()
        plan = Plan(config, system)

        charmcraft = plan.snaps[0]
        assert charmcraft.name == "charmcraft"
        assert charmcraft.channel == "latest/edge"  # Override applied

    def test_plan_init_with_extra_snaps(self) -> None:
        """Test Plan initialization with extra snaps from overrides."""
        config = ConciergeConfig(
            host=HostConfig(snaps={"charmcraft": SnapConfig(channel="latest/stable")}),
            overrides=ConfigOverrides(extra_snaps=["jq/latest/edge", "yq"]),
        )
        system = Mock()
        plan = Plan(config, system)

        assert len(plan.snaps) == 3
        snap_names = [snap.name for snap in plan.snaps]
        assert "charmcraft" in snap_names
        assert "jq" in snap_names
        assert "yq" in snap_names

        # Check that jq has channel from extra_snaps
        jq = next(s for s in plan.snaps if s.name == "jq")
        assert jq.channel == "latest/edge"

    def test_plan_init_with_extra_snap_override(self) -> None:
        """Test that channel override applies to extra snaps."""
        config = ConciergeConfig(
            overrides=ConfigOverrides(
                extra_snaps=["charmcraft/latest/stable"],
                charmcraft_channel="latest/edge",
            )
        )
        system = Mock()
        plan = Plan(config, system)

        charmcraft = plan.snaps[0]
        assert charmcraft.name == "charmcraft"
        assert charmcraft.channel == "latest/edge"  # Override wins

    def test_plan_init_with_debs(self) -> None:
        """Test Plan initialization with deb packages."""
        config = ConciergeConfig(host=HostConfig(packages=["python3-pip", "git"]))
        system = Mock()
        plan = Plan(config, system)

        assert plan.debs == ["python3-pip", "git"]

    def test_plan_init_with_extra_debs(self) -> None:
        """Test Plan initialization with extra deb packages."""
        config = ConciergeConfig(
            host=HostConfig(packages=["python3-pip"]),
            overrides=ConfigOverrides(extra_debs=["git", "curl"]),
        )
        system = Mock()
        plan = Plan(config, system)

        assert "python3-pip" in plan.debs
        assert "git" in plan.debs
        assert "curl" in plan.debs

    def test_plan_init_with_providers(self) -> None:
        """Test Plan initialization with enabled providers."""
        config = ConciergeConfig(
            providers=ProviderConfig(
                lxd=LXDConfig(enable=True, bootstrap=True),
                k8s=K8sConfig(enable=True, bootstrap=True),
            )
        )
        system = Mock()

        with patch("concierge.core.plan.create_provider") as mock_create:
            # Mock create_provider to return mock providers
            mock_lxd = Mock()
            mock_lxd.bootstrap.return_value = True
            mock_k8s = Mock()
            mock_k8s.bootstrap.return_value = True

            def create_side_effect(
                name: str, _system: Mock, _config: ConciergeConfig
            ) -> Mock | None:
                if name == "lxd":
                    return mock_lxd
                if name == "k8s":
                    return mock_k8s
                return None

            mock_create.side_effect = create_side_effect

            plan = Plan(config, system)

            # Should have created providers for lxd and k8s
            assert mock_lxd in plan.providers
            assert mock_k8s in plan.providers

    def test_plan_init_disable_juju_override(self) -> None:
        """Test that disable_juju override is applied during init."""
        config = ConciergeConfig(
            juju=JujuConfig(disable=False), overrides=ConfigOverrides(disable_juju=True)
        )
        system = Mock()
        plan = Plan(config, system)

        assert plan.config.juju.disable is True


class TestPlanExecute:
    """Tests for Plan.execute method."""

    @pytest.mark.asyncio
    async def test_execute_prepare(self) -> None:
        """Test executing prepare action."""
        config = ConciergeConfig(
            host=HostConfig(
                snaps={"charmcraft": SnapConfig(channel="latest/stable")},
                packages=["python3-pip"],
            ),
            juju=JujuConfig(disable=True),  # Disable Juju to simplify test
        )
        system = Mock()
        plan = Plan(config, system)

        with (
            patch("concierge.core.plan.SnapHandler") as mock_snap_handler_class,
            patch("concierge.core.plan.DebHandler") as mock_deb_handler_class,
            patch("concierge.core.plan.do_action", new_callable=AsyncMock) as mock_do_action,
        ):
            mock_snap_handler = Mock()
            mock_snap_handler_class.return_value = mock_snap_handler
            mock_deb_handler = Mock()
            mock_deb_handler_class.return_value = mock_deb_handler

            await plan.execute("prepare")

            # Verify handlers were created
            mock_snap_handler_class.assert_called_once_with(system, plan.snaps)
            mock_deb_handler_class.assert_called_once_with(system, plan.debs)

            # Verify do_action was called for snap and deb handlers
            assert mock_do_action.call_count >= 2
            calls = mock_do_action.call_args_list
            assert any(
                call[0][0] == mock_snap_handler and call[0][1] == "prepare" for call in calls
            )
            assert any(call[0][0] == mock_deb_handler and call[0][1] == "prepare" for call in calls)

    @pytest.mark.asyncio
    async def test_execute_restore(self) -> None:
        """Test executing restore action."""
        config = ConciergeConfig(
            host=HostConfig(snaps={"charmcraft": SnapConfig()}), juju=JujuConfig(disable=True)
        )
        system = Mock()
        plan = Plan(config, system)

        with (
            patch("concierge.core.plan.SnapHandler"),
            patch("concierge.core.plan.DebHandler"),
            patch("concierge.core.plan.do_action", new_callable=AsyncMock) as mock_do_action,
        ):
            await plan.execute("restore")

            # Verify do_action was called with "restore"
            calls = mock_do_action.call_args_list
            assert any(call[0][1] == "restore" for call in calls)

    @pytest.mark.asyncio
    async def test_execute_with_juju(self) -> None:
        """Test executing with Juju enabled."""
        config = ConciergeConfig(
            host=HostConfig(snaps={"charmcraft": SnapConfig()}), juju=JujuConfig(disable=False)
        )
        system = Mock()
        plan = Plan(config, system)

        with (
            patch("concierge.core.plan.SnapHandler"),
            patch("concierge.core.plan.DebHandler"),
            patch("concierge.core.plan.JujuHandler") as mock_juju_handler_class,
            patch("concierge.core.plan.do_action", new_callable=AsyncMock) as mock_do_action,
        ):
            mock_juju_handler = Mock()
            mock_juju_handler_class.return_value = mock_juju_handler

            await plan.execute("prepare")

            # Verify JujuHandler was created
            mock_juju_handler_class.assert_called_once_with(system, config, plan.providers)

            # Verify do_action was called for Juju handler
            calls = mock_do_action.call_args_list
            assert any(
                call[0][0] == mock_juju_handler and call[0][1] == "prepare" for call in calls
            )

    @pytest.mark.asyncio
    async def test_execute_with_juju_disabled(self) -> None:
        """Test that Juju handler is not called when Juju is disabled."""
        config = ConciergeConfig(
            host=HostConfig(snaps={"charmcraft": SnapConfig()}), juju=JujuConfig(disable=True)
        )
        system = Mock()
        plan = Plan(config, system)

        with (
            patch("concierge.core.plan.SnapHandler"),
            patch("concierge.core.plan.DebHandler"),
            patch("concierge.core.plan.JujuHandler") as mock_juju_handler_class,
            patch("concierge.core.plan.do_action", new_callable=AsyncMock),
        ):
            await plan.execute("prepare")

            # JujuHandler should not be created when Juju is disabled
            mock_juju_handler_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_with_providers(self) -> None:
        """Test executing with providers."""
        config = ConciergeConfig(
            providers=ProviderConfig(lxd=LXDConfig(enable=True, bootstrap=True)),
            juju=JujuConfig(disable=True),
        )
        system = Mock()

        with patch("concierge.core.plan.create_provider") as mock_create:
            mock_provider = Mock()
            mock_provider.bootstrap.return_value = True

            def create_side_effect(
                name: str, _system: Mock, _config: ConciergeConfig
            ) -> Mock | None:
                if name == "lxd":
                    return mock_provider
                return None

            mock_create.side_effect = create_side_effect

            plan = Plan(config, system)

            with (
                patch("concierge.core.plan.SnapHandler"),
                patch("concierge.core.plan.DebHandler"),
                patch("concierge.core.plan.do_action", new_callable=AsyncMock) as mock_do_action,
            ):
                await plan.execute("prepare")

                # Verify do_action was called for the provider
                calls = mock_do_action.call_args_list
                assert any(
                    call[0][0] == mock_provider and call[0][1] == "prepare" for call in calls
                )

    @pytest.mark.asyncio
    async def test_validate_called(self) -> None:
        """Test that _validate is called during execute."""
        config = ConciergeConfig(juju=JujuConfig(disable=True))
        system = Mock()
        plan = Plan(config, system)

        with (
            patch("concierge.core.plan.SnapHandler"),
            patch("concierge.core.plan.DebHandler"),
            patch("concierge.core.plan.do_action", new_callable=AsyncMock),
            patch.object(plan, "_validate", new_callable=AsyncMock) as mock_validate,
        ):
            await plan.execute("prepare")
            mock_validate.assert_awaited_once()
