"""Auriga Opportunities — daily Facebook Page auto-publisher (official Graph API).

Usage:
  python main.py               # generate 5 cards+captions, schedule all to FB
  python main.py --slot ai_cs  # publish ONE category immediately (per-slot cron)
  python main.py --status      # today's posts, FB ids, success/failure, remaining, DB size

Default (6 PM run): generate everything and Graph-schedule each category at its
slot (7-11 PM). If no FACEBOOK_* token is set, runs in DRY_RUN and prints
"Would post <CAT> at <time>" + the exact Graph payload — nothing is sent.

Standard library only, plus Pillow for the 1080x1080 image cards.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

import cards
import config
import db
import facebook_publisher as fb
import instagram_publisher
import scheduler
import scoring
import scrapers
import scan_test
import site_export
import token_check
import verify
import writer
from models import Opportunity


def log(msg: str) -> None:
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with config.LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def select(conn, category: str) -> list[Opportunity]:
    unposted = set(db.unposted_by_category(conn, category))
    pool = [o for o in scrapers.collect()
            if o.category == category and o.fingerprint in unposted]
    chosen: list[Opportunity] = []
    for opp in pool:
        if not verify.verify_one(opp):
            db.update_url_status(conn, opp.fingerprint, opp.url_status)
            log(f"  [{category}] dropped: {opp.program[:36]} -> {opp.reject_reason}")
            continue
        db.update_url_status(conn, opp.fingerprint, opp.url_status)
        opp.first_seen = db.get_first_seen(conn, opp.fingerprint)
        scoring.score(opp)
        chosen.append(opp)
    chosen.sort(key=lambda o: o.score, reverse=True)
    return chosen[: config.PER_CATEGORY]


def handle_category(conn, category: str, immediate: bool, publish: bool = True) -> dict:
    opps = select(conn, category)
    if not opps:
        log(f"  [{category}] no unposted opportunities left — add more to sources/")
        return {"category": category, "status": "empty", "post_id": None}
    paths = cards.render_category_cards(category, opps)   # cover + 5 slides
    cap = writer.write_caption_file(category, opps)
    log(f"  [{category}] {len(opps)} picks | slides={len(paths)} | caption={cap}")
    if not publish:
        return {"category": category, "status": "preview", "slides": len(paths),
                "post_id": None}
    fb_res = fb.publish_category(conn, category, opps, immediate=immediate)
    ig_res = instagram_publisher.publish_category(conn, category, opps)  # same slides, additive
    return {"category": category, "status": fb_res.get("status"),
            "facebook": fb_res, "instagram": ig_res,
            "post_id": fb_res.get("post_id")}


def refresh_catalog(conn) -> None:
    for opp in scrapers.collect():
        db.upsert_catalog(conn, opp)
    conn.commit()


def cmd_status(conn) -> int:
    print(scheduler.schedule_text())
    rows = db.todays_facebook_posts(conn)
    print(f"\nToday's posts ({config.TODAY.isoformat()}):")
    if not rows:
        print("  (none generated yet today — run `python main.py`)")
    seen = {}
    for r in rows:
        seen.setdefault(r["category"], r)
    for cat in config.CATEGORIES:
        r = seen.get(cat)
        if not r:
            print(f"  {scheduler.slot_label(cat):>5}  {config.CATEGORIES[cat]:<13} not generated")
            continue
        ok = "✅ success" if r["posted_facebook"] else ("DRY_RUN" if config.DRY_RUN else "⏳ pending")
        pid = r["facebook_post_id"] or "-"
        print(f"  {scheduler.slot_label(cat):>5}  {config.CATEGORIES[cat]:<13} "
              f"{ok:<10} post_id={pid}")
    s = db.stats(conn)
    size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
    print(f"\nOpportunities remaining (unposted): {s['remaining']} / {s['total']}")
    print(f"Published to Facebook (all time):   {s['facebook']}")
    print(f"Published to Instagram (all time):  {s['instagram']}")
    print(f"Database size:                      {size/1024:.1f} KB ({config.DB_PATH})")
    print(f"Mode:                               {'DRY_RUN' if config.DRY_RUN else 'LIVE'}")
    # --- v3.1 observability (additive): token status + last successful publish ---
    tk = token_check.verify()
    print(f"Meta token status:                  {'PASS' if tk['passed'] else 'FAIL'} ({tk.get('mode','')})")
    row = conn.execute("SELECT MAX(facebook_post_time) t FROM opportunities "
                       "WHERE posted_facebook=1").fetchone()
    print(f"Last successful publish:            {row['t'] if row and row['t'] else 'never'}")
    return 0



def _category_counts(conn) -> dict:
    rows = conn.execute(
        "SELECT category, COUNT(*) total, "
        "SUM(CASE WHEN posted_date IS NOT NULL THEN 1 ELSE 0 END) posted "
        "FROM opportunities GROUP BY category").fetchall()
    out = {}
    for r in rows:
        total = r["total"]; posted = r["posted"] or 0
        out[r["category"]] = (total, posted, total - posted)
    return out


def _print_inventory(conn) -> None:
    counts = _category_counts(conn)
    print(f"\n{'CATEGORY':<14}{'TOTAL':>8}{'POSTED':>9}{'REMAINING':>12}")
    print("-" * 43)
    for cat in config.CATEGORIES:
        t, p, r = counts.get(cat, (0, 0, 0))
        flag = "  <-- LOW" if r < 20 else ""
        print(f"{config.CATEGORIES[cat]:<14}{t:>8}{p:>9}{r:>12}{flag}")


def cmd_refill(conn) -> int:
    log("=== refill start ===")
    before = db.stats(conn)["total"]
    res = scrapers.refill()                 # scrape -> verify -> score -> append unseen
    refresh_catalog(conn)                   # load any new entries into the DB catalog
    conn.commit()
    after = db.stats(conn)["total"]
    log(f"refill: +{res['added']} added, {res['skipped_seen']} already seen, "
        f"{res['skipped_dead']} dead (catalog {before} -> {after})")
    _print_inventory(conn)
    return 0


def maybe_auto_refill(conn) -> None:
    counts = _category_counts(conn)
    low = [c for c, (t, p, r) in counts.items() if r < 20]
    if low:
        log("AUTO REFILL TRIGGERED — low inventory: " + ", ".join(low))
        res = scrapers.refill()
        refresh_catalog(conn)
        conn.commit()
        log(f"auto-refill added {res['added']} new opportunities")


def cmd_preflight(conn) -> int:
    checks = []
    # Database
    try:
        conn.execute("SELECT COUNT(*) FROM opportunities").fetchone()
        checks.append(("Database", "PASS", "sqlite reachable"))
    except Exception as e:  # noqa: BLE001
        checks.append(("Database", "FAIL", str(e)[:40]))
    # Cards (Pillow + QR encoder)
    try:
        import cards as _c
        _c.qr_matrix("https://example.org/preflight")
        from PIL import Image  # noqa
        checks.append(("Cards", "PASS", "Pillow + QR ok"))
    except Exception as e:  # noqa: BLE001
        checks.append(("Cards", "FAIL", str(e)[:40]))
    # Captions
    try:
        writer.build_caption("ai_cs", [])
        checks.append(("Captions", "PASS", "writer ok"))
    except Exception as e:  # noqa: BLE001
        checks.append(("Captions", "FAIL", str(e)[:40]))
    # Token / Page / Instagram
    tk = token_check.verify()
    if not config.FACEBOOK_ACCESS_TOKEN:
        checks.append(("Token", "DRY", "no token (dev mode)"))
        checks.append(("Page", "DRY", "set FACEBOOK_PAGE_ID"))
    else:
        checks.append(("Token", "PASS" if tk["valid"] else "FAIL", tk.get("mode", "")))
        checks.append(("Page", "PASS" if tk["page_match"] else "FAIL",
                       tk.get("page_name", "") or "page not matched"))
    if config.INSTAGRAM_BUSINESS_ID and config.IG_IMAGE_BASE_URL:
        checks.append(("Instagram", "PASS", "id + image base set"))
    else:
        checks.append(("Instagram", "DRY", "set INSTAGRAM_BUSINESS_ID + IG_IMAGE_BASE_URL"))
    # Scheduler
    sched_ok = all(c in config.SCHEDULE for c in config.CATEGORIES)
    checks.append(("Scheduler", "PASS" if sched_ok else "FAIL",
                   "5 slots 7-11 PM" if sched_ok else "missing slots"))

    print(f"\n{'CHECK':<12}{'STATUS':<8}DETAIL")
    print("-" * 52)
    icon = {"PASS": "✅", "FAIL": "❌", "DRY": "⚪"}
    for name, status, detail in checks:
        print(f"{name:<12}{icon.get(status,'')} {status:<5}{detail}")
    failed = any(st == "FAIL" for _, st, _ in checks)
    print("\nRESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


def cmd_dashboard(conn) -> int:
    s = db.stats(conn)
    counts = _category_counts(conn)
    low = [config.CATEGORIES[c] for c, (t, p, r) in counts.items() if r < 20]
    today = db.todays_facebook_posts(conn)
    scheduled_today = len({r["category"] for r in today})
    fb_last = conn.execute("SELECT MAX(facebook_post_time) t FROM opportunities "
                           "WHERE posted_facebook=1").fetchone()["t"]
    ig_last = conn.execute("SELECT MAX(instagram_post_time) t FROM opportunities "
                           "WHERE posted_instagram=1").fetchone()["t"]
    size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
    print("┌─ Auriga Daily Dashboard " + "─" * 30 + "┐")
    print(f"  Total opportunities       : {s['total']}")
    print(f"  Remaining (unposted)      : {s['remaining']}")
    print(f"  Today's scheduled posts   : {scheduled_today} / {len(config.CATEGORIES)} categories")
    print(f"  Last successful FB post   : {fb_last or 'never'}")
    print(f"  Last successful IG post   : {ig_last or 'never'}")
    print(f"  Database size             : {size/1024:.1f} KB")
    print(f"  Categories low (<20 left) : {', '.join(low) if low else 'none'}")
    print("└" + "─" * 55 + "┘")
    return 0


def cmd_export_site(conn) -> int:
    res = site_export.export()
    print(f"Exported {res['images_copied']} images -> {res['site_dir']}")
    print(f"Open {res['index']} or deploy the site/ folder to GitHub/Cloudflare Pages.")
    print(f"Then set IG_IMAGE_BASE_URL to the deployed base URL "
          f"(currently: {config.IG_IMAGE_BASE_URL or 'unset'}).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=list(config.CATEGORIES), help="publish one category now")
    ap.add_argument("--status", action="store_true", help="show today's status")
    ap.add_argument("--preview", action="store_true", help="generate cards+captions only, no publishing")
    ap.add_argument("--refill", action="store_true", help="scrape+verify+score and append unseen opportunities")
    ap.add_argument("--schedule", action="store_true", help="generate all + create Meta scheduled posts (7-11 PM)")
    ap.add_argument("--preflight", action="store_true", help="deployment readiness PASS/FAIL table")
    ap.add_argument("--dashboard", action="store_true", help="daily operations dashboard")
    ap.add_argument("--export-site", dest="export_site", action="store_true", help="build deployable site/ for image hosting")
    ap.add_argument("--scan-test", dest="scan_test", action="store_true", help="decode every QR and verify it matches its URL")
    args = ap.parse_args()

    conn = db.connect()
    if args.status:
        rc = cmd_status(conn); conn.close(); return rc
    if args.preflight:
        rc = cmd_preflight(conn); conn.close(); return rc
    if args.dashboard:
        rc = cmd_dashboard(conn); conn.close(); return rc
    if args.export_site:
        rc = cmd_export_site(conn); conn.close(); return rc
    if args.scan_test:
        conn.close(); return scan_test.run()
    if args.refill:
        rc = cmd_refill(conn); conn.close(); return rc

    # --schedule forces Graph native scheduling (computer can be off afterward)
    if args.schedule:
        config.USE_GRAPH_SCHEDULING = True
        log("--schedule: Facebook posts use Graph scheduled_publish_time "
            "(computer can be off). Instagram has NO native scheduling — IG "
            "carousels publish immediately or via Meta Business Suite.")

    # v3.1: token configured but FAILS preflight -> auto-switch to DRY_RUN
    # (keep generating cards/captions instead of failing to post).
    if not config.DRY_RUN and not args.preview:
        _tk = token_check.verify()
        if not _tk["passed"]:
            config.DRY_RUN = True
            log("token preflight FAILED -> auto DRY_RUN: " + "; ".join(_tk["reasons"]))
    log("=== run start ===  mode=" + ("DRY_RUN" if config.DRY_RUN else "LIVE"))
    refresh_catalog(conn)
    if not args.preview:
        maybe_auto_refill(conn)   # GOAL 2: top up any category under 20

    cats = [args.slot] if args.slot else list(config.CATEGORIES)
    results = []
    for cat in cats:
        log(f"category: {cat} ({config.CATEGORIES[cat]})")
        results.append(handle_category(conn, cat, immediate=bool(args.slot),
                                       publish=not args.preview))
    conn.commit()

    ok = sum(r["status"] in ("ok", "dry_run", "preview") for r in results)
    log(f"done: {ok}/{len(results)} categories processed | {db.stats(conn)}")
    log("=== run ok ===")

    print("\n" + scheduler.schedule_text())
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
