"""Excel export."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from models.comment import Comment
from storage.dataframe import comments_to_dataframe


def write_xlsx(comments: Sequence[Comment], path: Path, logger: logging.Logger | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    comments_to_dataframe(comments).to_excel(path, index=False)
    if logger:
        logger.info("export_completed", extra={"format": "xlsx", "path": str(path), "rows": len(comments)})
    return path

