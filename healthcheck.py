"""Operational healthcheck. Standard library only.

Checks SQLite, folders, captions, remaining opportunities, DB size, last post
time, DRY_RUN status and Meta token status. Prints a summary table and logs to
logs/health.log. Exit 0 if healthy, 1 if a CRITICAL check fails (DB unreachable).

  python healthcheck.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import config
import token_check


def _log(msg: str) -> None:
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.ROOT / "logs" / "health.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def _last_post_time(conn) -> str:
    row = conn.execute(
        "SELECT MAX(COALESCE(facebook_post_time, posted_date)) t "
        "FROM opportunities WHERE posted_date IS NOT NULL").fetchone()
    return (row["t"] if row and row["t"] else "never")


def run() -> int:
    rows: list[tuple[str, str, str]] = []  # (check, status, detail)
    critical_ok = True

    # SQLite
    conn = None
    try:
        import db
        conn = db.connect()
        n = conn.execute("SELECT COUNT(*) c FROM opportunities").fetchone()["c"]
        rows.append(("SQLite reachable", "OK", f"{n} rows"))
    except Exception as e:  # noqa: BLE001
        rows.append(("SQLite reachable", "CRITICAL", str(e)[:50]))
        critical_ok = False

    # folders
    rows.append(("logs/ exists", "OK" if (config.ROOT / "logs").exists() else "WARN", ""))
    rows.append(("cards/ exists", "OK" if config.CARDS_DIR.exists() else "WARN",
                 str(config.CARDS_DIR.name)))

    # captions
    caps = sorted(config.FACEBOOK_DIR.glob("*.txt")) if config.FACEBOOK_DIR.exists() else []
    rows.append(("facebook captions", "OK" if len(caps) >= 1 else "WARN",
                 f"{len(caps)}/{len(config.CATEGORIES)} files"))

    # cards present
    cards_n = len(list(config.CARDS_DIR.glob("*.png"))) if config.CARDS_DIR.exists() else 0
    rows.append(("image cards", "OK" if cards_n >= 1 else "WARN",
                 f"{cards_n}/{len(config.CATEGORIES)} png"))

    # stats / size / last post
    if conn is not None:
        s = db.stats(conn)
        rows.append(("opportunities remaining", "OK", f"{s['remaining']}/{s['total']}"))
        rows.append(("published to facebook", "OK", str(s["facebook"])))
        rows.append(("last post time", "OK", _last_post_time(conn)))
    size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
    rows.append(("database size", "OK", f"{size/1024:.1f} KB"))

    # DRY_RUN
    rows.append(("DRY_RUN", "OK", "DRY_RUN" if config.DRY_RUN else "LIVE"))

    # Meta token
    tk = token_check.verify()
    tstatus = "OK" if tk["passed"] else "FAIL"
    rows.append(("Meta token", tstatus, tk.get("mode", "")))

    # print table
    print("┌─ Auriga Healthcheck " + "─" * 38 + "┐")
    for name, status, detail in rows:
        icon = {"OK": "✅", "WARN": "⚠️ ", "FAIL": "❌", "CRITICAL": "🛑"}.get(status, "  ")
        print(f"│ {icon} {name:<26} {status:<9} {detail:<16}│")
    print("└" + "─" * 59 + "┘")

    _log(f"healthcheck critical_ok={critical_ok} token={tstatus} dry_run={config.DRY_RUN}")
    return 0 if critical_ok else 1


if __name__ == "__main__":
    sys.exit(run())
