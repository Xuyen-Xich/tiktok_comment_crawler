"""Comment data model used by every extraction and export path."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from utils.text import clean_text, parse_social_count
from utils.time import utc_now_iso

CommentSource = Literal["api", "dom", "html"]


class Comment(BaseModel):
    """A normalized TikTok comment or reply."""

    model_config = ConfigDict(str_strip_whitespace=True)

    comment_id: str
    username: str = ""
    user_url: str = ""
    comment_text: str = ""
    like_count: int | None = None
    created_time: str = ""
    video_url: str = ""
    video_id: str = ""
    creator_handle: str = ""
    keyword: str = ""
    scraped_at: str = Field(default_factory=utc_now_iso)
    parent_comment_id: str = ""
    is_reply: bool = False
    source_type: CommentSource = "dom"
    search_rank: int | None = None

    @field_validator("comment_id", "username", "user_url", "comment_text", "created_time", "video_url", "video_id", "creator_handle", "keyword", "parent_comment_id", mode="before")
    @classmethod
    def normalize_strings(cls, value: object) -> str:
        return clean_text(value)

    @field_validator("like_count", mode="before")
    @classmethod
    def normalize_like_count(cls, value: object) -> int | None:
        if isinstance(value, int):
            return value
        return parse_social_count(value)


def dedupe_comments(comments: list[Comment]) -> list[Comment]:
    """Deduplicate comments while preserving first-seen order."""

    output: list[Comment] = []
    seen: set[tuple[str, str]] = set()
    for comment in comments:
        key = (comment.video_id, comment.comment_id)
        if key in seen:
            continue
        seen.add(key)
        output.append(comment)
    return output

