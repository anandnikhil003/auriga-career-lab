"""Publish a category's card + caption to a Facebook Page via the Graph API.

Two modes (chosen by config.USE_GRAPH_SCHEDULING):
  - scheduling: upload as unpublished with scheduled_publish_time -> Graph
    publishes it at the slot time. Links go in the caption (can't comment on an
    unpublished post). One run schedules all 5; machine can be off afterward.
  - immediate:  publish now, then add the links as the first comment.

DRY_RUN (auto when no token): prints "Would post <CAT> at <time>" + the exact
Graph payload JSON, and writes nothing to Facebook.
"""
from __future__ import annotations

import json
from datetime import datetime

import cards
import config
import db
import meta_api
import scheduler
import writer
from models import Opportunity


def _fb_log(msg: str) -> None:
    config.FB_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with config.FB_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def _slide_paths(category: str) -> list[str]:
    d = config.CARDS_DIR / category
    if not d.exists():
        return []
    return [str(p) for p in sorted(d.glob("*.png"), key=lambda x: x.name)]


def publish_category(conn, category: str, opps: list[Opportunity],
                     immediate: bool = False) -> dict:
    """Publish a multi-image CAROUSEL (cover + 5 opportunity slides) to the Page
    via the official Graph API: each slide is uploaded as an unpublished photo,
    then a single feed post references them via attached_media."""
    label = config.CATEGORIES.get(category, category)
    slides = [str(config.CARDS_DIR / category / f) for f in cards.slide_filenames(opps)]
    slot = scheduler.slot_label(category)

    use_schedule = config.USE_GRAPH_SCHEDULING and not immediate
    sched_time = None
    if use_schedule:
        epoch, ok, reason = scheduler.slot_epoch(category)
        if ok:
            sched_time = epoch
        else:
            _fb_log(f"{category}: scheduling skipped ({reason}); publishing immediately")

    caption = writer.build_caption(category, opps)

    # ----- DRY RUN (behavior unchanged: print + advance ledger, send nothing) -----
    if config.DRY_RUN:
        payload = {
            "step1_upload_each_slide_unpublished": [
                {"endpoint": f"/{config.FACEBOOK_PAGE_ID or '<PAGE_ID>'}/photos",
                 "source": s, "published": "false"} for s in slides],
            "step2_feed_carousel": {
                "endpoint": f"/{config.FACEBOOK_PAGE_ID or '<PAGE_ID>'}/feed",
                "message": caption[:120] + ("..." if len(caption) > 120 else ""),
                "attached_media": "[{media_fbid: <id> } x %d]" % len(slides),
                **({"scheduled_publish_time": sched_time, "published": "false"} if sched_time else {})},
        }
        print(f"  Would post {label} CAROUSEL ({len(slides)} slides) at {slot}")
        print("  Payload: " + json.dumps(payload, ensure_ascii=False)[:600])
        for o in opps:
            db.mark_posted(conn, o.fingerprint, o.score)
        conn.commit()
        return {"category": category, "status": "dry_run", "scheduled": bool(sched_time),
                "slides": len(slides), "post_id": None}

    # ----- LIVE -----
    try:
        if not slides:
            raise RuntimeError("no slide images found — run card generation first")
        media_ids = []
        for path in slides:
            r = meta_api._post(f"{config.FACEBOOK_PAGE_ID}/photos",
                               {"published": "false", "access_token": config.FACEBOOK_ACCESS_TOKEN},
                               file_field="source", file_path=path)
            mid = r.get("id")
            if not mid:
                raise RuntimeError(f"photo upload returned no id: {r}")
            media_ids.append(mid)
        fields = {
            "message": caption,
            "attached_media": json.dumps([{"media_fbid": m} for m in media_ids]),
            "access_token": config.FACEBOOK_ACCESS_TOKEN,
        }
        if sched_time is not None:
            fields["published"] = "false"
            fields["scheduled_publish_time"] = str(sched_time)
        res = meta_api._post(f"{config.FACEBOOK_PAGE_ID}/feed", fields)
        post_id = res.get("id", "")
        now = datetime.now().isoformat(timespec="seconds")
        for o in opps:
            db.mark_posted(conn, o.fingerprint, o.score)
            db.mark_facebook(conn, o.fingerprint, post_id, now)
        conn.commit()
        _fb_log(f"{category}: carousel published post_id={post_id} slides={len(slides)} "
                f"scheduled={bool(sched_time)}")
        return {"category": category, "status": "ok", "scheduled": bool(sched_time),
                "slides": len(slides), "post_id": post_id}
    except Exception as e:  # noqa: BLE001
        _fb_log(f"{category}: CAROUSEL FAILED after retries: {e}")
        return {"category": category, "status": "failed", "error": str(e), "post_id": None}
