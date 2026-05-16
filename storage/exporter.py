"""Export dispatcher independent from crawler code."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from models.comment import Comment
from storage.csv_writer import write_csv
from storage.excel_writer import write_xlsx
from storage.json_writer import write_json
from storage.parquet_writer import write_parquet
from storage.sqlite_writer import write_sqlite

ExportFormat = Literal["csv", "json", "xlsx", "parquet", "sqlite", "all"]


def export_comments(
    comments: Sequence[Comment],
    *,
    output_dir: Path,
    base_name: str,
    formats: Sequence[ExportFormat],
    logger: logging.Logger | None = None,
) -> list[Path]:
    """Export comments to one or more classroom-friendly formats."""

    selected = ["csv", "json", "xlsx", "parquet"] if "all" in formats else list(formats)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for fmt in selected:
        path = output_dir / f"{base_name}.{fmt if fmt != 'sqlite' else 'db'}"
        if fmt == "csv":
            paths.append(write_csv(comments, path, logger))
        elif fmt == "json":
            paths.append(write_json(comments, path, logger))
        elif fmt == "xlsx":
            paths.append(write_xlsx(comments, path, logger))
        elif fmt == "parquet":
            paths.append(write_parquet(comments, path, logger))
        elif fmt == "sqlite":
            paths.append(write_sqlite(comments, path, logger))
        else:
            raise ValueError(f"Unsupported export format: {fmt}")
    return paths

