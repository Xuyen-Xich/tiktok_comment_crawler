"""Project-wide constants.

Keeping these values in one small module makes classroom demos easier: students
can see the defaults without reading the crawler internals.
"""

from __future__ import annotations

from pathlib import Path

APP_NAME = "tiktok-social-listening"
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_PROFILE_DIR = Path("profiles") / "default"
DEFAULT_DEBUG_DIR = Path("output") / "debug"
DEFAULT_LANGUAGE = "en-US"
DEFAULT_TIMEZONE = "Asia/Bangkok"

TIKTOK_HOME = "https://www.tiktok.com"

DESKTOP_VIEWPORT = {"width": 1366, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

