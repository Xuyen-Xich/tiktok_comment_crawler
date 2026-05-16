"""DOM extraction fallback for rendered TikTok pages."""

from __future__ import annotations

import logging

from playwright.async_api import Page

from crawler.parser import CommentParser
from models.comment import Comment
from utils.text import extract_creator_handle, extract_video_id
from utils.time import utc_now_iso


class DomExtractor:
    """Extract comments from the live DOM, then fall back to HTML parsing."""

    def __init__(self, parser: CommentParser, logger: logging.Logger) -> None:
        self.parser = parser
        self.logger = logger

    async def extract(
        self,
        page: Page,
        *,
        video_url: str,
        keyword: str = "",
        source_type: str = "dom",
        search_rank: int | None = None,
    ) -> list[Comment]:
        """Return comments from the currently rendered page."""

        live_rows = await self._extract_live_rows(page, video_url, keyword, search_rank)
        if live_rows:
            comments = [Comment(**row) for row in live_rows]
            self.logger.info("comments_extracted", extra={"source": "dom", "count": len(comments)})
            return comments

        html = await page.content()
        comments = self.parser.parse_html(
            html,
            video_url=video_url,
            keyword=keyword,
            source_type=source_type,
            search_rank=search_rank,
        )
        self.logger.info("comments_extracted", extra={"source": "html", "count": len(comments)})
        return comments

    async def _extract_live_rows(
        self,
        page: Page,
        video_url: str,
        keyword: str,
        search_rank: int | None,
    ) -> list[dict[str, object]]:
        script = """
        ({ videoUrl, videoId, keyword, searchRank, scrapedAt, creatorHandle }) => {
            function clean(value) {
                return (value || '').replace(/\\s+/g, ' ').trim();
            }
            function closestCommentBlock(node) {
                let current = node;
                for (let depth = 0; current && depth < 10; depth++) {
                    const hasProfile = Boolean(current.querySelector && current.querySelector('a[href*="/@"]'));
                    const hasText = Boolean(current.querySelector && current.querySelector('[data-e2e^="comment-level-"]'));
                    const hasMeta = Boolean(current.querySelector && (
                        current.querySelector('[data-e2e^="comment-time-"]') ||
                        current.querySelector('[data-e2e="comment-like-count"]')
                    ));
                    if (hasProfile && hasText && hasMeta) return current;
                    current = current.parentElement;
                }
                return node.closest('div[data-comment-ui-enabled="true"], div[class*="CommentItem"], div[class*="DivComment"], div[id]') || node.parentElement;
            }
            function pickText(root, selectors) {
                for (const selector of selectors) {
                    const element = root ? root.querySelector(selector) : null;
                    const text = clean(element ? element.innerText || element.textContent : '');
                    if (text) return text;
                }
                return '';
            }
            function pickHref(root) {
                const element = root ? root.querySelector('a[href*="/@"]') : null;
                if (!element) return '';
                const href = element.href || element.getAttribute('href') || '';
                return href.startsWith('/') ? `https://www.tiktok.com${href}` : href;
            }
            function fallbackId(parts) {
                const raw = parts.filter(Boolean).join('|');
                let hash = 0;
                for (let i = 0; i < raw.length; i++) {
                    hash = ((hash << 5) - hash) + raw.charCodeAt(i);
                    hash |= 0;
                }
                return `dom_${Math.abs(hash).toString(16)}`;
            }

            const nodes = Array.from(document.querySelectorAll(
                '[data-e2e^="comment-level-"], p[class*="comment"], span[class*="comment"]'
            ));
            const rows = [];
            const seen = new Set();
            for (const textNode of nodes) {
                const commentText = clean(textNode.innerText || textNode.textContent);
                if (!commentText) continue;
                const block = closestCommentBlock(textNode);
                if (!block) continue;
                let username = pickText(block, [
                    '[data-e2e^="comment-username-"]',
                    'a[href*="/@"] span',
                    'a[href*="/@"]'
                ]).split('·')[0].trim();
                const createdTime = pickText(block, [
                    '[data-e2e^="comment-time-"]',
                    'time',
                    'span[class*="time"]'
                ]);
                const likeCount = pickText(block, [
                    '[data-e2e="comment-like-count"]',
                    '[class*="LikeCount"]',
                    '[class*="like-count"]'
                ]);
                const dataE2e = clean(textNode.getAttribute('data-e2e'));
                const className = clean(block.className);
                const isReply = /level-2|reply|Reply|SubComment|subcomment/.test(`${dataE2e} ${className}`);
                const rawId = clean(block.id || block.getAttribute('data-id'));
                const commentId = rawId || fallbackId([videoId, username, commentText, createdTime, dataE2e]);
                if (seen.has(commentId)) continue;
                seen.add(commentId);
                rows.push({
                    comment_id: commentId,
                    username: username,
                    user_url: pickHref(block),
                    comment_text: commentText,
                    like_count: likeCount,
                    created_time: createdTime,
                    video_url: videoUrl,
                    video_id: videoId,
                    creator_handle: creatorHandle,
                    keyword: keyword,
                    scraped_at: scrapedAt,
                    parent_comment_id: '',
                    is_reply: isReply,
                    source_type: 'dom',
                    search_rank: searchRank,
                });
            }
            return rows;
        }
        """
        try:
            rows = await page.evaluate(
                script,
                {
                    "videoUrl": video_url,
                    "videoId": extract_video_id(video_url),
                    "keyword": keyword,
                    "searchRank": search_rank,
                    "scrapedAt": utc_now_iso(),
                    "creatorHandle": extract_creator_handle(video_url),
                },
            )
        except Exception as exc:
            self.logger.debug("dom_extraction_failed", extra={"error": str(exc)})
            return []
        return rows if isinstance(rows, list) else []

