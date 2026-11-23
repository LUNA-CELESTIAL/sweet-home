"""One day, wired: morning duty -> conversation cluster -> evening
duty -> diary -> site export. Used by main.py (resident) and by the
trial scripts. Posting goes through a Poster; generation through an
LLM client; the day's events are the shared pool everything reads.
"""

import datetime
import json
from pathlib import Path

from diary import build_diary, writer_for
from duty import duty_member
from export_site import build_entry, merge
from generate import diary_prose, duty_text
from session import run_session

DEFAULT_CLUSTER_ORDER = ["luna", "stella", "spica", "stella"]


def run_day(llm, poster, date: datetime.date, weather: str,
            yesterday_seed: dict | None, events: list[dict],
            out_dir: Path, cluster_order: list[str] | None = None,
            site_export_path: Path | None = None, voice=None) -> dict:
    result = {}
    out_dir.mkdir(parents=True, exist_ok=True)

    def maybe_voice(member: dict, slot: str, text: str):
        if voice is None:
            return
        path = voice.synthesize(member["id"], text,
                                out_dir / "voice" / f"{date.isoformat()}-{slot}.wav")
        if path:
            result.setdefault("voice", {})[slot] = str(path)

    morning_member = duty_member(date, "morning")
    morning = duty_text(llm, morning_member, "morning", weather, yesterday_seed)
    poster.post("duty", morning_member["name"], morning)
    maybe_voice(morning_member, "morning", morning)
    result["morning"] = morning

    if yesterday_seed:
        transcript, pool_line = run_session(
            yesterday_seed, cluster_order or DEFAULT_CLUSTER_ORDER, llm)
        for t in transcript:
            poster.post("living", t["name"], t["text"])
        result["session"] = transcript
        result["pool_line"] = pool_line

    evening_member = duty_member(date, "evening")
    evening = duty_text(llm, evening_member, "evening", "", None)
    poster.post("duty", evening_member["name"], evening)
    maybe_voice(evening_member, "evening", evening)
    result["evening"] = evening

    writer = writer_for(date)
    structure, _ = build_diary(date, events)
    meta, md = diary_prose(llm, writer, date, events, structure)
    poster.post("diary", writer["name"], f"{meta['title']}\n{meta['siteExcerpt']}")
    result["diary"] = meta

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"diary-{date.isoformat()}.md").write_text(md, encoding="utf-8")
    (out_dir / f"diary-{date.isoformat()}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    if site_export_path is not None:
        existing = (json.loads(site_export_path.read_text(encoding="utf-8"))
                    if site_export_path.exists() else None)
        site = merge(existing, build_entry(meta, md))
        (out_dir / "diary-site.json").write_text(
            json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    result["seed"] = meta["seed"]
    return result
