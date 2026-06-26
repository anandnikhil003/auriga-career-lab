"""Posting schedule: maps each category to a clock slot today and to a UTC epoch
for Facebook Graph native scheduling. Standard library only.

Graph requires scheduled_publish_time to be 10 minutes .. 75 days in the future.
slot_epoch() returns (epoch, ok, reason) so the publisher can decide.
"""
from __future__ import annotations

from datetime import datetime

import config


def ordered_slots() -> list[tuple[str, int]]:
    return sorted(config.SCHEDULE.items(), key=lambda kv: kv[1])


def _local_tz():
    return datetime.now().astimezone().tzinfo


def slot_datetime(category: str) -> datetime:
    hour = config.SCHEDULE[category]
    return datetime.now(_local_tz()).replace(hour=hour, minute=0, second=0, microsecond=0)


def slot_epoch(category: str) -> tuple[int, bool, str]:
    when = slot_datetime(category)
    now = datetime.now(_local_tz())
    delta = (when - now).total_seconds()
    epoch = int(when.timestamp())
    if delta < 600:
        return epoch, False, "slot <10 min away (Graph min) — publish immediately"
    if delta > 75 * 86400:
        return epoch, False, "slot >75 days away (Graph max)"
    return epoch, True, "ok"


def slot_label(category: str) -> str:
    h = config.SCHEDULE[category]
    return f"{(h - 1) % 12 + 1} {'AM' if h < 12 else 'PM'}"


def schedule_text() -> str:
    lines = ["Posting schedule (local time):"]
    for cat, _ in ordered_slots():
        lines.append(f"  {slot_label(cat):>6}  ->  {config.CATEGORIES[cat]}")
    return "\n".join(lines)


def cron_snippet() -> str:
    out = ["# Generate + schedule once each evening (Graph publishes at slot times):",
           "0 18 * * *  cd /path/to/auriga-opportunities && python3 main.py >> logs/cron.log 2>&1",
           "#",
           "# OR publish immediately at each slot (set USE_GRAPH_SCHEDULING=false):"]
    for cat, h in ordered_slots():
        out.append(f"0 {h} * * *  cd /path/to/auriga-opportunities && "
                   f"python3 main.py --slot {cat} >> logs/cron.log 2>&1")
    return "\n".join(out)
