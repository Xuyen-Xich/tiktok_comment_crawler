"""JSON export."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

from models.comment import Comment


def write_json(comments: Sequence[Comment], path: Path, logger: logging.Logger | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [comment.model_dump(mode="json") for comment in comments]
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if logger:
        logger.info("export_completed", extra={"format": "json", "path": str(path), "rows": len(comments)})
    return path


def read_json(path: Path) -> list[Comment]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [Comment(**row) for row in rows]

