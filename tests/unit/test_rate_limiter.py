"""Tests for the token bucket rate limiter."""

import asyncio
import time
import pytest

from backend.app.execution.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    def test_concurrency_limit(self):
        """Should not exceed max_concurrent parallel operations."""
        limiter = TokenBucketRateLimiter(requests_per_minute=6000, max_concurrent=3)
        max_concurrent_seen = 0
        current = 0

        async def task():
            nonlocal max_concurrent_seen, current
            async with limiter:
                current += 1
                if current > max_concurrent_seen:
                    max_concurrent_seen = current
                await asyncio.sleep(0.05)
                current -= 1

        async def run():
            await asyncio.gather(*[task() for _ in range(10)])

        asyncio.get_event_loop().run_until_complete(run())
        assert max_concurrent_seen <= 3

    def test_rpm_throttling(self):
        """RPM limit should introduce delays between requests."""
        # 120 RPM = 0.5 seconds between requests
        limiter = TokenBucketRateLimiter(requests_per_minute=120, max_concurrent=10)

        async def run():
            t0 = time.monotonic()
            for _ in range(3):
                async with limiter:
                    pass
            return time.monotonic() - t0

        elapsed = asyncio.get_event_loop().run_until_complete(run())
        # 3 requests at 120 RPM (0.5s interval) should take ~1.0s
        assert elapsed >= 0.9

    def test_context_manager(self):
        """Should work as async context manager."""
        limiter = TokenBucketRateLimiter()

        async def run():
            async with limiter:
                return "ok"

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == "ok"

    def test_release_on_exception(self):
        """Semaphore should be released even if code raises."""
        limiter = TokenBucketRateLimiter(requests_per_minute=6000, max_concurrent=1)

        async def run():
            try:
                async with limiter:
                    raise ValueError("boom")
            except ValueError:
                pass

            # Should be able to acquire again
            async with limiter:
                return "recovered"

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == "recovered"

    def test_high_rpm_no_throttle(self):
        """Very high RPM should not introduce significant delay."""
        limiter = TokenBucketRateLimiter(requests_per_minute=60000, max_concurrent=100)

        async def run():
            t0 = time.monotonic()
            for _ in range(5):
                async with limiter:
                    pass
            return time.monotonic() - t0

        elapsed = asyncio.get_event_loop().run_until_complete(run())
        assert elapsed < 0.5
