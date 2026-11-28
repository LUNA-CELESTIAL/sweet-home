"""Weekly prepared talk topics.

Luna writes a week of living-room topics in advance and posts
them to the work channel as a 週間テーマ： request; the house
files them here and spends one per day, on its date.

Why: the diary-seed cycle alone had two failure shapes — a day
with nothing circulating went quiet, and a topic that did
circulate re-seeded itself forever (the Ping loop, 2026-11-28).
A prepared queue is the floor, not the ceiling: a morning share
or a genuinely new diary seed still preempts it.

A prepared seed carries no verbatim quote — words are never put
in a sister's mouth. The packet says plainly that the topic was
brought as this week's theme, with the angle line Luna wrote,
and the named sister opens it in her own words.
"""

import datetime
import json
from pathlib import Path

QUEUE_FILE = "topic-queue.json"
SEP = "｜"


def parse_topics_request(content: str) -> list[dict] | None:
    """週間テーマ： followed by one entry per line:
    YYYY-MM-DD｜名前｜テーマ｜切り口 (the angle may be omitted).
    Lines that do not parse are skipped, never fatal."""
    text = (content or "").strip()
    if not (text.startswith("週間テーマ：") or text.startswith("週間テーマ:")):
        return None
    entries = []
    for line in text.splitlines()[1:]:
        parts = [p.strip() for p in line.split(SEP)]
        if len(parts) < 3:
            continue
        date_s, member, topic = parts[0], parts[1], parts[2]
        try:
            datetime.date.fromisoformat(date_s)
        except ValueError:
            continue
        if not member or not topic:
            continue
        entries.append({"date": date_s, "member": member, "topic": topic,
                        "angle": parts[3] if len(parts) > 3 else ""})
    return entries or None


def load_queue(out_dir: Path) -> list[dict]:
    try:
        data = json.loads((out_dir / QUEUE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def append_topics(out_dir: Path, entries: list[dict]) -> int:
    """File new entries; a date+topic already queued is not
    duplicated. Returns how many were added."""
    queue = load_queue(out_dir)
    known = {(e.get("date"), e.get("topic")) for e in queue}
    added = 0
    for e in entries:
        if (e["date"], e["topic"]) in known:
            continue
        queue.append(e)
        known.add((e["date"], e["topic"]))
        added += 1
    if added:
        queue.sort(key=lambda e: e["date"])
        (out_dir / QUEUE_FILE).write_text(
            json.dumps(queue, ensure_ascii=False, indent=1), encoding="utf-8")
    return added


def topic_seed_for(out_dir: Path, date_iso: str) -> dict | None:
    """The prepared seed for a date, or None. Date-keying is the
    consumption rule: an entry belongs to its date and is never
    spent on another day."""
    for e in load_queue(out_dir):
        if e.get("date") == date_iso:
            return {
                "topic": e["topic"],
                "sourceMember": e["member"],
                "quote": "",
                "note": e.get("angle", ""),
                "about": e.get("angle", ""),
                "prepared": True,
            }
    return None
