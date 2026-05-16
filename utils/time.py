"""Time helpers for async crawling."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return an ISO timestamp with timezone information."""

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


async def sleep_with_jitter(seconds: float, jitter: float = 0.25) -> None:
    """Sleep asynchronously with small random jitter to avoid rigid timing."""

    delay = max(0.05, seconds + random.uniform(-jitter, jitter))
    await asyncio.sleep(delay)

