"""Parsers that normalize API and HTML/DOM data into Comment models."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Sequence
from typing import Any

from bs4 import BeautifulSoup, Tag

from config.constants import TIKTOK_HOME
from crawler.selectors import COMMENT_BLOCK_SELECTORS, COMMENT_TEXT_SELECTORS, LIKE_SELECTORS, TIME_SELECTORS, USERNAME_SELECTORS
from models.comment import Comment, dedupe_comments
from utils.text import clean_text, extract_creator_handle, extract_video_id, normalize_tiktok_url, stable_id
from utils.time import utc_now_iso


class CommentParser:
    """Normalize TikTok API payloads and HTML into one comment schema."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger(__name__)

    def parse_api_payload(
        self,
        payload: dict[str, Any],
        *,
        video_url: str,
        keyword: str = "",
        search_rank: int | None = None,
    ) -> list[Comment]:
        """Parse TikTok comment API JSON.

        TikTok has several response shapes. This parser accepts common keys and
        recursively looks for nested reply lists.
        """

        comments: list[Comment] = []
        video_id = extract_video_id(video_url)
        creator_handle = extract_creator_handle(video_url)

        for raw in self._iter_comment_dicts(payload):
            comment = self._comment_from_api_dict(
                raw,
                video_url=video_url,
                video_id=video_id,
                creator_handle=creator_handle,
                keyword=keyword,
                search_rank=search_rank,
            )
            if comment:
                comments.append(comment)
            for reply in self._iter_reply_dicts(raw):
                reply_comment = self._comment_from_api_dict(
                    reply,
                    video_url=video_url,
                    video_id=video_id,
                    creator_handle=creator_handle,
                    keyword=keyword,
                    search_rank=search_rank,
                    parent_comment_id=comment.comment_id if comment else clean_text(raw.get("cid")),
                    is_reply=True,
                )
                if reply_comment:
                    comments.append(reply_comment)

        return dedupe_comments(comments)

    def parse_html(
        self,
        html: str,
        *,
        video_url: str,
        keyword: str = "",
        source_type: str = "html",
        search_rank: int | None = None,
    ) -> list[Comment]:
        """Parse comments from a rendered HTML snapshot."""

        soup = BeautifulSoup(html, "html.parser")
        video_id = extract_video_id(video_url)
        creator_handle = extract_creator_handle(video_url)
        scraped_at = utc_now_iso()
        comments: list[Comment] = []
        seen_blocks: set[str] = set()
        parent_stack: list[str] = []

        for selector in COMMENT_BLOCK_SELECTORS:
            for block in soup.select(selector):
                marker = clean_text(block.get("id")) or stable_id(_get_text(block)[:300])
                if marker in seen_blocks:
                    continue
                seen_blocks.add(marker)
                comment_text = _get_text(_first_select(block, COMMENT_TEXT_SELECTORS))
                username_node = _first_select(block, USERNAME_SELECTORS)
                username = _get_text(username_node).split("·")[0].strip()
                if not comment_text and not username:
                    continue

                is_reply = _detect_reply(block)
                parent_comment_id = parent_stack[-1] if is_reply and parent_stack else ""
                comment_id = clean_text(block.get("id")) or clean_text(block.get("data-id"))
                comment_id = comment_id or stable_id(video_id, username, comment_text, parent_comment_id)
                if not is_reply:
                    parent_stack.append(comment_id)
                    parent_stack = parent_stack[-20:]

                comments.append(
                    Comment(
                        comment_id=comment_id,
                        username=username,
                        user_url=_extract_user_url(block),
                        comment_text=comment_text,
                        like_count=_get_text(_first_select(block, LIKE_SELECTORS)),
                        created_time=_get_text(_first_select(block, TIME_SELECTORS)),
                        video_url=video_url,
                        video_id=video_id,
                        creator_handle=creator_handle,
                        keyword=keyword,
                        scraped_at=scraped_at,
                        parent_comment_id=parent_comment_id,
                        is_reply=is_reply,
                        source_type=source_type,  # type: ignore[arg-type]
                        search_rank=search_rank,
                    )
                )
        return dedupe_comments(comments)

    def _iter_comment_dicts(self, payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
        candidates = payload.get("comments") or payload.get("comment_list") or payload.get("data")
        if isinstance(candidates, dict):
            candidates = candidates.get("comments") or candidates.get("comment_list") or candidates.get("list")
        if isinstance(candidates, list):
            for item in candidates:
                if isinstance(item, dict):
                    yield item

    def _iter_reply_dicts(self, raw: dict[str, Any]) -> Iterable[dict[str, Any]]:
        for key in ("reply_comment", "reply_comments", "replies", "comment_reply"):
            value = raw.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item

    def _comment_from_api_dict(
        self,
        raw: dict[str, Any],
        *,
        video_url: str,
        video_id: str,
        creator_handle: str,
        keyword: str,
        search_rank: int | None,
        parent_comment_id: str = "",
        is_reply: bool | None = None,
    ) -> Comment | None:
        text = clean_text(raw.get("text") or raw.get("comment_text") or raw.get("content"))
        user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
        username = clean_text(
            user.get("unique_id")
            or user.get("nickname")
            or raw.get("username")
            or raw.get("user_name")
        )
        comment_id = clean_text(raw.get("cid") or raw.get("comment_id") or raw.get("id"))
        if not comment_id:
            comment_id = stable_id(video_id, username, text, raw.get("create_time"), parent_comment_id)
        if not text and not username:
            return None

        user_url = ""
        if username:
            user_url = f"{TIKTOK_HOME}/@{username.lstrip('@')}"
        created_time = clean_text(raw.get("create_time") or raw.get("created_time") or raw.get("date"))
        reply_flag = bool(parent_comment_id) if is_reply is None else is_reply
        return Comment(
            comment_id=comment_id,
            username=username,
            user_url=user_url,
            comment_text=text,
            like_count=raw.get("digg_count") or raw.get("like_count"),
            created_time=created_time,
            video_url=video_url,
            video_id=video_id,
            creator_handle=creator_handle,
            keyword=keyword,
            parent_comment_id=parent_comment_id or clean_text(raw.get("reply_id") or raw.get("reply_to_comment_id")),
            is_reply=reply_flag,
            source_type="api",
            search_rank=search_rank,
        )


def merge_comment_groups(*groups: Sequence[Comment]) -> list[Comment]:
    """Merge API and DOM comments, preferring richer records."""

    merged: dict[tuple[str, str], Comment] = {}
    for group in groups:
        for comment in group:
            key = (comment.video_id, comment.comment_id)
            existing = merged.get(key)
            if existing is None:
                merged[key] = comment
                continue
            if comment.source_type == "api" and existing.source_type != "api":
                merged[key] = comment
            elif len(comment.comment_text) > len(existing.comment_text):
                merged[key] = comment
    return list(merged.values())


def _first_select(root: Tag, selectors: Sequence[str]) -> Tag | None:
    for selector in selectors:
        found = root.select_one(selector)
        if found is not None:
            return found
    return None


def _get_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return clean_text(node.get_text(" ", strip=True))


def _extract_user_url(block: Tag) -> str:
    link = block.select_one('a[href*="/@"]')
    if not link:
        return ""
    href = clean_text(link.get("href"))
    if not href:
        return ""
    if href.startswith("/"):
        href = TIKTOK_HOME + href
    return normalize_tiktok_url(href)


def _detect_reply(block: Tag) -> bool:
    data_e2e_values = " ".join(clean_text(tag.get("data-e2e")) for tag in block.select("[data-e2e]"))
    class_values = " ".join(block.get("class", []))
    style = clean_text(block.get("style"))
    haystack = f"{data_e2e_values} {class_values} {style}"
    return bool(re.search(r"comment-level-2|reply|subcomment|margin-left|padding-left", haystack, re.I))

