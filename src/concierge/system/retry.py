"""A small async retry helper with exponential backoff.

This mirrors upstream concierge's use of Go's `retry.DoValue` together with
`retry.RetryableError`: a caller-supplied predicate decides which failures are
transient, and everything else surfaces immediately.
"""

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def _always_retry(exc: Exception) -> bool:
    """Treat every exception as transient.

    Returns:
        True, always.
    """
    return True


async def retry_with_backoff[T](
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int | None = None,
    max_duration: float | None = None,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    is_retryable: Callable[[Exception], bool] = _always_retry,
) -> T:
    """Call an async function, retrying transient failures with exponential backoff.

    The wait before the nth retry is `2 ** (n - 1)` seconds, clamped to
    [`min_wait`, `max_wait`]. The exception raised by the final attempt
    propagates to the caller unwrapped.

    The elapsed time is checked before backing off rather than after, so
    `max_duration` bounds when the last attempt may *start*: an attempt that is
    already running is never cut short.

    Args:
        func: Async callable, taking no arguments, to run.
        max_attempts: Maximum number of attempts, or None for no attempt limit.
        max_duration: Total time budget in seconds, or None for no time limit.
        min_wait: Lower bound on the backoff, in seconds.
        max_wait: Upper bound on the backoff, in seconds.
        is_retryable: Predicate deciding whether a failure is worth retrying.

    Returns:
        The value returned by `func`.

    Raises:
        ValueError: If neither `max_attempts` nor `max_duration` is given.
        Exception: Whatever `func` raised, if it is not retryable or the
            attempt or time budget is exhausted.
    """
    if max_attempts is None and max_duration is None:
        raise ValueError("One of max_attempts or max_duration must be given")

    start = time.monotonic()
    attempt = 0

    while True:
        attempt += 1
        try:
            return await func()
        except Exception as e:
            if not is_retryable(e):
                raise
            if max_attempts is not None and attempt >= max_attempts:
                raise
            if max_duration is not None and time.monotonic() - start >= max_duration:
                raise
            await asyncio.sleep(min(max(2.0 ** (attempt - 1), min_wait), max_wait))
