"""Environment-driven settings for the crawler.

Values can be supplied through command-line flags or through a ``.env`` file.
The CLI passes explicit options into these settings, while defaults keep the
tool easy for students to run with minimal configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.constants import (
    DEFAULT_DEBUG_DIR,
    DEFAULT_LANGUAGE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PROFILE_DIR,
    DEFAULT_TIMEZONE,
)


class AppSettings(BaseSettings):
    """Runtime settings shared by browser, crawler, and export layers."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TIKTOK_",
        extra="ignore",
    )

    headless: bool = False
    browser_channel: str | None = None
    chrome_path: Path | None = None
    profile_dir: Path = DEFAULT_PROFILE_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    debug_dir: Path = DEFAULT_DEBUG_DIR
    language: str = DEFAULT_LANGUAGE
    timezone_id: str = DEFAULT_TIMEZONE
    captcha_timeout_seconds: int = Field(default=600, ge=30)
    page_timeout_ms: int = Field(default=45_000, ge=5_000)
    max_scrolls: int = Field(default=30, ge=1)
    scroll_steps: int = Field(default=5, ge=1)
    scroll_pixels: int = Field(default=900, ge=100)
    scroll_pause_seconds: float = Field(default=1.2, ge=0.1)
    stagnant_rounds: int = Field(default=8, ge=1)
    click_replies: bool = True
    emulation: Literal["desktop", "mobile"] = "desktop"
    log_level: str = "INFO"

    def model_post_init(self, __context: object) -> None:
        """Use the bundled classroom Chrome when it is present."""

        local_chrome = Path.cwd() / "chrome-win64" / "chrome.exe"
        if self.chrome_path is None and local_chrome.exists():
            self.chrome_path = local_chrome


def load_settings(**overrides: object) -> AppSettings:
    """Load settings and apply non-``None`` overrides from the CLI."""

    clean_overrides = {key: value for key, value in overrides.items() if value is not None}
    return AppSettings(**clean_overrides)
