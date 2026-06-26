"""SQLite persistence. Standard library only.

Catalog + dedup. An opportunity is posted at most once, ever (posted_date set
when chosen for a category file; posted_facebook=1 once it reaches Facebook).
"""
from __future__ import annotations

import sqlite3
from typing import Optional

import config
from models import Opportunity

SCHEMA = """
CREATE TABLE IF NOT EXISTS opportunities (
    fingerprint   TEXT PRIMARY KEY,
    program       TEXT NOT NULL,
    organization  TEXT,
    country       TEXT,
    official_url  TEXT NOT NULL,
    category      TEXT NOT NULL,
    funding       TEXT,
    eligibility   TEXT,
    deadline_raw  TEXT,
    is_funded     INTEGER DEFAULT 1,
    undergrad     INTEGER DEFAULT 1,
    tier          INTEGER DEFAULT 2,
    source        TEXT,
    first_seen    TEXT NOT NULL,
    url_status    TEXT DEFAULT 'unknown',
    score         REAL DEFAULT 0,
    posted_date   TEXT
);
CREATE INDEX IF NOT EXISTS idx_cat_posted ON opportunities (category, posted_date);
"""

# Columns added in v3 (Facebook). Applied idempotently via _migrate().
_FB_COLUMNS = {
    "posted_facebook": "INTEGER DEFAULT 0",
    "facebook_post_id": "TEXT",
    "facebook_post_time": "TEXT",
    # v3.2 Instagram (separate from Facebook tracking):
    "posted_instagram": "INTEGER DEFAULT 0",
    "instagram_post_id": "TEXT",
    "instagram_post_time": "TEXT",
}


def _migrate(conn: sqlite3.Connection) -> None:
    have = {r["name"] for r in conn.execute("PRAGMA table_info(opportunities)")}
    for col, ddl in _FB_COLUMNS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE opportunities ADD COLUMN {col} {ddl}")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def upsert_catalog(conn: sqlite3.Connection, opp: Opportunity) -> None:
    conn.execute(
        """INSERT INTO opportunities
           (fingerprint, program, organization, country, official_url, category,
            funding, eligibility, deadline_raw, is_funded, undergrad, tier, source,
            first_seen, url_status, score)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(fingerprint) DO UPDATE SET
             program=excluded.program, organization=excluded.organization,
             country=excluded.country, official_url=excluded.official_url,
             category=excluded.category, funding=excluded.funding,
             eligibility=excluded.eligibility, deadline_raw=excluded.deadline_raw,
             is_funded=excluded.is_funded, undergrad=excluded.undergrad,
             tier=excluded.tier, source=excluded.source
        """,
        (opp.fingerprint, opp.program, opp.organization, opp.country, opp.official_url,
         opp.category, opp.funding, opp.eligibility, opp.deadline_raw or "",
         int(opp.is_funded), int(opp.undergrad_eligible), opp.tier, opp.source,
         config.TODAY.isoformat(), opp.url_status, opp.score),
    )


def get_first_seen(conn, fingerprint: str) -> Optional[str]:
    row = conn.execute("SELECT first_seen FROM opportunities WHERE fingerprint=?",
                       (fingerprint,)).fetchone()
    return row["first_seen"] if row else None


def unposted_by_category(conn, category: str) -> list[str]:
    rows = conn.execute(
        "SELECT fingerprint FROM opportunities WHERE category=? AND posted_date IS NULL",
        (category,)).fetchall()
    return [r["fingerprint"] for r in rows]


def mark_posted(conn, fingerprint: str, score: float) -> None:
    conn.execute("UPDATE opportunities SET posted_date=?, score=? WHERE fingerprint=?",
                 (config.TODAY.isoformat(), score, fingerprint))


def mark_facebook(conn, fingerprint: str, post_id: str, post_time: str) -> None:
    conn.execute(
        "UPDATE opportunities SET posted_facebook=1, facebook_post_id=?, "
        "facebook_post_time=? WHERE fingerprint=?", (post_id, post_time, fingerprint))


def mark_instagram(conn, fingerprint: str, post_id: str, post_time: str) -> None:
    conn.execute(
        "UPDATE opportunities SET posted_instagram=1, instagram_post_id=?, "
        "instagram_post_time=? WHERE fingerprint=?", (post_id, post_time, fingerprint))


def update_url_status(conn, fingerprint: str, status: str) -> None:
    conn.execute("UPDATE opportunities SET url_status=? WHERE fingerprint=?",
                 (status, fingerprint))


def todays_facebook_posts(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT category, program, country, facebook_post_id, facebook_post_time, "
        "posted_facebook FROM opportunities WHERE posted_date=? ORDER BY category",
        (config.TODAY.isoformat(),)).fetchall()


def stats(conn) -> dict:
    total = conn.execute("SELECT COUNT(*) c FROM opportunities").fetchone()["c"]
    posted = conn.execute("SELECT COUNT(*) c FROM opportunities WHERE posted_date IS NOT NULL"
                          ).fetchone()["c"]
    fb = conn.execute("SELECT COUNT(*) c FROM opportunities WHERE posted_facebook=1"
                      ).fetchone()["c"]
    ig = conn.execute("SELECT COUNT(*) c FROM opportunities WHERE posted_instagram=1"
                      ).fetchone()["c"]
    return {"total": total, "posted": posted, "remaining": total - posted,
            "facebook": fb, "instagram": ig}
