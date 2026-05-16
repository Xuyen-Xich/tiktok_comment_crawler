"""Scrolling and lazy-loading support for TikTok comment panels."""

from __future__ import annotations

import logging
from typing import Any

from playwright.async_api import Page

from crawler.selectors import COMMENTS_CONTAINER_SELECTORS
from utils.time import sleep_with_jitter


class ScrollEngine:
    """Scroll the TikTok comments panel without blocking the event loop."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        scroll_steps: int,
        scroll_pixels: int,
        pause_seconds: float,
    ) -> None:
        self.logger = logger
        self.scroll_steps = scroll_steps
        self.scroll_pixels = scroll_pixels
        self.pause_seconds = pause_seconds

    async def scroll_once(self, page: Page) -> dict[str, Any]:
        """Scroll the best available comments container and return progress state."""

        state = await page.evaluate(
            """
            ({ selectors, steps, amount }) => {
                function visible(element) {
                    if (!element) return false;
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 20 && rect.height > 20 && style.visibility !== 'hidden' && style.display !== 'none';
                }
                function isScrollable(element) {
                    if (!visible(element)) return false;
                    const style = window.getComputedStyle(element);
                    const overflow = `${style.overflow} ${style.overflowY}`;
                    return element.scrollHeight > element.clientHeight + 80 && /(auto|scroll|overlay)/i.test(overflow);
                }
                function parentScrollables(node) {
                    const output = [];
                    let current = node;
                    while (current && current !== document.body && current !== document.documentElement) {
                        if (isScrollable(current)) output.push(current);
                        current = current.parentElement;
                    }
                    return output;
                }
                function commentCount() {
                    return document.querySelectorAll(
                        '[data-e2e^="comment-level-"], [data-e2e^="comment-username-"], div[data-comment-ui-enabled="true"]'
                    ).length;
                }

                const commentNode = document.querySelector('[data-e2e^="comment-level-"], [data-e2e^="comment-username-"], div[data-comment-ui-enabled="true"]');
                let scrollables = commentNode ? parentScrollables(commentNode) : [];
                for (const selector of selectors) {
                    document.querySelectorAll(selector).forEach((element) => {
                        if (isScrollable(element) && !scrollables.includes(element)) scrollables.push(element);
                    });
                }
                if (!scrollables.length) {
                    scrollables = Array.from(document.querySelectorAll('main, aside, section, div'))
                        .filter(isScrollable)
                        .sort((a, b) => b.scrollHeight - a.scrollHeight);
                }

                const target = scrollables[0] || null;
                const beforeTop = target ? target.scrollTop : window.scrollY;
                const beforeCount = commentCount();
                for (let index = 0; index < steps; index++) {
                    if (target) {
                        target.scrollTop = Math.min(target.scrollTop + amount, target.scrollHeight);
                        target.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: amount }));
                        target.dispatchEvent(new Event('scroll', { bubbles: true }));
                    } else {
                        window.scrollBy(0, amount);
                        window.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: amount }));
                        window.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }
                }
                const afterTop = target ? target.scrollTop : window.scrollY;
                const scrollHeight = target ? target.scrollHeight : document.documentElement.scrollHeight;
                const clientHeight = target ? target.clientHeight : window.innerHeight;
                return {
                    target_found: Boolean(target),
                    before_top: beforeTop,
                    after_top: afterTop,
                    moved: afterTop > beforeTop,
                    before_count: beforeCount,
                    after_count: commentCount(),
                    at_bottom: afterTop + clientHeight >= scrollHeight - 12,
                    scroll_height: scrollHeight,
                    client_height: clientHeight,
                };
            }
            """,
            {
                "selectors": COMMENTS_CONTAINER_SELECTORS,
                "steps": self.scroll_steps,
                "amount": self.scroll_pixels,
            },
        )
        await sleep_with_jitter(self.pause_seconds)
        self.logger.info("scrolling_progress", extra=state)
        return dict(state)

