"""Video target model."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from utils.text import extract_creator_handle, extract_video_id, normalize_tiktok_url


class VideoTarget(BaseModel):
    """A TikTok video plus classroom metadata such as keyword/search rank."""

    model_config = ConfigDict(str_strip_whitespace=True)

    url: str
    keyword: str = ""
    source_type: str = "post"
    search_rank: int | None = None
    video_id: str = Field(default="")
    creator_handle: str = Field(default="")

    def model_post_init(self, __context: object) -> None:
        self.url = normalize_tiktok_url(self.url)
        self.video_id = self.video_id or extract_video_id(self.url)
        self.creator_handle = self.creator_handle or extract_creator_handle(self.url)

