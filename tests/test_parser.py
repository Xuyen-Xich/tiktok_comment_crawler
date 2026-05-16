from crawler.parser import CommentParser


def test_parse_api_payload_comments_and_replies() -> None:
    parser = CommentParser()
    payload = {
        "comments": [
            {
                "cid": "c1",
                "text": "Love this product",
                "digg_count": 12,
                "create_time": "1710000000",
                "user": {"unique_id": "brandfan"},
                "reply_comment": [
                    {
                        "cid": "r1",
                        "text": "Same here",
                        "digg_count": "2",
                        "user": {"unique_id": "student"},
                    }
                ],
            }
        ]
    }

    comments = parser.parse_api_payload(
        payload,
        video_url="https://www.tiktok.com/@creator/video/1234567890",
        keyword="skincare",
    )

    assert len(comments) == 2
    assert comments[0].comment_id == "c1"
    assert comments[0].video_id == "1234567890"
    assert comments[0].creator_handle == "creator"
    assert comments[1].is_reply is True
    assert comments[1].parent_comment_id == "c1"


def test_parse_html_with_selector_fallbacks() -> None:
    parser = CommentParser()
    html = """
    <div data-comment-ui-enabled="true" id="abc">
      <a href="/@user1"><span>user1</span></a>
      <p data-e2e="comment-level-1">Great launch!</p>
      <span data-e2e="comment-like-count">1.2K</span>
      <span data-e2e="comment-time-1">2d ago</span>
    </div>
    """

    comments = parser.parse_html(
        html,
        video_url="https://www.tiktok.com/@creator/video/999",
        keyword="campaign",
    )

    assert len(comments) == 1
    assert comments[0].comment_id == "abc"
    assert comments[0].username == "user1"
    assert comments[0].like_count == 1200
    assert comments[0].user_url == "https://www.tiktok.com/@user1"

