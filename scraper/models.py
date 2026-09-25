"""Shared data structures."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class JobPosting:
    """A single scraped job posting."""

    company: str            # e.g. "infineon"
    company_display: str    # e.g. "Infineon Technologies"
    title: str
    url: str
    location: str = ""
    scraped_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def job_id(self) -> str:
        """
        Stable unique ID for dedup purposes.

        Built from company + URL (not title, since titles can be edited
        without it being a "new" job) so the same posting is recognized
        across runs even if scraped_at changes.
        """
        raw = f"{self.company}:{self.url}".strip().lower()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def matches_keywords(self, keywords: list[str]) -> bool:
        if not keywords:
            return True
        haystack = f"{self.title} {self.location}".lower()
        return any(kw.strip().lower() in haystack for kw in keywords if kw.strip())
