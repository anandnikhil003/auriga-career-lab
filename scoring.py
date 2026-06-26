"""Four-factor scoring -> single rank score in [0,1]. Deterministic, no network.

  freshness : urgency by deadline if known, else recency since first_seen
              (newer in DB = fresher; decays the longer it sits unposted).
  funding   : funded + richness of the funding description (stipend/housing/travel).
  prestige  : from curated tier (1>2>3).
  undergrad : how explicitly undergraduate-eligible the wording is.
"""
from __future__ import annotations

from datetime import date

import config
from models import Opportunity

_RICH = ("stipend", "salary", "housing", "accommodation", "travel", "airfare",
         "tuition", "allowance", "insurance", "lodging")
_UG_STRONG = ("undergraduate", "undergrad", "first & second-year", "first-year",
              "second-year", "sophomore", "3rd year", "final-year", "final year")


def _freshness(opp: Opportunity) -> float:
    if opp.deadline:
        days = (opp.deadline - config.TODAY).days
        if days < 0:
            return 0.0
        if days <= 30:
            return 1.0
        if days <= 90:
            return 0.8
        return 0.6
    # no deadline: use recency since first_seen (decay 0.03/day from 1.0, floor 0.5)
    if opp.first_seen:
        try:
            age = (config.TODAY - date.fromisoformat(opp.first_seen)).days
            return max(0.5, 1.0 - 0.03 * max(0, age))
        except Exception:
            pass
    return 0.7


def _funding(opp: Opportunity) -> float:
    if not opp.is_funded:
        return 0.0
    hits = sum(1 for w in _RICH if w in (opp.funding or "").lower())
    return min(1.0, 0.6 + 0.1 * hits)


def _prestige(opp: Opportunity) -> float:
    return {1: 1.0, 2: 0.8, 3: 0.6}.get(opp.tier, 0.7)


def _undergrad(opp: Opportunity) -> float:
    if not opp.undergrad_eligible:
        return 0.0
    text = (opp.eligibility or "").lower()
    if any(w in text for w in _UG_STRONG):
        return 1.0
    if "student" in text:
        return 0.75
    return 0.6


def score(opp: Opportunity) -> float:
    parts = {
        "freshness": _freshness(opp),
        "funding": _funding(opp),
        "prestige": _prestige(opp),
        "undergrad": _undergrad(opp),
    }
    opp.scores = {k: round(v, 2) for k, v in parts.items()}
    opp.score = round(sum(config.WEIGHTS[k] * v for k, v in parts.items()), 4)
    return opp.score
