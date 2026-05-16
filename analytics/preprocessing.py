"""Text cleaning helpers for social listening analytics."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from utils.text import clean_text

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "you",
    "คือ",
    "ที่",
    "และ",
}


def normalize_comment_text(text: str) -> str:
    """Lowercase text and remove URLs while keeping readable words."""

    text = re.sub(r"https?://\S+", " ", clean_text(text).lower())
    text = re.sub(r"[^\w\s#@ก-๙]", " ", text, flags=re.UNICODE)
    return clean_text(text)


def top_keywords(texts: Iterable[str], limit: int = 20) -> list[tuple[str, int]]:
    """Return simple word-frequency keywords for classroom exploration."""

    counter: Counter[str] = Counter()
    for text in texts:
        words = [word for word in normalize_comment_text(text).split() if len(word) > 2 and word not in STOPWORDS]
        counter.update(words)
    return counter.most_common(limit)

