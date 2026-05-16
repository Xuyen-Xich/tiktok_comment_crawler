"""High-level TikTok crawler orchestration."""

from __future__ import annotations

import logging
import asyncio
import re
from pathlib import Path
from urllib.parse import quote_plus

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from browser.captcha_handler import CaptchaHandler
from config.settings import AppSettings
from crawler.api_interceptor import TikTokApiInterceptor
from crawler.dom_extractor import DomExtractor
from crawler.parser import CommentParser, merge_comment_groups
from crawler.scroll_engine import ScrollEngine
from crawler.selectors import COMMENT_TAB_TEXTS, REPLY_BUTTON_TEXTS
from models.comment import Comment, dedupe_comments
from models.video import VideoTarget
from utils.retry import async_retry
from utils.text import VIDEO_URL_RE, extract_video_id, normalize_tiktok_url
from utils.time import sleep_with_jitter


class TikTokCrawler:
    """Crawl comments from TikTok videos using API interception plus DOM fallback."""

    def __init__(
        self,
        page: Page,
        settings: AppSettings,
        logger: logging.Logger,
        *,
        parser: CommentParser | None = None,
        captcha_handler: CaptchaHandler | None = None,
        interceptor: TikTokApiInterceptor | None = None,
        dom_extractor: DomExtractor | None = None,
        scroll_engine: ScrollEngine | None = None,
    ) -> None:
        self.page = page
        self.settings = settings
        self.logger = logger
        self.parser = parser or CommentParser(logger)
        self.captcha_handler = captcha_handler or CaptchaHandler(settings.captcha_timeout_seconds, logger)
        self.interceptor = interceptor or TikTokApiInterceptor(self.parser, logger)
        self.dom_extractor = dom_extractor or DomExtractor(self.parser, logger)
        self.scroll_engine = scroll_engine or ScrollEngine(
            logger,
            scroll_steps=settings.scroll_steps,
            scroll_pixels=settings.scroll_pixels,
            pause_seconds=settings.scroll_pause_seconds,
        )
        self.interceptor.attach(page)
        self._login_closer_task: asyncio.Task | None = None
        self._login_closer_stop: asyncio.Event = asyncio.Event()

    async def _login_closer_loop(self) -> None:
        """Background loop that aggressively closes login modal periodically.

        Runs until `self._login_closer_stop` is set. Uses short sleeps so it
        does not interfere with normal crawling operations.
        """
        try:
            while not self._login_closer_stop.is_set():
                try:
                    # aggressive_close is fast (small timeouts) so await is fine
                    await self.captcha_handler.aggressive_close_login_container(self.page)
                except Exception:
                    # Never let this background task raise
                    pass
                # Run fairly frequently but not too tight
                await asyncio.sleep(0.8)
        except asyncio.CancelledError:
            return

    def _start_login_closer(self) -> None:
        """Start background login-closer if not already running."""
        if self._login_closer_task and not self._login_closer_task.done():
            return
        self._login_closer_stop.clear()
        self._login_closer_task = asyncio.create_task(self._login_closer_loop())

    async def _stop_login_closer(self) -> None:
        """Stop the background login-closer task and wait for it to finish."""
        try:
            self._login_closer_stop.set()
            if self._login_closer_task:
                self._login_closer_task.cancel()
                try:
                    await self._login_closer_task
                except Exception:
                    pass
        finally:
            self._login_closer_task = None

    @async_retry(max_attempts=3, base_delay=1.0)
    async def open_url(self, url: str) -> None:
        """Navigate and wait for TikTok to render enough page structure."""

        self.logger.info("navigation_started", extra={"url": url})
        await self.page.goto(url, wait_until="domcontentloaded")
        await self.page.locator("body").wait_for(timeout=self.settings.page_timeout_ms)
        await self.captcha_handler.wait_if_needed(self.page)
        self.logger.info("navigation_completed", extra={"url": url})

    async def crawl_video(
        self,
        url: str,
        *,
        keyword: str = "",
        max_comments: int | None = None,
        source_type: str = "post",
        search_rank: int | None = None,
    ) -> list[Comment]:
        """Crawl comments and replies from one TikTok video URL."""

        target = VideoTarget(url=url, keyword=keyword, source_type=source_type, search_rank=search_rank)
        self.interceptor.clear()
        self.interceptor.configure_context(video_url=target.url, keyword=keyword, search_rank=search_rank)
        await self.open_url(target.url)
        await self.ensure_comments_visible()
        # Start background task to aggressively close any login modal during long crawls
        try:
            self._start_login_closer()
        except Exception:
            pass

        records_by_id: dict[tuple[str, str], Comment] = {}
        stale_rounds = 0

        for round_number in range(1, self.settings.max_scrolls + 1):
            if self.settings.click_replies and (round_number == 1 or round_number % 2 == 0):
                await self.click_more_replies()

            api_comments = self.interceptor.comments()
            dom_comments = await self.dom_extractor.extract(
                self.page,
                video_url=target.url,
                keyword=keyword,
                source_type="dom",
                search_rank=search_rank,
            )
            comments = merge_comment_groups(api_comments, dom_comments)
            before = len(records_by_id)
            for comment in comments:
                records_by_id.setdefault((comment.video_id, comment.comment_id), comment)

            current_count = len(records_by_id)
            self.logger.info(
                "comments_extracted",
                extra={
                    "video_id": target.video_id or extract_video_id(target.url),
                    "round": round_number,
                    "max_scrolls": self.settings.max_scrolls,
                    "unique_comments": current_count,
                    "api_payloads": len(self.interceptor.raw_payloads),
                },
            )
            if max_comments and current_count >= max_comments:
                break

            stale_rounds = stale_rounds + 1 if current_count == before else 0
            if stale_rounds >= self.settings.stagnant_rounds and current_count > 0:
                self.logger.info("crawl_stopped_stagnant", extra={"unique_comments": current_count})
                break

            # Try a quick aggressive close right before scrolling to avoid modal interruptions
            try:
                await self.captcha_handler.aggressive_close_login_container(self.page)
            except Exception:
                pass

            scroll_state = await self.scroll_engine.scroll_once(self.page)
            await self.captcha_handler.wait_if_needed(self.page)
            if scroll_state.get("at_bottom") and stale_rounds >= max(2, self.settings.stagnant_rounds // 2):
                self.logger.info("crawl_stopped_bottom", extra={"unique_comments": current_count})
                break

        comments = dedupe_comments(list(records_by_id.values()))
        if not comments:
            await self.write_debug_artifacts(target.url)
        # Stop the background login-closer if it was started
        try:
            await self._stop_login_closer()
        except Exception:
            pass
        return comments[:max_comments] if max_comments else comments

    async def search_video_urls(self, keyword: str, *, top_n: int = 10, search_scrolls: int = 8) -> list[str]:
        """Collect video URLs from TikTok search results."""

        search_url = f"https://www.tiktok.com/search?q={quote_plus(keyword)}"
        await self.open_url(search_url)
        collected: list[str] = []
        stable_rounds = 0

        for round_number in range(1, search_scrolls + 1):
            html = await self.page.content()
            urls = [normalize_tiktok_url(match) for match in VIDEO_URL_RE.findall(html)]
            for item in urls:
                if item not in collected:
                    collected.append(item)
            self.logger.info(
                "search_progress",
                extra={"keyword": keyword, "round": round_number, "video_urls": len(collected)},
            )
            if len(collected) >= top_n:
                break
            previous = len(collected)
            
            try:
                await self.captcha_handler.aggressive_close_login_container(self.page)
            except Exception:
                pass

            await self.scroll_engine.scroll_once(self.page)
            
            stable_rounds = stable_rounds + 1 if len(collected) == previous else 0
            if stable_rounds >= 3:
                break

        return collected[:top_n]

    async def crawl_search(
        self,
        keyword: str,
        *,
        top_n: int = 10,
        max_comments_per_video: int | None = None,
        search_scrolls: int = 8,
    ) -> list[Comment]:
        """Search TikTok and crawl comments from the top collected videos."""

        urls = await self.search_video_urls(keyword, top_n=top_n, search_scrolls=search_scrolls)
        all_comments: list[Comment] = []
        for rank, video_url in enumerate(urls, start=1):
            self.logger.info("search_video_crawl_started", extra={"rank": rank, "url": video_url})
            comments = await self.crawl_video(
                video_url,
                keyword=keyword,
                max_comments=max_comments_per_video,
                source_type="search",
                search_rank=rank,
            )
            all_comments.extend(comments)
        return dedupe_comments(all_comments)

    async def ensure_comments_visible(self) -> bool:
        """Open or focus the TikTok comments tab when the layout requires it."""

        if await self.has_comments_dom(timeout_ms=3_000):
            return True

        self.logger.info("comments_tab_lookup")
        candidates = self.page.locator("button, [role='button'], [role='tab'], div[tabindex], span")
        try:
            count = min(await candidates.count(), 250)
        except Exception:
            count = 0
        for index in range(count):
            element = candidates.nth(index)
            try:
                text = (await element.inner_text(timeout=500)).strip().lower()
                aria = (await element.get_attribute("aria-label") or "").strip().lower()
            except Exception:
                continue
            haystack = f"{text} {aria}"
            if not any(token in haystack for token in COMMENT_TAB_TEXTS):
                continue
            if len(text) > 80:
                continue
            try:
                await element.scroll_into_view_if_needed(timeout=1_000)
                # Close any login container quickly before clicking
                try:
                    await self.captcha_handler.aggressive_close_login_container(self.page)
                except Exception:
                    pass

                await element.click(timeout=2_000)
                await sleep_with_jitter(1.0)
                if await self.has_comments_dom(timeout_ms=4_000):
                    self.logger.info("comments_tab_opened")
                    return True
            except Exception:
                continue

        self.logger.warning("comments_tab_not_verified")
        return False

    async def has_comments_dom(self, timeout_ms: int = 2_000) -> bool:
        """Check whether visible comment nodes exist."""

        try:
            await self.page.locator(
                '[data-e2e^="comment-level-"], [data-e2e^="comment-username-"], div[data-comment-ui-enabled="true"]'
            ).first.wait_for(timeout=timeout_ms)
            return True
        except PlaywrightTimeoutError:
            return False

    async def click_more_replies(self) -> int:
        """Click visible reply expansion controls."""

        candidates = self.page.locator("button, [role='button'], span")
        clicked = 0
        try:
            count = min(await candidates.count(), 250)
        except Exception:
            return 0
        for index in range(count):
            element = candidates.nth(index)
            try:
                text = (await element.inner_text(timeout=300)).strip().lower()
            except Exception:
                continue
            if not text or not any(token in text for token in REPLY_BUTTON_TEXTS):
                continue
            if not re.search(r"\d|reply|replies|phản hồi|trả lời|tra loi|xem", text, re.I):
                continue
            try:
                await element.scroll_into_view_if_needed(timeout=1_000)
                await element.click(timeout=1_000)
                clicked += 1
                await sleep_with_jitter(0.45, jitter=0.15)
            except Exception:
                continue
        if clicked:
            self.logger.info("reply_controls_clicked", extra={"count": clicked})
        return clicked

    async def write_debug_artifacts(self, video_url: str) -> None:
        """Save HTML and screenshot when no comments are collected."""

        debug_dir = Path(self.settings.debug_dir)
        debug_dir.mkdir(parents=True, exist_ok=True)
        video_id = extract_video_id(video_url) or "unknown"
        html_path = debug_dir / f"{video_id}.html"
        screenshot_path = debug_dir / f"{video_id}.png"
        html_path.write_text(await self.page.content(), encoding="utf-8")
        await self.page.screenshot(path=str(screenshot_path), full_page=True)
        self.logger.warning(
            "debug_artifacts_saved",
            extra={"html_path": str(html_path), "screenshot_path": str(screenshot_path)},
        )

