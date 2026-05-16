"""Playwright network interception for TikTok comment APIs."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from playwright.async_api import Page, Response

from crawler.parser import CommentParser
from models.comment import Comment, dedupe_comments

COMMENT_ENDPOINT_MARKERS = (
    "/comment/list",
    "/comment/list/reply",
    "comment/list",
    "comment/list/reply",
    "aweme/v1/comment",
)


class TikTokApiInterceptor:
    """Capture and normalize TikTok comment JSON responses."""

    def __init__(
        self,
        parser: CommentParser,
        logger: logging.Logger,
        *,
        video_url: str = "",
        keyword: str = "",
        search_rank: int | None = None,
    ) -> None:
        self.parser = parser
        self.logger = logger
        self.video_url = video_url
        self.keyword = keyword
        self.search_rank = search_rank
        self.raw_payloads: list[dict[str, Any]] = []
        self._comments: list[Comment] = []
        self._attached = False

    def configure_context(self, *, video_url: str, keyword: str = "", search_rank: int | None = None) -> None:
        """Update metadata used when normalizing intercepted responses."""

        self.video_url = video_url
        self.keyword = keyword
        self.search_rank = search_rank

    def attach(self, page: Page) -> None:
        """Attach a response listener to a Playwright page."""

        if self._attached:
            return
        page.on("response", lambda response: asyncio.create_task(self._handle_response(response)))
        self._attached = True

    def comments(self) -> list[Comment]:
        return dedupe_comments(self._comments)

    def clear(self) -> None:
        self.raw_payloads.clear()
        self._comments.clear()

    async def _handle_response(self, response: Response) -> None:
        url = response.url.lower()
        if not any(marker in url for marker in COMMENT_ENDPOINT_MARKERS):
            return
        try:
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and response.status >= 400:
                return
            payload = await response.json()
        except Exception as exc:
            self.logger.debug("api_intercept_skipped", extra={"url": response.url, "error": str(exc)})
            return

        if not isinstance(payload, dict):
            return
        self.raw_payloads.append(payload)
        parsed = self.parser.parse_api_payload(
            payload,
            video_url=self.video_url,
            keyword=self.keyword,
            search_rank=self.search_rank,
        )
        self._comments.extend(parsed)
        self._comments = dedupe_comments(self._comments)
        self.logger.info(
            "api_intercepted",
            extra={"url": response.url, "comments_seen": len(self._comments), "payloads": len(self.raw_payloads)},
        )

