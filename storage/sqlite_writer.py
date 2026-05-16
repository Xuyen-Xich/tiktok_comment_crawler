"""SQLite export for future classroom analytics exercises."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from pathlib import Path

from models.comment import Comment
from storage.dataframe import comments_to_dataframe


def write_sqlite(
    comments: Sequence[Comment],
    path: Path,
    logger: logging.Logger | None = None,
    table_name: str = "comments",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        comments_to_dataframe(comments).to_sql(table_name, connection, if_exists="replace", index=False)
    if logger:
        logger.info("export_completed", extra={"format": "sqlite", "path": str(path), "rows": len(comments)})
    return path

