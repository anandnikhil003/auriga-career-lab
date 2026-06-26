"""Domain model. Standard library only."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from urllib.parse import urlparse, urlunparse


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except Exception:
        return url.strip().lower()
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower() or "https", host, path, "", "", ""))


def parse_deadline(value) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except Exception:
        return None


@dataclass
class Opportunity:
    program: str
    organization: str
    country: str
    official_url: str
    category: str = "stem"
    funding: str = ""
    eligibility: str = ""
    description: str = ""
    deadline_raw: str = ""
    is_funded: bool = True
    undergrad_eligible: bool = True
    tier: int = 2                    # 1=top, 2=strong, 3=good -> prestige
    source: str = ""
    # runtime / persisted:
    deadline: Optional[date] = None
    url_status: str = "unknown"      # ok | dead | unknown
    verified: bool = False
    reject_reason: str = ""
    first_seen: Optional[str] = None  # ISO date string from DB
    scores: dict = field(default_factory=dict)
    score: float = 0.0

    def __post_init__(self) -> None:
        self.deadline = parse_deadline(self.deadline_raw)

    @property
    def fingerprint(self) -> str:
        base = f"{self.program.strip().lower()}|{canonical_url(self.official_url)}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]

    @property
    def deadline_display(self) -> str:
        if self.deadline:
            return self.deadline.isoformat()
        return self.deadline_raw or "Rolling — check official page"
