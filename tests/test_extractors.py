from utils.text import extract_creator_handle, extract_video_id, normalize_tiktok_url, parse_social_count


def test_tiktok_url_helpers() -> None:
    url = normalize_tiktok_url("https://www.tiktok.com/@demo/video/123?q=test#comments")
    assert url == "https://www.tiktok.com/@demo/video/123"
    assert extract_video_id(url) == "123"
    assert extract_creator_handle(url) == "demo"


def test_parse_social_count() -> None:
    assert parse_social_count("1.5K") == 1500
    assert parse_social_count("2M") == 2_000_000
    assert parse_social_count("likes") is None

