"""Diary module (offline composition).

Pipeline: event pool -> sections by time block -> diary.md + diary.json.
Rules from docs/SPEC_v0.md and the Step 1/1.5 prototypes:
- Sections are time blocks (max 5), never one per topic; topics the
  writer did not pick still land in diary.json's topic list.
- Quotes from the day are carried verbatim (no paraphrase drift of
  proper nouns: the seed keeps an exact quote and the source member).
- The next-morning seed is a FRAGMENT (topic + quote + one connector
  line without its own time words), so the morning duty can embed it
  without duplicating "yesterday".
- The writer rotates by date.
"""

import datetime

from personas import PERSONAS

BLOCKS = [
    ("朝のこと", 0, 11 * 60),
    ("昼のこと", 11 * 60, 14 * 60),
    ("午後のこと", 14 * 60, 17 * 60),
    ("夕方のこと", 17 * 60, 20 * 60),
    ("夜のこと", 20 * 60, 24 * 60),
]


def writer_for(date: datetime.date) -> dict:
    return PERSONAS[(date.toordinal() + 2) % len(PERSONAS)]


def block_of(minutes: int) -> str:
    for name, start, end in BLOCKS:
        if start <= minutes < end:
            return name
    return "夜のこと"


def build_diary(date: datetime.date, events: list[dict]) -> tuple[dict, str]:
    """events: {minutes, member, topic, quote (optional), open (optional)}"""
    writer = writer_for(date)
    sections: dict[str, list[dict]] = {}
    for ev in events:
        sections.setdefault(block_of(ev["minutes"]), []).append(ev)

    section_list = []
    body_parts = [f"# {date.isoformat()} の日記 — 書き手: {writer['name']}", ""]
    for block, _, _ in BLOCKS:
        evs = sections.get(block)
        if not evs:
            continue
        topic_line = "、".join(dict.fromkeys(e["topic"] for e in evs))
        section_list.append({"heading": block, "topic": topic_line})
        body_parts.append(f"## {block} — {topic_line}")
        for e in evs:
            line = f"{e['member']}の「{e['topic']}」の話があった。"
            if e.get("quote"):
                line += f"「{e['quote']}」と言っていた。"
            body_parts.append(line)
        body_parts.append("")

    topics = list(dict.fromkeys(e["topic"] for e in events))

    seed = None
    open_events = [e for e in events if e.get("open")]
    if open_events:
        last = open_events[-1]
        seed = {
            "topic": last["topic"],
            "sourceMember": last["member"],
            "quote": last.get("quote", ""),
            "note": f"{last['member']}の{last['topic']}の話、途中で終わっていたのが気になってる。",
        }

    data = {
        "date": date.isoformat(),
        "writer": writer["id"],
        "writerName": writer["name"],
        "sections": section_list,
        "topics": topics,
        "participants": list(dict.fromkeys(e["member"] for e in events)),
        "seed": seed,
    }
    body_parts.append("## 今日わかったこと")
    body_parts.append("今日の出来事は、明日の種になる。")
    body_parts.append("")
    body_parts.append(f"— {writer['name']}")
    return data, "\n".join(body_parts)
