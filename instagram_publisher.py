"""Publish the SAME 1080x1080 card to Instagram via the official Instagram Graph API.

Two-step official flow:
  1. POST /{ig_business_id}/media         (image_url + caption)  -> creation_id
  2. POST /{ig_business_id}/media_publish (creation_id)          -> media id

Instagram requires a PUBLIC image_url (it cannot accept a local file upload), so
the card must be served at config.IG_IMAGE_BASE_URL/cards/<category>.png.

DRY_RUN (auto when IG id / token / base url missing): prints "Would post IG <cat>"
and the exact payload, sends nothing. Retries FB_MAX_RETRIES times. Logs to
logs/instagram.log. Records posted_instagram / instagram_post_id /
instagram_post_time in SQLite (separate from Facebook columns).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import cards
import config
import db
import writer
from models import Opportunity


def _log(msg: str) -> None:
    config.IG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with config.IG_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def _endpoint(path: str) -> str:
    return f"https://graph.facebook.com/{config.GRAPH_VERSION}/{path}"


def _post(path: str, params: dict) -> dict:
    url = _endpoint(path)
    last = None
    for attempt in range(1, config.FB_MAX_RETRIES + 1):
        try:
            data = urllib.parse.urlencode(params).encode()
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
                out = json.loads(r.read().decode("utf-8"))
            _log(f"OK {path} attempt={attempt} -> {out}")
            return out
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}"
            _log(f"FAIL {path} attempt={attempt}/{config.FB_MAX_RETRIES} {last}")
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            _log(f"FAIL {path} attempt={attempt}/{config.FB_MAX_RETRIES} {last}")
        time.sleep(2 * attempt)
    raise RuntimeError(f"IG call failed after {config.FB_MAX_RETRIES} retries: {last}")


def image_url_for(category: str) -> str:
    base = config.IG_IMAGE_BASE_URL or "<IG_IMAGE_BASE_URL>"
    return f"{base}/posts/cards/{category}.png"


def build_payload(category: str, caption: str) -> dict:
    return {
        "step1_create_container": {
            "endpoint": _endpoint(f"{config.INSTAGRAM_BUSINESS_ID or '<IG_ID>'}/media"),
            "method": "POST",
            "params": {"image_url": image_url_for(category), "caption": caption,
                       "access_token": "<redacted>" if config.FACEBOOK_ACCESS_TOKEN else "<TOKEN>"},
        },
        "step2_publish": {
            "endpoint": _endpoint(f"{config.INSTAGRAM_BUSINESS_ID or '<IG_ID>'}/media_publish"),
            "method": "POST",
            "params": {"creation_id": "<from step1>", "access_token": "<redacted>"},
        },
    }


def slide_files(category: str) -> list[str]:
    d = config.CARDS_DIR / category
    if not d.exists():
        return []
    return [p.name for p in sorted(d.glob("*.png"), key=lambda x: x.name)]


def image_urls_for(category: str) -> list[str]:
    base = config.IG_IMAGE_BASE_URL or "<IG_IMAGE_BASE_URL>"
    files = slide_files(category) or ["0_cover.png"]
    return [f"{base}/cards/{category}/{f}" for f in files]


def build_carousel_payload(category: str, caption: str) -> dict:
    urls = image_urls_for(category)
    return {
        "step1_child_containers": [
            {"endpoint": _endpoint(f"{config.INSTAGRAM_BUSINESS_ID or '<IG_ID>'}/media"),
             "params": {"image_url": u, "is_carousel_item": "true"}} for u in urls],
        "step2_carousel_container": {
            "endpoint": _endpoint(f"{config.INSTAGRAM_BUSINESS_ID or '<IG_ID>'}/media"),
            "params": {"media_type": "CAROUSEL", "children": "<child ids>",
                       "caption": caption[:80] + ("..." if len(caption) > 80 else "")}},
        "step3_publish": {
            "endpoint": _endpoint(f"{config.INSTAGRAM_BUSINESS_ID or '<IG_ID>'}/media_publish"),
            "params": {"creation_id": "<carousel id>"}},
    }


def publish_category(conn, category: str, opps: list[Opportunity]) -> dict:
    """Publish a multi-image Instagram CAROUSEL: one child container per slide,
    a CAROUSEL container referencing them, then publish. Retry logic unchanged."""
    caption = writer.build_caption(category, opps)
    base = config.IG_IMAGE_BASE_URL or "<IG_IMAGE_BASE_URL>"
    urls = [f"{base}/cards/{category}/{f}" for f in cards.slide_filenames(opps)]

    if config.INSTAGRAM_DRY_RUN:
        print(f"  [IG] Would post {config.CATEGORIES.get(category, category)} "
              f"CAROUSEL ({len(urls)} slides)")
        print("  [IG] Payload: " + json.dumps(build_carousel_payload(category, caption),
                                               ensure_ascii=False)[:420])
        return {"platform": "instagram", "category": category, "status": "dry_run",
                "slides": len(urls), "post_id": None}

    try:
        children = []
        for u in urls:
            c = _post(f"{config.INSTAGRAM_BUSINESS_ID}/media",
                      {"image_url": u, "is_carousel_item": "true",
                       "access_token": config.FACEBOOK_ACCESS_TOKEN})
            cid = c.get("id")
            if not cid:
                raise RuntimeError(f"no child id: {c}")
            children.append(cid)
        container = _post(f"{config.INSTAGRAM_BUSINESS_ID}/media",
                          {"media_type": "CAROUSEL", "children": ",".join(children),
                           "caption": caption, "access_token": config.FACEBOOK_ACCESS_TOKEN})
        creation_id = container.get("id")
        if not creation_id:
            raise RuntimeError(f"no carousel id: {container}")
        res = _post(f"{config.INSTAGRAM_BUSINESS_ID}/media_publish",
                    {"creation_id": creation_id, "access_token": config.FACEBOOK_ACCESS_TOKEN})
        media_id = res.get("id", "")
        now = datetime.now().isoformat(timespec="seconds")
        for o in opps:
            db.mark_instagram(conn, o.fingerprint, media_id, now)
        conn.commit()
        _log(f"{category}: carousel published media_id={media_id} slides={len(urls)}")
        return {"platform": "instagram", "category": category, "status": "ok",
                "slides": len(urls), "post_id": media_id}
    except Exception as e:  # noqa: BLE001
        _log(f"{category}: CAROUSEL FAILED after retries: {e}")
        return {"platform": "instagram", "category": category, "status": "failed",
                "error": str(e), "post_id": None}
