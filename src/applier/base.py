"""
Base Applier Class using Playwright.
Provides foundation for ATS auto-applying and form interaction.
"""

import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
from src.models import CandidateProfile, JobApplication, ApplicationStatus


class BaseApplier(ABC):
    """Abstract Base Class for job board and ATS appliers."""

    def __init__(
        self,
        profile: CandidateProfile,
        headless: bool = True,
        slow_mo_ms: int = 500,
        timeout_ms: int = 30000,
    ):
        self.profile = profile
        self.headless = headless
        self.slow_mo_ms = slow_mo_ms
        self.timeout_ms = timeout_ms

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Returns True if this applier supports the given job posting URL."""
        pass

    @abstractmethod
    def apply(self, url: str, dry_run: bool = True, **kwargs) -> Optional[JobApplication]:
        """
        Fills and submits (or dry-runs) the application for the given URL.
        Returns the recorded JobApplication on success, or None on failure.
        """
        pass

    def human_delay(self, seconds: float = 1.0) -> None:
        """Adds a natural human-like delay between form actions."""
        time.sleep(seconds)

    def verify_resume_exists(self) -> Path:
        """Checks that the resume file exists before attempting upload."""
        if not self.profile.resume_path:
            raise FileNotFoundError("Resume path is not specified in profile!")
        resume_file = Path(self.profile.resume_path)
        if not resume_file.exists():
            raise FileNotFoundError(f"Resume file not found at: {resume_file.resolve()}")
        return resume_file
