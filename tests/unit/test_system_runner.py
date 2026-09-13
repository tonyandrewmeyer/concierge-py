"""Tests for the System worker implementation."""

from typing import TYPE_CHECKING

import pytest

from concierge.system.runner import System

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def system() -> System:
    return System()


class TestWriteFilePermissions:
    async def test_writes_file_as_0600(self, system: System, tmp_path: Path) -> None:
        """Files written into the home directory can carry secrets, so they should
        be readable only by the owner regardless of the process umask."""
        filepath = tmp_path / "credentials.yaml"

        await system.write_file(filepath, b"credentials: {}\n")

        assert filepath.read_bytes() == b"credentials: {}\n"
        assert (filepath.stat().st_mode & 0o777) == 0o600

    async def test_fixes_permissions_on_overwrite(self, system: System, tmp_path: Path) -> None:
        filepath = tmp_path / "config"
        filepath.write_bytes(b"old")
        filepath.chmod(0o644)

        await system.write_file(filepath, b"new")

        assert (filepath.stat().st_mode & 0o777) == 0o600


class TestMkdirAllPermissions:
    async def test_creates_directory_as_0755(self, system: System, tmp_path: Path) -> None:
        dirpath = tmp_path / "juju"

        await system.mkdir_all(dirpath)

        assert dirpath.is_dir()
        assert (dirpath.stat().st_mode & 0o777) == 0o755

    async def test_sets_permissions_on_every_created_parent(
        self, system: System, tmp_path: Path
    ) -> None:
        dirpath = tmp_path / ".local" / "share" / "juju"

        await system.mkdir_all(dirpath)

        for path in (tmp_path / ".local", tmp_path / ".local" / "share", dirpath):
            assert (path.stat().st_mode & 0o777) == 0o755

    async def test_leaves_existing_parent_untouched(self, system: System, tmp_path: Path) -> None:
        """A pre-existing directory (like the user's home directory) should not
        have its permissions altered just because a subdirectory is created."""
        existing = tmp_path / "home"
        existing.mkdir(mode=0o700)

        await system.mkdir_all(existing / "share" / "juju")

        assert (existing.stat().st_mode & 0o777) == 0o700

    async def test_idempotent_when_directory_exists(self, system: System, tmp_path: Path) -> None:
        """Calling mkdir_all on an already-existing directory (as happens on every
        subsequent `prepare` run) must not alter its permissions."""
        dirpath = tmp_path / "juju"
        dirpath.mkdir()
        dirpath.chmod(0o700)

        await system.mkdir_all(dirpath)

        assert (dirpath.stat().st_mode & 0o777) == 0o700
