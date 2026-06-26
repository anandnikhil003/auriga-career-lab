"""Collect opportunities. Standard library only.

Backbone = a curated, categorized source file (sources/opportunities.json) of real,
fully-funded STEM/undergrad programs with OFFICIAL urls, each checked live by
verify.py. Optional RSS augmentation is best-effort and never crashes collection.
"""
from __future__ import annotations

import json
import urllib.request
import xml.etree.ElementTree as ET

import config
from models import Opportunity


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def load_seed() -> list[Opportunity]:
    data = json.loads(config.SOURCES_FILE.read_text(encoding="utf-8"))
    opps: list[Opportunity] = []
    for it in data.get("opportunities", []):
        opps.append(Opportunity(
            program=it["program"],
            organization=it.get("organization", ""),
            country=it.get("country", ""),
            official_url=it["official_url"],
            category=it.get("category", "stem"),
            funding=it.get("funding", ""),
            eligibility=it.get("eligibility", ""),
            description=it.get("description", ""),
            deadline_raw=it.get("deadline_raw") or "",
            is_funded=bool(it.get("is_funded", True)),
            undergrad_eligible=bool(it.get("undergrad_eligible", True)),
            tier=int(it.get("tier", 2)),
            source=it.get("source", "seed"),
        ))
    return opps


def from_rss(url: str, organization: str, category: str) -> list[Opportunity]:
    try:
        root = ET.fromstring(_get(url))
    except Exception:
        return []
    out: list[Opportunity] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            out.append(Opportunity(program=title, organization=organization,
                                   country="", official_url=link, category=category,
                                   source="rss"))
    return out


def collect() -> list[Opportunity]:
    return load_seed()


# ───────────────────────── SELF-REFILLING SOURCES ──────────────────────────
# Append-only refill. Pulls RSS/Atom from provider feeds, keeps only UNSEEN +
# live URLs, scores them, and APPENDS to sources/opportunities.json. Never
# deletes existing entries. Replace/extend feeds with working ones per provider.
import json as _json
from datetime import date as _date

REFILL_FEEDS = [
    ("stem", "DAAD", "https://www.daad.de/en/rss/"),
    ("stem", "Mitacs", "https://www.mitacs.ca/feed/"),
    ("stem", "CERN", "https://home.cern/api/news/news/feed.rss"),
    ("ug_research", "ETH Zurich", "https://ethz.ch/en/news-and-events/eth-news.rss.html"),
    ("ug_research", "EPFL", "https://actu.epfl.ch/feeds/rss/all/en/"),
    ("stem", "KAUST", "https://www.kaust.edu.sa/en/rss"),
    ("stem", "OIST", "https://www.oist.jp/news-center/rss.xml"),
    ("ai_cs", "Google Summer of Code", "https://summerofcode.withgoogle.com/feed"),
    ("ai_cs", "MLH", "https://mlh.io/blog.rss"),
    ("scholarships", "Scholarship Positions", "https://scholarship-positions.com/feed/"),
    ("ug_research", "Opportunity Desk", "https://opportunitydesk.org/category/research/feed/"),
]


def _existing_urls() -> set:
    from models import canonical_url
    data = _json.loads(config.SOURCES_FILE.read_text(encoding="utf-8"))
    return {canonical_url(o["official_url"]) for o in data.get("opportunities", [])}


def refill(fetcher=None, url_check=None, max_per_feed: int = 10) -> dict:
    """Add only unseen, live opportunities to opportunities.json. Append-only.

    fetcher(url)->xml  and  url_check(url)->'ok'|'dead'|'unknown' are injectable
    for testing. Returns {'added','skipped_seen','skipped_dead'}.
    """
    import verify
    import scoring
    from models import Opportunity, canonical_url

    fetcher = fetcher or _get
    url_check = url_check or verify.url_status

    data = _json.loads(config.SOURCES_FILE.read_text(encoding="utf-8"))
    seen = {canonical_url(o["official_url"]) for o in data.get("opportunities", [])}
    added = skipped_seen = skipped_dead = 0

    for category, org, feed in REFILL_FEEDS:
        try:
            items = from_rss(feed, org, category)  # uses fetcher via _get; best-effort
        except Exception:
            items = []
        # if a custom fetcher is supplied (tests), parse it directly
        if fetcher is not _get:
            try:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(fetcher(feed))
                items = []
                for it in root.iter("item"):
                    t = (it.findtext("title") or "").strip()
                    l = (it.findtext("link") or "").strip()
                    if t and l:
                        items.append(Opportunity(program=t, organization=org, country="",
                                                 official_url=l, category=category, source="refill"))
            except Exception:
                items = []

        for opp in items[:max_per_feed]:
            cu = canonical_url(opp.official_url)
            if cu in seen:
                skipped_seen += 1
                continue
            status = url_check(opp.official_url)
            if status == "dead":
                skipped_dead += 1
                continue
            seen.add(cu)
            opp.first_seen = _date.today().isoformat()
            opp.is_funded = True
            opp.undergrad_eligible = True
            opp.url_status = status
            scoring.score(opp)
            data["opportunities"].append({
                "program": opp.program, "organization": org, "country": "",
                "official_url": opp.official_url, "category": category,
                "funding": "", "eligibility": "", "deadline_raw": None,
                "is_funded": True, "undergrad_eligible": True, "tier": 2,
                "source": f"refill:{org}",
                "scores": opp.scores, "score": opp.score,
            })
            added += 1

    if added:
        config.SOURCES_FILE.write_text(_json.dumps(data, indent=2, ensure_ascii=False),
                                       encoding="utf-8")
    return {"added": added, "skipped_seen": skipped_seen, "skipped_dead": skipped_dead}


if __name__ == "__main__":
    import sys
    if "--refill" in sys.argv:
        print(refill())
    else:
        opps = collect()
        print(f"{len(opps)} opportunities in catalog")
