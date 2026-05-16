"""Persistent browser profile helpers."""

from __future__ import annotations

import logging
from pathlib import Path


class SessionManager:
    """Prepare and describe persistent Playwright browser profiles."""

    def __init__(self, profile_dir: Path, logger: logging.Logger) -> None:
        self.profile_dir = profile_dir
        self.logger = logger

    def prepare_profile(self) -> Path:
        """Create the profile directory if it does not exist."""

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info("profile_loaded", extra={"profile_dir": str(self.profile_dir)})
        return self.profile_dir

