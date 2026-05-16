"""Human-in-the-loop TikTok verification handling."""

from __future__ import annotations

import asyncio
import logging
import time

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

VERIFICATION_TEXTS = (
    "verification",
    "captcha",
    "drag the puzzle",
    "drag the slider",
    "slide to verify",
    "complete the verification",
    "verify to continue",
    "xác minh",
    "xac minh",
    "kéo thanh trượt",
    "keo thanh truot",
    "trượt để xác minh",
    "truot de xac minh",
)

VERIFICATION_SELECTORS = (
    "iframe[src*='captcha']",
    "iframe[src*='verify']",
    "[class*='captcha' i]",
    "[id*='captcha' i]",
    "[class*='secsdk']",
    "[id*='secsdk']",
)

LOGIN_TEXTS = (
    "log in",
    "login",
    "sign in",
    "sign up",
    "continue with",
    "use your email or phone",
    "use phone / email / username",
    "đăng nhập",
    "đăng ký",
)

LOGIN_SELECTORS = (
    "iframe[src*='login']",
    "iframe[src*='accounts']",
    "#loginContainer",
    "[id='loginContainer']",
    "button:has-text('Log in')",
    "button:has-text('Sign in')",
    "button:has-text('Đăng nhập')",
    "button:has-text('Sign up')",
)


class CaptchaHandler:
    """Detect TikTok verification and pause until a human solves it."""

    def __init__(self, timeout_seconds: int, logger: logging.Logger, poll_seconds: float = 3.0) -> None:
        self.timeout_seconds = timeout_seconds
        self.logger = logger
        self.poll_seconds = poll_seconds

    async def is_challenge_visible(self, page: Page) -> bool:
        """Return True when a captcha or verification screen appears visible."""

        try:
            body_text = await page.locator("body").inner_text(timeout=1_000)
        except PlaywrightTimeoutError:
            body_text = ""
        except Exception:
            body_text = ""
        
        if any(token in body_text.lower() for token in VERIFICATION_TEXTS):
            return True

        for selector in VERIFICATION_SELECTORS:
            try:
                if await page.locator(selector).first.is_visible(timeout=200):
                    return True
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue
        return False

    async def wait_if_needed(self, page: Page) -> None:
        """Pause execution while the user solves TikTok verification."""

        if not await self.is_challenge_visible(page):
            return

        self.logger.warning("captcha_detected")
        print("\nPlease solve TikTok verification manually in the opened browser.")
        print("The crawler will resume automatically after verification disappears.\n")

        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if not await self.is_challenge_visible(page):
                self.logger.info("captcha_solved")
                await asyncio.sleep(2)
                return
            await asyncio.sleep(self.poll_seconds)

        self.logger.warning(
            "captcha_timeout",
            extra={"timeout_seconds": self.timeout_seconds},
        )

    async def is_login_prompt_visible(self, page: Page) -> bool:
        """Return True when TikTok is blocking access behind a manual login prompt."""

        try:
            body_text = await page.locator("body").inner_text(timeout=500)
        except Exception:
            body_text = ""

        normalized = body_text.lower()
        if any(token in normalized for token in LOGIN_TEXTS):
            try:
                if await page.locator("div[role='dialog']").count(timeout=300) > 0:
                    return True
            except Exception:
                return True

        try:
            if await page.locator("#loginContainer").is_visible(timeout=100):
                return True
        except Exception:
            pass

        for selector in LOGIN_SELECTORS:
            try:
                if await page.locator(selector).first.is_visible(timeout=100):
                    return True
            except Exception:
                continue
        return False

    async def auto_close_login_container(self, page: Page) -> bool:
        """Try to automatically close loginContainer aggressively.
        
        Returns True if loginContainer was found and closed, False otherwise.
        """
        try:
            # Method 1: Try to find loginContainer quickly
            try:
                login_container = page.locator("#loginContainer").first
                is_visible = await login_container.is_visible(timeout=100)
            except Exception:
                return False
            
            if not is_visible:
                return False
            
            self.logger.info("login_container_detected_attempting_close")
            print("\nLogin container detected. Closing...\n")
            
            # Method 1: Try Escape key (fastest)
            try:
                await page.press("body", "Escape")
                await asyncio.sleep(0.3)
                # Check if closed
                try:
                    if not await login_container.is_visible(timeout=50):
                        self.logger.info("login_container_closed_with_escape")
                        return True
                except Exception:
                    return True
            except Exception:
                pass
            
            # Method 2: Try clicking outside the modal to close it
            try:
                await page.click("body", timeout=500)
                await asyncio.sleep(0.3)
                try:
                    if not await login_container.is_visible(timeout=50):
                        self.logger.info("login_container_closed_with_click_outside")
                        return True
                except Exception:
                    return True
            except Exception:
                pass
            
            # Method 3: Find and click close button
            close_button_selectors = [
                "#loginContainer [class*='close']",
                "#loginContainer button[aria-label*='close' i]",
                "#loginContainer button[aria-label*='Close' i]",
                "#loginContainer button:first-of-type",
            ]
            
            for close_selector in close_button_selectors:
                try:
                    close_btn = page.locator(close_selector).first
                    if await close_btn.is_visible(timeout=100):
                        await close_btn.click(timeout=300)
                        await asyncio.sleep(0.3)
                        self.logger.info("login_container_closed_with_button")
                        return True
                except Exception:
                    continue
            
            # Method 4: Try JavaScript to remove modal overlay
            try:
                await page.evaluate("""
                    () => {
                        // Try to remove loginContainer
                        const container = document.getElementById('loginContainer');
                        if (container) {
                            container.remove();
                            return true;
                        }
                        // Try to remove modal overlay
                        const modal = document.querySelector('[role="dialog"]');
                        if (modal) {
                            modal.remove();
                            return true;
                        }
                        return false;
                    }
                """, timeout=500)
                self.logger.info("login_container_closed_with_js")
                await asyncio.sleep(0.3)
                return True
            except Exception:
                pass
                    
        except Exception as e:
            self.logger.debug(f"Error attempting to close login container: {e}")
        
        return False

    async def aggressive_close_login_container(self, page: Page) -> bool:
        """Aggressively close login container without timeout.
        
        Called during scrolling to prevent modal from blocking scroll.
        Returns True if closed, False if not present.
        """
        try:
            login_container = page.locator("#loginContainer").first
            # Very quick check - don't wait if not visible
            try:
                is_visible = await login_container.is_visible(timeout=50)
            except Exception:
                return False
            
            if not is_visible:
                return False
            
            # Try Escape (fastest)
            try:
                await page.press("body", "Escape")
                return True
            except Exception:
                pass
            
            # Try JavaScript removal (instant)
            try:
                await page.evaluate("""
                    () => {
                        const container = document.getElementById('loginContainer');
                        if (container) container.remove();
                        const modal = document.querySelector('[role="dialog"]');
                        if (modal) modal.remove();
                        return true;
                    }
                """, timeout=200)
                return True
            except Exception:
                pass
                
        except Exception:
            pass
        
        return False

    async def wait_for_login_if_needed(self, page: Page) -> None:
        """Pause briefly while TikTok login prompts are inspected."""

        try:
            await asyncio.wait_for(
                self._wait_for_login_if_needed_internal(page),
                timeout=2.0,
            )
        except asyncio.TimeoutError:
            self.logger.warning("login_check_timeout", extra={"timeout_seconds": 2.0})
            print("\nLogin check timed out. Continuing anyway...\n")
        except Exception as e:
            self.logger.debug(f"Error in login check: {e}")

    async def _wait_for_login_if_needed_internal(self, page: Page) -> None:
        """Internal login check logic."""

        if not await self.is_login_prompt_visible(page):
            return

        # Try to auto-close loginContainer if present
        if await self.auto_close_login_container(page):
            await asyncio.sleep(0.5)
            return

        self.logger.info("login_prompt_detected_skipped")
        print("\nLogin dialog detected. Skipping login and continuing.\n")

