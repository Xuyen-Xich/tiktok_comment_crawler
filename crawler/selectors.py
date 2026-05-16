"""Selector fallbacks for TikTok's frequently changing interface."""

COMMENTS_CONTAINER_SELECTORS = [
    'div[data-e2e="comment-list"]',
    'div[data-e2e="comments-list"]',
    'div[class*="DivCommentListContainer"]',
    'div[class*="CommentList"]',
    'div[class*="DivCommentContainer"]',
    'section[class*="comment"]',
    'div[data-comment-ui-enabled="true"]',
]

COMMENT_BLOCK_SELECTORS = [
    'div[data-comment-ui-enabled="true"]',
    'div[id][class*="CommentItem"]',
    'div[class*="DivCommentItemContainer"]',
    'div[class*="CommentItemContainer"]',
    'div[class*="DivCommentContentContainer"]',
]

COMMENT_TEXT_SELECTORS = [
    'p[data-e2e^="comment-level-"]',
    'span[data-e2e^="comment-level-"]',
    '[data-e2e^="comment-level-"]',
    '[data-e2e="comment-text"]',
    'p[class*="comment"]',
]

USERNAME_SELECTORS = [
    '[data-e2e^="comment-username-"]',
    'a[href*="/@"] span',
    'a[href*="/@"]',
]

TIME_SELECTORS = [
    '[data-e2e^="comment-time-"]',
    'span[class*="time"]',
    'time',
]

LIKE_SELECTORS = [
    '[data-e2e="comment-like-count"]',
    '[class*="like-count"]',
    '[class*="LikeCount"]',
]

COMMENT_TAB_TEXTS = ("comments", "comment", "bình luận", "binh luan")

REPLY_BUTTON_TEXTS = (
    "view",
    "more replies",
    "reply",
    "replies",
    "xem",
    "phản hồi",
    "trả lời",
)

