"""Small lexicon sentiment helper for classroom demos.

This is intentionally simple. Production sentiment analysis can later replace
this module with a Thai/English model or an LLM-based classifier.
"""

from __future__ import annotations

from analytics.preprocessing import normalize_comment_text

POSITIVE_WORDS = {
    "amazing",
    "best",
    "good",
    "great",
    "love",
    "nice",
    "perfect",
    "ชอบ",
    "ดี",
    "เยี่ยม",
}

NEGATIVE_WORDS = {
    "bad",
    "fake",
    "hate",
    "poor",
    "scam",
    "worst",
    "แย่",
    "โกง",
}


def score_sentiment(text: str) -> float:
    """Return a simple sentiment score between -1 and 1."""

    words = normalize_comment_text(text).split()
    if not words:
        return 0.0
    positive = sum(1 for word in words if word in POSITIVE_WORDS)
    negative = sum(1 for word in words if word in NEGATIVE_WORDS)
    return (positive - negative) / max(1, positive + negative)


def label_sentiment(text: str) -> str:
    """Return ``positive``, ``neutral``, or ``negative``."""

    score = score_sentiment(text)
    if score > 0.05:
        return "positive"
    if score < -0.05:
        return "negative"
    return "neutral"

