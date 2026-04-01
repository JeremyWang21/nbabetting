"""
Shared async HTTP client with automatic retries and timeouts.

Usage:
    async with get_http_client() as client:
        resp = await client.get("https://api.example.com/data")
        resp.raise_for_status()
        data = resp.json()
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import httpx


@asynccontextmanager
async def get_http_client(
    timeout: float = 10.0,
    retries: int = 3,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.AsyncHTTPTransport(retries=retries)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        transport=transport,
        follow_redirects=True,
    ) as client:
        yield client
