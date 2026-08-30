"""Tests for the async retry helper."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from concierge.system.retry import retry_with_backoff


@pytest.fixture
def sleep() -> Iterator[AsyncMock]:
    """Patch out the backoff sleep so that the tests do not wait in real time."""
    with patch("concierge.system.retry.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        yield mock_sleep


class TestRetryWithBackoff:
    async def test_returns_without_retrying_on_success(self, sleep: AsyncMock) -> None:
        attempt = AsyncMock(return_value="ok")

        result = await retry_with_backoff(attempt, max_attempts=10)

        assert result == "ok"
        assert attempt.await_count == 1
        sleep.assert_not_awaited()

    async def test_succeeds_after_retry(self, sleep: AsyncMock) -> None:
        attempt = AsyncMock(side_effect=[ValueError("transient"), ValueError("transient"), "ok"])

        result = await retry_with_backoff(attempt, max_attempts=10)

        assert result == "ok"
        assert attempt.await_count == 3
        assert [call.args[0] for call in sleep.await_args_list] == [1.0, 2.0]

    async def test_raises_final_exception_after_exhausting_attempts(
        self, sleep: AsyncMock
    ) -> None:
        attempt = AsyncMock(side_effect=[ValueError("first"), ValueError("last")])

        with pytest.raises(ValueError, match="last"):
            await retry_with_backoff(attempt, max_attempts=2)

        assert attempt.await_count == 2
        # No backoff after the final attempt, since there is no attempt left to make.
        assert sleep.await_count == 1

    async def test_backoff_is_clamped_to_bounds(self, sleep: AsyncMock) -> None:
        attempt = AsyncMock(side_effect=ValueError("transient"))

        with pytest.raises(ValueError, match="transient"):
            await retry_with_backoff(attempt, max_attempts=8, min_wait=2, max_wait=10)

        waits = [call.args[0] for call in sleep.await_args_list]
        assert waits == [2.0, 2.0, 4.0, 8.0, 10.0, 10.0, 10.0]

    async def test_non_retryable_exception_is_raised_immediately(self, sleep: AsyncMock) -> None:
        attempt = AsyncMock(side_effect=KeyError("permanent"))

        with pytest.raises(KeyError):
            await retry_with_backoff(
                attempt,
                max_attempts=10,
                is_retryable=lambda e: not isinstance(e, KeyError),
            )

        assert attempt.await_count == 1
        sleep.assert_not_awaited()

    async def test_retryable_exception_is_retried(self, sleep: AsyncMock) -> None:
        attempt = AsyncMock(side_effect=[TypeError("transient"), "ok"])

        result = await retry_with_backoff(
            attempt,
            max_attempts=10,
            is_retryable=lambda e: not isinstance(e, KeyError),
        )

        assert result == "ok"
        assert attempt.await_count == 2

    async def test_stops_once_the_time_budget_is_spent(self) -> None:
        attempt = AsyncMock(side_effect=ValueError("transient"))

        with pytest.raises(ValueError, match="transient"):
            await retry_with_backoff(attempt, max_duration=0.2, min_wait=0.1, max_wait=0.1)

        # The budget allows a couple of backoffs, but not the ten of an attempt cap.
        assert 1 < attempt.await_count < 5

    async def test_requires_a_stop_condition(self) -> None:
        attempt = AsyncMock(return_value="ok")

        with pytest.raises(ValueError, match="max_attempts or max_duration"):
            await retry_with_backoff(attempt)

        attempt.assert_not_awaited()
