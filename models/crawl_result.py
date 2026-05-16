"""Crawl result model."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from models.comment import Comment
from utils.time import utc_now_iso


class CrawlResult(BaseModel):
    """The outcome of one crawl command."""

    comments: list[Comment] = Field(default_factory=list)
    started_at: str = Field(default_factory=utc_now_iso)
    finished_at: str | None = None
    output_files: list[Path] = Field(default_factory=list)

    @property
    def total_comments(self) -> int:
        return len(self.comments)

