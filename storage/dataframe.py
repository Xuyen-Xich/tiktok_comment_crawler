"""Shared pandas conversion helpers."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from models.comment import Comment


def comments_to_dataframe(comments: Sequence[Comment]) -> pd.DataFrame:
    """Convert comments to a stable-column DataFrame."""

    columns = list(Comment.model_fields.keys())
    if not comments:
        return pd.DataFrame(columns=columns)
    rows = [comment.model_dump(mode="json") for comment in comments]
    return pd.DataFrame(rows).reindex(columns=columns).drop_duplicates(
        subset=["video_id", "comment_id"],
        keep="first",
    )

