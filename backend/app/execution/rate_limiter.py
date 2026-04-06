"""Token bucket rate limiter with per-backend concurrency control."""

from __future__ import annotations

import asyncio
import time


class TokenBucketRateLimiter:
    """Async rate limiter using token bucket algorithm.

    Controls both requests-per-minute and concurrent requests.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        max_concurrent: int = 10,
    ):
        self._rpm = requests_per_minute
        self._interval = 60.0 / requests_per_minute  # seconds between requests
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_request_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until we can make a request (respects both RPM and concurrency)."""
        await self._semaphore.acquire()

        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_request_time = time.monotonic()

    def release(self) -> None:
        """Release the concurrency semaphore after a request completes."""
        self._semaphore.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *args):
        self.release()
