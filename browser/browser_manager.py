"""Async Playwright browser lifecycle management."""

from __future__ import annotations

import logging
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from browser.stealth import apply_stealth, context_kwargs_for_emulation
from config.settings import AppSettings


class BrowserManager:
    """Own the Playwright runtime and one browser context."""

    def __init__(self, settings: AppSettings, logger: logging.Logger) -> None:
        self.settings = settings
        self.logger = logger
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def start(self) -> Page:
        """Launch Chromium and return the first page."""

        self._playwright = await async_playwright().start()
        launch_options = {
            "headless": self.settings.headless,
            "args": [
                "--disable-infobars",
                "--disable-notifications",
                "--disable-popup-blocking",
            ],
        }
        if self.settings.chrome_path:
            launch_options["executable_path"] = str(Path(self.settings.chrome_path))
        elif self.settings.browser_channel:
            launch_options["channel"] = self.settings.browser_channel

        try:
            self._browser = await self._playwright.chromium.launch(**launch_options)
        except Exception as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "Could not find Chromium" in message:
                raise RuntimeError(
                    "Playwright browser executable not found. Run 'python -m playwright install chromium' "
                    "or install browsers with Playwright before retrying."
                ) from exc
            raise

        self.context = await self._browser.new_context(
            accept_downloads=True,
            ignore_https_errors=True,
            locale=self.settings.language,
            timezone_id=self.settings.timezone_id,
            **context_kwargs_for_emulation(self.settings.emulation),
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
            },
        )
        return self.page

    async def new_page(self) -> Page:
        """Create a new page in the browser context."""

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
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self.logger.info("browser_closed")

