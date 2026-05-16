"""Small anti-detection helpers for Playwright.

This module uses ``playwright-stealth`` when available and keeps a conservative
fallback script for classroom machines where package versions differ.
"""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import BrowserContext, Page


async def apply_stealth(context: BrowserContext, page: Page, logger: logging.Logger) -> None:
    """Apply low-risk browser patches before TikTok scripts execute."""

    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """
    )
    try:
        from playwright_stealth import stealth_async  # type: ignore

        await stealth_async(page)  # pragma: no cover - depends on optional package API
        logger.info("stealth_applied", extra={"provider": "playwright-stealth"})
    except Exception as exc:  # pragma: no cover - package APIs vary by version
        logger.info("stealth_applied", extra={"provider": "fallback", "note": str(exc)})


def context_kwargs_for_emulation(emulation: str) -> dict[str, Any]:
    """Return Playwright context options for desktop or mobile browsing."""

    if emulation == "mobile":
        return {
            "viewport": {"width": 390, "height": 844},
            "is_mobile": True,
            "has_touch": True,
            "user_agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                "Mobile/15E148 Safari/604.1"
            ),
        }
    return {
        "viewport": {"width": 1366, "height": 900},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }

