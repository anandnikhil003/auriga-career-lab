"""Minimal Facebook Graph API client. Standard library only (urllib).

Implements exactly what we need with official endpoints:
  - publish_photo(): POST /{page_id}/photos  (multipart upload of a PNG)
        optional scheduled_publish_time + published=false  -> Graph schedules it.
  - add_comment():   POST /{object_id}/comments
Every call retries up to FB_MAX_RETRIES with backoff and logs to logs/facebook.log.
No third-party packages, no browser automation.
"""
from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

import config


def _log(msg: str) -> None:
    config.FB_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with config.FB_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _endpoint(path: str) -> str:
    return f"https://graph.facebook.com/{config.GRAPH_VERSION}/{path}"


def _encode_multipart(fields: dict[str, str], file_field: str | None,
                      file_path: str | None) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    nl = b"\r\n"
    body = bytearray()
    for k, v in fields.items():
        body += b"--" + boundary.encode() + nl
        body += f'Content-Disposition: form-data; name="{k}"'.encode() + nl + nl
        body += str(v).encode() + nl
    if file_field and file_path:
        fp = Path(file_path)
        ctype = mimetypes.guess_type(fp.name)[0] or "application/octet-stream"
        body += b"--" + boundary.encode() + nl
        body += (f'Content-Disposition: form-data; name="{file_field}"; '
                 f'filename="{fp.name}"').encode() + nl
        body += f"Content-Type: {ctype}".encode() + nl + nl
        body += fp.read_bytes() + nl
    body += b"--" + boundary.encode() + b"--" + nl
    return bytes(body), boundary


def _post(path: str, fields: dict, file_field=None, file_path=None) -> dict:
    """POST with retries. Returns parsed JSON. Raises on final failure."""
    url = _endpoint(path)
    last = None
    for attempt in range(1, config.FB_MAX_RETRIES + 1):
        try:
            body, boundary = _encode_multipart(fields, file_field, file_path)
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
                data = json.loads(r.read().decode("utf-8"))
            _log(f"OK {path} attempt={attempt} -> {data}")
            return data
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            _log(f"FAIL {path} attempt={attempt}/{config.FB_MAX_RETRIES} {last}")
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            _log(f"FAIL {path} attempt={attempt}/{config.FB_MAX_RETRIES} {last}")
        time.sleep(2 * attempt)
    raise RuntimeError(f"Graph call failed after {config.FB_MAX_RETRIES} retries: {last}")


def build_photo_payload(image_path: str, caption: str,
                        scheduled_publish_time: int | None = None) -> dict:
    """The exact fields sent to /{page_id}/photos (token redacted, file by path).
    Returned for DRY_RUN inspection and tests."""
    payload = {
        "endpoint": _endpoint(f"{config.FACEBOOK_PAGE_ID or '<PAGE_ID>'}/photos"),
        "method": "POST",
        "fields": {
            "caption": caption,
            "access_token": "<redacted>" if config.FACEBOOK_ACCESS_TOKEN else "<TOKEN>",
        },
        "file": {"source": image_path},
    }
    if scheduled_publish_time is not None:
        payload["fields"]["published"] = "false"
        payload["fields"]["scheduled_publish_time"] = scheduled_publish_time
    return payload


def publish_photo(image_path: str, caption: str,
                  scheduled_publish_time: int | None = None) -> dict:
    fields = {"caption": caption, "access_token": config.FACEBOOK_ACCESS_TOKEN}
    if scheduled_publish_time is not None:
        fields["published"] = "false"
        fields["scheduled_publish_time"] = str(scheduled_publish_time)
    return _post(f"{config.FACEBOOK_PAGE_ID}/photos", fields,
                 file_field="source", file_path=image_path)


def add_comment(object_id: str, message: str) -> dict:
    return _post(f"{object_id}/comments",
                 {"message": message, "access_token": config.FACEBOOK_ACCESS_TOKEN})
