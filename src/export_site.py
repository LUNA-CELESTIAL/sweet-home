"""Export a diary (meta json + md body) into sweet-bits' diary.json shape.

Contract: docs/DIARY_DELIVERY.md. Only small structured text crosses
to the site: no media, no raw logs, no seed. The export enforces the
size cap and the 30-entry index limit on the writer's side.
"""

import json
import re

MAX_ENTRIES = 30
MAX_BYTES = 64 * 1024


def parse_md_sections(md_text: str) -> list[dict]:
    sections = []
    current = None
    buf: list[str] = []
    for line in md_text.splitlines():
        if line.startswith("## "):
            if current is not None:
                current["paragraphs"] = [p for p in "\n".join(buf).split("\n") if p.strip()]
                sections.append(current)
            heading = line[3:].strip()
            current = {"heading": heading, "paragraphs": []}
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        current["paragraphs"] = [p for p in "\n".join(buf).split("\n") if p.strip()]
        sections.append(current)
    return sections


def build_entry(meta: dict, md_text: str) -> dict:
    md_sections = parse_md_sections(md_text)
    topic_by_heading = {s["heading"]: s.get("topic", "") for s in meta.get("sections", [])}
    sections = []
    for s in md_sections:
        heading = s["heading"].split(" — ")[0]
        sections.append({
            "heading": heading,
            "topic": topic_by_heading.get(heading, ""),
            "paragraphs": s["paragraphs"],
        })
    return {
        "date": meta["date"],
        "writerName": meta["writerName"],
        "title": meta["title"],
        "excerpt": meta["siteExcerpt"],
        "sections": sections,
        "topics": meta.get("topics", []),
    }


def merge(existing: dict | None, entry: dict) -> dict:
    entries = [] if existing is None else [existing["latest"]] + [
        e for e in existing.get("entries", []) if e["date"] != existing["latest"]["date"]
    ]
    by_date = {e["date"]: e for e in entries if e["date"] != entry["date"]}
    # index keeps summaries only; full text only for the latest entry
    index = [{"date": e["date"], "writerName": e["writerName"], "title": e["title"], "excerpt": e["excerpt"]}
             for e in by_date.values()]
    index.append({"date": entry["date"], "writerName": entry["writerName"],
                  "title": entry["title"], "excerpt": entry["excerpt"]})
    index.sort(key=lambda e: e["date"], reverse=True)
    latest = max([entry] + [e for e in by_date.values() if "sections" in e],
                 key=lambda e: e["date"], default=entry)
    out = {"latest": latest, "entries": index[:MAX_ENTRIES]}
    size = len(json.dumps(out, ensure_ascii=False).encode())
    if size > MAX_BYTES:
        raise ValueError(f"diary.json would exceed {MAX_BYTES} bytes ({size})")
    return out
