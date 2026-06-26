"""Build Facebook captions, link-comments, and per-category caption files.
Standard library only.
"""
from __future__ import annotations

import config
from models import Opportunity

_FLAGS = {
    "germany": "🇩🇪", "canada": "🇨🇦", "switzerland": "🇨🇭", "japan": "🇯🇵",
    "saudi arabia": "🇸🇦", "usa": "🇺🇸", "united states": "🇺🇸", "india": "🇮🇳",
    "israel": "🇮🇱", "south korea": "🇰🇷", "korea": "🇰🇷", "china": "🇨🇳",
    "türkiye": "🇹🇷", "turkey": "🇹🇷", "hungary": "🇭🇺", "italy": "🇮🇹",
    "brunei": "🇧🇳", "remote": "🌐",
}


def country_flag(country: str) -> str:
    c = (country or "").lower()
    for key, flag in _FLAGS.items():
        if key in c:
            return flag
    return "🌍"


def short_name(program: str) -> str:
    name = program.split(" — ")[0].split(" (")[0].strip()
    return name[:42]


def _cat_tag(category: str) -> str:
    return config.CATEGORIES.get(category, category).replace("/", "").replace(" ", "")


_HASHTAGS = {
    "stem": "#STEM #Research #Scholarships",
    "ug_research": "#Research #Undergrad #Scholarships",
    "ai_cs": "#AI #CS #Scholarships",
    "scholarships": "#Scholarships #StudyAbroad #FullyFunded",
    "conferences": "#Conferences #Travel #Scholarships",
}


def build_caption(category: str, opps: list[Opportunity], include_links: bool = True) -> str:
    """Caption with hyperlinks for ALL opportunities (one per line)."""
    label = config.CATEGORIES.get(category, category)
    lines = [f"🚀 {label} Opportunities", ""]
    for i, o in enumerate(opps, 1):
        lines.append(f"{i}. {short_name(o.program)} {o.official_url}")
    lines.append("")
    tags = _HASHTAGS.get(category, f"#{_cat_tag(category)} #Scholarships")
    lines.append(f"{tags} #AurigaCareerLab")
    return "\n".join(lines)


def build_links_comment(category: str, opps: list[Opportunity]) -> str:
    lines = ["🔗 Full details & official links:", ""]
    for i, o in enumerate(opps, 1):
        lines.append(f"{i}. {short_name(o.program)}")
        lines.append(f"   {o.official_url}")
    return "\n".join(lines)


def write_caption_file(category: str, opps: list[Opportunity]) -> str:
    """Write the link caption to BOTH posts/facebook/<cat>.txt and
    posts/instagram/<cat>.txt. Returns the facebook path."""
    caption = build_caption(category, opps)
    config.FACEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    config.INSTAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    fb = config.FACEBOOK_DIR / f"{category}.txt"
    ig = config.INSTAGRAM_DIR / f"{category}.txt"
    fb.write_text(caption + "\n", encoding="utf-8")
    ig.write_text(caption + "\n", encoding="utf-8")
    return str(fb)
