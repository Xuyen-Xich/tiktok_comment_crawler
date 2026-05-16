"""Text and URL normalization helpers."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse, urlunparse

VIDEO_ID_RE = re.compile(r"/video/(\d+)")
HANDLE_RE = re.compile(r"tiktok\.com/@([^/]+)/video/")
VIDEO_URL_RE = re.compile(r"https?://(?:www\.)?tiktok\.com/@[^\"'<>\s]+/video/\d+")


def clean_text(value: object | None) -> str:
    """Normalize whitespace and convert missing values to an empty string."""

    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def stable_id(*parts: object) -> str:
    """Create a stable short hash for comments missing platform IDs."""

    raw = "|".join(clean_text(part) for part in parts if clean_text(part))
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def normalize_tiktok_url(url: str) -> str:
    """Remove query strings and fragments from TikTok URLs."""

    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc or "www.tiktok.com"
    clean = parsed._replace(scheme=scheme, netloc=netloc, query="", fragment="")
    return urlunparse(clean)


def extract_video_id(video_url: str) -> str:
    match = VIDEO_ID_RE.search(video_url)
    return match.group(1) if match else ""


def extract_creator_handle(video_url: str) -> str:
    match = HANDLE_RE.search(video_url)
    return match.group(1) if match else ""


def parse_social_count(value: object | None) -> int | None:
    """Convert TikTok display counts such as ``1.2K`` into integers."""

    text = clean_text(value).replace(",", "")
    if not text or text.lower() in {"like", "likes", "thích"}:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)([kmb])?", text, re.I)
    if not match:
        return None
    number = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suffix, 1)
    return int(number * multiplier)


def safe_filename(value: str) -> str:
    """Return a Windows-safe filename stem."""

    name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_")
    return name[:120] or "tiktok_comments"

