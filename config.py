"""Configuration. Standard library only (+ Pillow for cards). Reads optional .env."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


USER_AGENT = "AurigaOpportunities/3.0 (+https://auriga.test)"
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "20"))
STRICT_URL_CHECK = _bool("STRICT_URL_CHECK", False)

# Categories and labels.
CATEGORIES: dict[str, str] = {
    "stem": "STEM",
    "ug_research": "UG Research",
    "ai_cs": "AI/CS",
    "scholarships": "Scholarships",
    "conferences": "Conferences",
}

# Per-category posting hour (24h local). Drives scheduler + cron.
SCHEDULE: dict[str, int] = {
    "stem": 19,          # 7 PM
    "ug_research": 20,   # 8 PM
    "ai_cs": 21,         # 9 PM
    "scholarships": 22,  # 10 PM
    "conferences": 23,   # 11 PM
}

PER_CATEGORY = int(os.environ.get("PER_CATEGORY", "5"))
WEIGHTS = {"freshness": 0.20, "funding": 0.30, "prestige": 0.25, "undergrad": 0.25}

# ---- Facebook / Meta Graph API ----
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v20.0")
FACEBOOK_PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")
FACEBOOK_ACCESS_TOKEN = os.environ.get("FACEBOOK_ACCESS_TOKEN", "")
# DRY_RUN is forced True whenever credentials are missing (safe by default).
DRY_RUN = _bool("DRY_RUN", True) or not (FACEBOOK_PAGE_ID and FACEBOOK_ACCESS_TOKEN)
# Default mode: ask Graph to publish each post at its slot time (machine can be
# off afterward). Set False to publish immediately when you run `--slot <cat>`.
USE_GRAPH_SCHEDULING = _bool("USE_GRAPH_SCHEDULING", True)
FB_MAX_RETRIES = int(os.environ.get("FB_MAX_RETRIES", "3"))

# ---- Instagram (same Meta Graph token) ----
INSTAGRAM_BUSINESS_ID = os.environ.get("INSTAGRAM_BUSINESS_ID", "")
# Instagram requires a PUBLIC image URL. Serve posts/cards/ at this base.
IG_IMAGE_BASE_URL = os.environ.get("IG_IMAGE_BASE_URL", "").rstrip("/")
INSTAGRAM_DRY_RUN = _bool("DRY_RUN", True) or not (INSTAGRAM_BUSINESS_ID and FACEBOOK_ACCESS_TOKEN and IG_IMAGE_BASE_URL)

# Paths
SOURCES_FILE = ROOT / "sources" / "opportunities.json"
DB_PATH = Path(os.environ.get("AURIGA_DB", str(ROOT / "opportunities.db")))
FACEBOOK_DIR = ROOT / "posts" / "facebook"
INSTAGRAM_DIR = ROOT / "posts" / "instagram"
CARDS_DIR = ROOT / "posts" / "cards"
LOG_FILE = ROOT / "logs" / "run.log"
FB_LOG_FILE = ROOT / "logs" / "facebook.log"
IG_LOG_FILE = ROOT / "logs" / "instagram.log"
REPORTS_DIR = ROOT / "reports"
SITE_DIR = ROOT / "site"

# Fonts (Pillow). Falls back to default bitmap font if missing.
FONT_BOLD = os.environ.get("FONT_BOLD", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
FONT_REG = os.environ.get("FONT_REG", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")

TODAY = date.today()
