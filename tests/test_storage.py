from pathlib import Path

from models.comment import Comment
from storage import export_comments
from storage.json_writer import read_json


def test_export_csv_and_json(tmp_path: Path) -> None:
    comments = [
        Comment(
            comment_id="c1",
            username="student",
            comment_text="Great",
            video_url="https://www.tiktok.com/@creator/video/1",
            video_id="1",
        )
    ]

    paths = export_comments(
        comments,
        output_dir=tmp_path,
        base_name="demo",
        formats=["csv", "json"],
    )

    assert tmp_path / "demo.csv" in paths
    assert tmp_path / "demo.json" in paths
    assert (tmp_path / "demo.csv").exists()
    loaded = read_json(tmp_path / "demo.json")
    assert loaded[0].comment_id == "c1"

