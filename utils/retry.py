"""Async retry helper with structured logging."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


def async_retry(
    *,
    max_attempts: int = 3,
    base_delay: float = 0.8,
    logger: logging.Logger | None = None,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Retry an async function with exponential backoff."""

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            active_logger = logger or logging.getLogger(func.__module__)
            last_error: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_error = exc
                    active_logger.warning(
                        "retry_attempt",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "error": str(exc),
                        },
                    )
                    if attempt == max_attempts:
                        break
                    await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
            assert last_error is not None
            raise last_error

        return wrapper

    return decorator

