"""
Token-bucket rate limiter for the NBA Stats API (stats.nba.com).

stats.nba.com has no official rate limit but will return 429s if you
hammer it. A ~0.6s delay between requests is the community-recommended
courtesy interval.

Usage:
    limiter = NbaApiRateLimiter()
    await limiter.acquire()
    # now safe to call nba_api
"""

import asyncio
import time


class NbaApiRateLimiter:
    """Simple token bucket — allows 1 request per `interval` seconds."""

    def __init__(self, interval: float = 0.6) -> None:
        self.interval = interval
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self.interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()


# Module-level singleton used by nba_stats_ingester
nba_limiter = NbaApiRateLimiter(interval=0.6)
