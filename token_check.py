"""Meta/Facebook token preflight. Standard library only.

Verifies BEFORE posting that:
  1. the token is valid,
  2. it is long-lived,
  3. it grants pages_manage_posts AND pages_read_engagement,
  4. the configured FACEBOOK_PAGE_ID belongs to the token (via /me/accounts).

Run standalone:           python token_check.py
Offline logic self-test:  python token_check.py --selftest

Returns/【exit】 PASS=0, FAIL=1. Logs every run to logs/token.log.
No token configured => PASS (intentional DRY_RUN), so the pipeline keeps
generating cards/captions without crashing.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import config

REQUIRED_PERMS = ("pages_manage_posts", "pages_read_engagement")


def _log(msg: str) -> None:
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.ROOT / "logs" / "token.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def _graph_get(path: str, params: dict) -> dict:
    url = (f"https://graph.facebook.com/{config.GRAPH_VERSION}/{path}?"
           + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def evaluate(debug: dict, accounts: list, perms: list, page_id: str) -> dict:
    """Pure decision logic (no network) -> result dict. Unit-testable."""
    now = int(time.time())
    valid = bool(debug.get("is_valid"))
    exp = int(debug.get("expires_at", 0) or 0)
    long_lived = (exp == 0) or (exp - now > 7 * 86400)

    granted = {p["permission"] for p in perms if p.get("status") == "granted"}
    granted |= set(debug.get("scopes", []))
    missing = [p for p in REQUIRED_PERMS if p not in granted]

    page = next((a for a in accounts if str(a.get("id")) == str(page_id)), None)
    page_match = page is not None
    page_name = page.get("name", "") if page else ""

    can_post = valid and page_match and "pages_manage_posts" in granted
    passed = valid and long_lived and not missing and page_match

    if exp == 0:
        exp_info = "Never expires (long-lived page token)"
    else:
        days = (exp - now) / 86400
        exp_info = f"{datetime.utcfromtimestamp(exp):%Y-%m-%d %H:%M} UTC ({days:.1f} days left)"

    reasons = []
    if not valid:
        reasons.append("token invalid/expired")
    if not long_lived:
        reasons.append("token is short-lived")
    if missing:
        reasons.append("missing perms: " + ", ".join(missing))
    if not page_match:
        reasons.append(f"PAGE_ID {page_id} not found on this token")

    return {
        "passed": passed, "valid": valid, "long_lived": long_lived,
        "granted": sorted(granted), "missing": missing,
        "page_match": page_match, "page_name": page_name, "page_id": page_id,
        "expiration": exp_info, "can_post": can_post, "reasons": reasons,
    }


def verify(token: str | None = None, page_id: str | None = None) -> dict:
    token = token if token is not None else config.FACEBOOK_ACCESS_TOKEN
    page_id = page_id if page_id is not None else config.FACEBOOK_PAGE_ID

    if not token:
        res = {"passed": True, "mode": "DRY_RUN", "valid": False, "long_lived": False,
               "granted": [], "missing": list(REQUIRED_PERMS), "page_match": False,
               "page_name": "", "page_id": page_id or "", "expiration": "n/a",
               "can_post": False, "reasons": ["no token configured — DRY_RUN"]}
        _log("no token configured -> PASS (DRY_RUN)")
        return res

    try:
        debug = _graph_get("debug_token", {"input_token": token, "access_token": token}
                           ).get("data", {})
        perms = _graph_get("me/permissions", {"access_token": token}).get("data", [])
        accounts = _graph_get("me/accounts", {"access_token": token,
                              "fields": "id,name,tasks"}).get("data", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        _log(f"FAIL graph http {e.code}: {body}")
        return _fail(page_id, f"Graph error {e.code}: {body}")
    except Exception as e:  # noqa: BLE001
        _log(f"FAIL graph unreachable: {e}")
        return _fail(page_id, f"could not reach Graph / token unverifiable: {e}")

    res = evaluate(debug, accounts, perms, page_id)
    res["mode"] = "LIVE" if res["passed"] else "DRY_RUN (token FAIL)"
    _log(f"{'PASS' if res['passed'] else 'FAIL'} page={res['page_name']} "
         f"missing={res['missing']} reasons={res['reasons']}")
    return res


def _fail(page_id: str, reason: str) -> dict:
    return {"passed": False, "mode": "DRY_RUN (token FAIL)", "valid": False,
            "long_lived": False, "granted": [], "missing": list(REQUIRED_PERMS),
            "page_match": False, "page_name": "", "page_id": page_id or "",
            "expiration": "n/a", "can_post": False, "reasons": [reason]}


def render(res: dict) -> str:
    v = lambda b: "✅" if b else "❌"  # noqa: E731
    lines = [
        "──────── Meta Token Check ────────",
        f"Result:        {'PASS' if res['passed'] else 'FAIL'}",
        f"Token valid:   {v(res['valid'])}",
        f"Long-lived:    {v(res['long_lived'])}",
        f"Page name:     {res['page_name'] or '-'}",
        f"Page ID:       {res['page_id'] or '-'}  match {v(res['page_match'])}",
        f"Permissions:   granted={', '.join(res['granted']) or 'none'}",
        f"               missing={', '.join(res['missing']) or 'none'}",
        f"Expiration:    {res['expiration']}",
        f"Post capable:  {v(res['can_post'])}",
        f"Mode:          {res.get('mode','')}",
    ]
    if res["reasons"]:
        lines.append("Notes:         " + "; ".join(res["reasons"]))
    lines.append("──────────────────────────────────")
    return "\n".join(lines)


def _selftest() -> int:
    now = int(time.time())
    healthy_debug = {"is_valid": True, "expires_at": 0,
                     "scopes": list(REQUIRED_PERMS)}
    healthy_perms = [{"permission": p, "status": "granted"} for p in REQUIRED_PERMS]
    healthy_acc = [{"id": "100", "name": "Auriga Career Lab", "tasks": ["CREATE_CONTENT"]}]

    cases = {
        "healthy -> PASS": (evaluate(healthy_debug, healthy_acc, healthy_perms, "100"), True),
        "invalid token -> FAIL":
            (evaluate({"is_valid": False, "expires_at": 0, "scopes": []},
                      healthy_acc, [], "100"), False),
        "missing page -> FAIL":
            (evaluate(healthy_debug, healthy_acc, healthy_perms, "999"), False),
        "missing perm -> FAIL":
            (evaluate({"is_valid": True, "expires_at": 0,
                       "scopes": ["pages_read_engagement"]},
                      healthy_acc, [{"permission": "pages_read_engagement",
                                     "status": "granted"}], "100"), False),
        "short-lived -> FAIL":
            (evaluate({"is_valid": True, "expires_at": now + 3600,
                       "scopes": list(REQUIRED_PERMS)},
                      healthy_acc, healthy_perms, "100"), False),
    }
    ok = True
    for name, (res, expect) in cases.items():
        got = res["passed"]
        mark = "OK" if got == expect else "WRONG"
        if got != expect:
            ok = False
        print(f"  [{mark}] {name}: passed={got}")
    # no-token -> PASS (via verify, no network)
    nt = verify("", "")
    print(f"  [{'OK' if nt['passed'] else 'WRONG'}] no token -> PASS: passed={nt['passed']}")
    return 0 if ok and nt["passed"] else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    res = verify()
    print(render(res))
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
