"""Verification + dedup. Standard library only.

Checks per opportunity:
  1. URL liveness  -> ok (2xx/3xx) | dead (4xx/5xx) | unknown (network error)
  2. Deadline      -> reject if a concrete deadline is in the past
  3. Fully funded  -> must be flagged funded
  4. Undergrad     -> must be undergraduate-eligible

Policy: a 'dead' URL is ALWAYS rejected. An 'unknown' (network/proxy failure,
not the link's fault) is kept unless STRICT_URL_CHECK=true. This keeps the tool
reliable behind proxies while still doing strict checks on a normal network.
"""
from __future__ import annotations

import urllib.error
import urllib.request

import config
from models import Opportunity


def url_status(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
            return "ok" if r.status < 400 else "dead"
    except urllib.error.HTTPError as e:
        # Some sites block HEAD/bots with 403/405 but are alive; treat those as unknown.
        if e.code in (401, 403, 405, 429):
            return "unknown"
        return "dead"
    except Exception:
        return "unknown"  # DNS/timeout/proxy -> environment issue, not a dead link


def verify_one(opp: Opportunity) -> bool:
    if not opp.is_funded:
        opp.reject_reason = "not fully funded"
        return False
    if not opp.undergrad_eligible:
        opp.reject_reason = "not undergraduate-eligible"
        return False
    if opp.deadline and opp.deadline < config.TODAY:
        opp.reject_reason = f"deadline passed ({opp.deadline})"
        return False

    opp.url_status = url_status(opp.official_url)
    if opp.url_status == "dead":
        opp.reject_reason = "official url is dead (4xx/5xx)"
        return False
    if opp.url_status == "unknown" and config.STRICT_URL_CHECK:
        opp.reject_reason = "url unreachable and STRICT_URL_CHECK=true"
        return False

    opp.verified = True
    return True


def dedupe(opps: list[Opportunity]) -> list[Opportunity]:
    seen: set[str] = set()
    out: list[Opportunity] = []
    for o in opps:
        if o.fingerprint in seen:
            continue
        seen.add(o.fingerprint)
        out.append(o)
    return out


def verify_all(opps: list[Opportunity]) -> list[Opportunity]:
    return [o for o in dedupe(opps) if verify_one(o)]
