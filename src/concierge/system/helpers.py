"""Standalone helper functions built on top of the Worker protocol."""

import asyncio
from pathlib import Path

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_delay,
    wait_exponential,
)

from concierge.system.command import Command, CommandError
from concierge.system.worker import Worker

# Guards access to _cmd_locks.
_lock_guard = asyncio.Lock()

# Per-executable locks for run_exclusive.
_cmd_locks: dict[str, asyncio.Lock] = {}


async def run_exclusive(worker: Worker, cmd: Command) -> bytes:
    """Execute a command with exclusive per-executable locking.

    Only one command with the same executable can run at a time.
    """
    async with _lock_guard:
        if cmd.executable not in _cmd_locks:
            _cmd_locks[cmd.executable] = asyncio.Lock()
        lock = _cmd_locks[cmd.executable]

    async with lock:
        return await worker.run(cmd)


async def run_with_retries(worker: Worker, cmd: Command, max_duration_ms: int) -> bytes:
    """Execute a command with exponential backoff retries."""
    max_duration_sec = max_duration_ms / 1000.0
    per_attempt_timeout = max_duration_sec * 0.9

    try:
        async for attempt in AsyncRetrying(
            wait=wait_exponential(multiplier=1, min=1, max=60),
            stop=stop_after_delay(max_duration_sec),
            reraise=True,
            retry=retry_if_exception_type((CommandError, asyncio.TimeoutError)),
        ):
            with attempt:
                return await asyncio.wait_for(worker.run(cmd), timeout=per_attempt_timeout)
    except RetryError as e:
        exc = e.last_attempt.exception()
        if exc is not None:
            raise exc from e
        raise
    except TimeoutError as e:
        raise CommandError(cmd.command_string, -1, "Command timed out") from e

    # This should never be reached due to reraise=True.
    raise RuntimeError("Unexpected retry error")


async def read_home_file(worker: Worker, filepath: Path) -> bytes:
    """Read a file at a path relative to the user's home directory."""
    full_path = worker.home_dir() / filepath
    return await worker.read_file(full_path)


async def write_home_file(worker: Worker, filepath: Path, contents: bytes) -> None:
    """Write contents to a path relative to the user's home directory.

    Creates parent directories and adjusts ownership as needed.
    """
    await mk_home_subdir(worker, filepath.parent)

    full_path = worker.home_dir() / filepath
    await worker.write_file(full_path, contents)
    await worker.chown_all(full_path)


async def mk_home_subdir(worker: Worker, subdirectory: Path) -> None:
    """Create a directory relative to the user's home directory.

    Changes ownership of the top-level directory within home.
    """
    if subdirectory.is_absolute():
        raise ValueError("Only relative paths are supported")

    full_path = worker.home_dir() / subdirectory
    await worker.mkdir_all(full_path)

    if subdirectory.parts:
        top_level = worker.home_dir() / subdirectory.parts[0]
        await worker.chown_all(top_level)
