"""Async Playwright browser lifecycle management."""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from browser.session_manager import SessionManager
from browser.stealth import apply_stealth, context_kwargs_for_emulation
from config.settings import AppSettings


class BrowserManager:
    """Own the Playwright runtime and one persistent Chromium context."""

    def __init__(self, settings: AppSettings, logger: logging.Logger) -> None:
        self.settings = settings
        self.logger = logger
        self._playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def start(self) -> Page:
        """Launch Chromium with a persistent profile and return the first page."""

        profile_dir = SessionManager(self.settings.profile_dir, self.logger).prepare_profile()
        self._playwright = await async_playwright().start()
        launch_options = {
            "headless": self.settings.headless,
            "locale": self.settings.language,
            "timezone_id": self.settings.timezone_id,
            "accept_downloads": True,
            "ignore_https_errors": True,
            "args": [
                "--disable-infobars",
                "--disable-notifications",
                "--disable-popup-blocking",
            ],
            **context_kwargs_for_emulation(self.settings.emulation),
        }
        if self.settings.chrome_path:
            launch_options["executable_path"] = str(Path(self.settings.chrome_path))
        elif self.settings.browser_channel:
            launch_options["channel"] = self.settings.browser_channel

        self.context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            **launch_options,
        )
        # Set conservative extra headers to match typical browser requests
        try:
            await self.context.set_extra_http_headers({"accept-language": self.settings.language or "en-US"})
        except Exception:
            pass
        self.context.set_default_timeout(self.settings.page_timeout_ms)
        self.context.set_default_navigation_timeout(self.settings.page_timeout_ms)

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await apply_stealth(self.context, self.page, self.logger)
        self.logger.info(
            "browser_launched",
            extra={
                "headless": self.settings.headless,
                "emulation": self.settings.emulation,
                "profile_dir": str(profile_dir),
            },
        )
        return self.page

    async def new_page(self) -> Page:
        """Create a new page in the persistent context."""

        if self.context is None:
            raise RuntimeError("Browser context is not started.")
        page = await self.context.new_page()
        await apply_stealth(self.context, page, self.logger)
        return page

    async def close(self) -> None:
        """Close Playwright resources."""

        if self.context is not None:
            await self.context.close()
            self.context = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self.logger.info("browser_closed")

