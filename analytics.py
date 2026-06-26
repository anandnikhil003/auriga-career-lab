"""Analytics + weekly report. Standard library only.

Tracks per post: category, date, platform, post id, reach, impressions, likes,
comments, shares, engagement rate — stored in SQLite (post_metrics table).

  python analytics.py --today     # today's posts + metrics
  python analytics.py --week      # last 7 days
  python analytics.py --best      # top posts by engagement
  python analytics.py --refresh   # pull live metrics from Graph (needs token)
  python analytics.py --report    # write reports/weekly_report.txt

Offline / before --refresh, metrics show 0 (we never fabricate engagement).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

import config
import db

METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS post_metrics (
    post_id text NOT NULL,
    platform text NOT NULL,
    category text,
    date text,
    reach int DEFAULT 0,
    impressions int DEFAULT 0,
    likes int DEFAULT 0,
    comments int DEFAULT 0,
    shares int DEFAULT 0,
    engagement_rate real DEFAULT 0,
    updated_at text,
    PRIMARY KEY (post_id, platform)
);
"""


def _conn():
    c = db.connect()
    c.executescript(METRICS_SCHEMA)
    return c


def _posts(conn, since: str):
    """Posts (one row per platform actually published) since a date (ISO)."""
    rows = conn.execute(
        "SELECT category, program, posted_date, posted_facebook, facebook_post_id, "
        "facebook_post_time, posted_instagram, instagram_post_id, instagram_post_time "
        "FROM opportunities WHERE posted_date >= ? ORDER BY posted_date DESC", (since,)
    ).fetchall()
    out = []
    for r in rows:
        plats = []
        if r["posted_facebook"]:
            plats.append(("facebook", r["facebook_post_id"], r["facebook_post_time"]))
        if r["posted_instagram"]:
            plats.append(("instagram", r["instagram_post_id"], r["instagram_post_time"]))
        if not plats:
            plats.append(("pending", "", r["posted_date"]))
        for plat, pid, when in plats:
            out.append({"category": r["category"], "program": r["program"],
                        "platform": plat, "post_id": pid or "-",
                        "date": (when or r["posted_date"])[:10]})
    return out


def _metric(conn, post_id, platform):
    row = conn.execute("SELECT * FROM post_metrics WHERE post_id=? AND platform=?",
                       (post_id, platform)).fetchone()
    if not row:
        return dict(reach=0, impressions=0, likes=0, comments=0, shares=0, engagement_rate=0.0)
    return dict(row)


def _table(conn, posts, title):
    print(f"\n{title}  ({len(posts)} posts)")
    print(f"{'CAT':<13}{'PLATFORM':<10}{'PROGRAM':<30}{'REACH':>7}{'IMPR':>7}"
          f"{'LIKE':>6}{'CMNT':>6}{'SHR':>5}{'ENG%':>7}")
    print("-" * 96)
    if not posts:
        print("(no posts in range)")
        return
    for p in posts:
        m = _metric(conn, p["post_id"], p["platform"])
        print(f"{p['category']:<13}{p['platform']:<10}{p['program'][:28]:<30}"
              f"{m['reach']:>7}{m['impressions']:>7}{m['likes']:>6}{m['comments']:>6}"
              f"{m['shares']:>5}{m['engagement_rate']*100:>6.1f}%")


def cmd_today(conn):
    _table(conn, _posts(conn, config.TODAY.isoformat()), "TODAY")


def cmd_week(conn):
    since = (config.TODAY - timedelta(days=7)).isoformat()
    _table(conn, _posts(conn, since), "LAST 7 DAYS")


def cmd_best(conn):
    since = (config.TODAY - timedelta(days=30)).isoformat()
    posts = _posts(conn, since)
    ranked = sorted(posts, key=lambda p: _metric(conn, p["post_id"], p["platform"])["engagement_rate"],
                    reverse=True)[:10]
    _table(conn, ranked, "TOP POSTS (30d by engagement)")


def cmd_refresh(conn):
    """Pull live insights from Graph for published posts. Needs a valid token."""
    if config.DRY_RUN:
        print("DRY_RUN / no token — skipping live metric refresh.")
        return
    import json, urllib.request
    posts = [p for p in _posts(conn, (config.TODAY - timedelta(days=30)).isoformat())
             if p["platform"] in ("facebook", "instagram") and p["post_id"] != "-"]
    updated = 0
    for p in posts:
        try:
            if p["platform"] == "facebook":
                url = (f"https://graph.facebook.com/{config.GRAPH_VERSION}/{p['post_id']}"
                       f"?fields=insights.metric(post_impressions,post_impressions_unique),"
                       f"likes.summary(true),comments.summary(true),shares"
                       f"&access_token={config.FACEBOOK_ACCESS_TOKEN}")
            else:
                url = (f"https://graph.facebook.com/{config.GRAPH_VERSION}/{p['post_id']}"
                       f"/insights?metric=reach,impressions,likes,comments,shares"
                       f"&access_token={config.FACEBOOK_ACCESS_TOKEN}")
            with urllib.request.urlopen(url, timeout=config.HTTP_TIMEOUT) as r:
                data = json.loads(r.read().decode())
            m = _parse_insights(data)
            eng = (m["likes"] + m["comments"] + m["shares"]) / m["reach"] if m["reach"] else 0
            conn.execute(
                "INSERT INTO post_metrics(post_id,platform,category,date,reach,impressions,"
                "likes,comments,shares,engagement_rate,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(post_id,platform) DO UPDATE SET reach=excluded.reach,"
                "impressions=excluded.impressions,likes=excluded.likes,comments=excluded.comments,"
                "shares=excluded.shares,engagement_rate=excluded.engagement_rate,"
                "updated_at=excluded.updated_at",
                (p["post_id"], p["platform"], p["category"], p["date"], m["reach"],
                 m["impressions"], m["likes"], m["comments"], m["shares"], eng,
                 datetime.now().isoformat(timespec="seconds")))
            updated += 1
        except Exception as e:  # noqa: BLE001
            print(f"  refresh failed {p['platform']} {p['post_id']}: {str(e)[:60]}")
    conn.commit()
    print(f"refreshed {updated} posts")


def _parse_insights(data):
    m = dict(reach=0, impressions=0, likes=0, comments=0, shares=0)
    # tolerant: works for either FB or IG shapes
    for item in data.get("data", []):
        name = item.get("name", "")
        val = 0
        if item.get("values"):
            val = item["values"][0].get("value", 0)
        if "reach" in name: m["reach"] = val
        elif "impressions" in name: m["impressions"] = val
        elif name == "likes": m["likes"] = val
        elif name == "comments": m["comments"] = val
        elif name == "shares": m["shares"] = val
    if "likes" in data: m["likes"] = data["likes"].get("summary", {}).get("total_count", m["likes"])
    if "comments" in data: m["comments"] = data["comments"].get("summary", {}).get("total_count", m["comments"])
    return m


def _count_errors(logname: str, since: datetime) -> int:
    f = config.ROOT / "logs" / logname
    if not f.exists():
        return 0
    n = 0
    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "FAIL" in line or "ERROR" in line:
            n += 1
    return n


def cmd_report(conn):
    since = (config.TODAY - timedelta(days=7)).isoformat()
    posts = _posts(conn, since)
    s = db.stats(conn)
    from collections import Counter
    by_cat = Counter(p["category"] for p in posts)
    by_plat = Counter(p["platform"] for p in posts)
    ranked = sorted(posts, key=lambda p: _metric(conn, p["post_id"], p["platform"])["engagement_rate"],
                    reverse=True)[:5]
    # missed schedules: categories with no post today
    today_posts = {p["category"] for p in _posts(conn, config.TODAY.isoformat())}
    missed = [config.CATEGORIES[c] for c in config.CATEGORIES if c not in today_posts]

    lines = [
        "AURIGA CAREER LAB — WEEKLY REPORT",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}  ·  window {since} → {config.TODAY}",
        "=" * 60, "",
        f"Posts published (7d):        {len(posts)}",
        "",
        "Per-category counts:",
    ]
    for c in config.CATEGORIES:
        lines.append(f"  {config.CATEGORIES[c]:<14} {by_cat.get(c,0)}")
    lines += ["", "Platform breakdown:"]
    for plat, n in by_plat.most_common():
        lines.append(f"  {plat:<14} {n}")
    lines += ["", f"Remaining opportunities:     {s['remaining']} / {s['total']}",
              f"Published to Facebook (all):  {s['facebook']}",
              f"Published to Instagram (all): {s['instagram']}", "",
              "Top performing posts (by engagement):"]
    if ranked and any(_metric(conn, p['post_id'], p['platform'])['engagement_rate'] for p in ranked):
        for p in ranked:
            m = _metric(conn, p["post_id"], p["platform"])
            lines.append(f"  [{p['platform']}] {p['program'][:40]} — {m['engagement_rate']*100:.1f}%")
    else:
        lines.append("  (no engagement data yet — run `analytics.py --refresh` once live)")
    lines += ["", "Errors encountered (7d logs):",
              f"  facebook.log:  {_count_errors('facebook.log', since)}",
              f"  instagram.log: {_count_errors('instagram.log', since)}",
              f"  token.log:     {_count_errors('token.log', since)}", "",
              "Missed schedules today:",
              ("  " + ", ".join(missed)) if missed else "  none — all categories posted",
              ""]
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.REPORTS_DIR / "weekly_report.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")
    return str(out)


def main() -> int:
    conn = _conn()
    args = sys.argv[1:]
    if "--today" in args: cmd_today(conn)
    elif "--week" in args: cmd_week(conn)
    elif "--best" in args: cmd_best(conn)
    elif "--refresh" in args: cmd_refresh(conn)
    elif "--report" in args: cmd_report(conn)
    else:
        print("usage: analytics.py [--today|--week|--best|--refresh|--report]")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
