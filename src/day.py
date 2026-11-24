"""One day, as parts: morning duty -> conversation clusters ->
evening duty -> diary -> site export.

`Day` holds the shared context so the parts can run either back to
back (run_day, for verification) or at their planned times through
the executor (for real operation). Posting goes through a Poster;
generation through an LLM client; the day's events are the shared
pool everything reads.
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


class Day:
    def __init__(self, llm, poster, date: datetime.date, weather: dict | None,
                 yesterday_seed: dict | None, events: list[dict],
                 out_dir: Path, voice=None, video=None,
                 line_gap_minutes=None, sleeper=None):
        self.llm = llm
        self.poster = poster
        self.date = date
        self.weather = weather
        self.seed = yesterday_seed
        self.events = events
        self.out_dir = out_dir
        self.voice = voice
        self.video = video
        # Living lines breathe: in live operation a gap (minutes, from
        # line_gap_minutes()) passes between lines of a cluster, so the
        # room feels visited over time rather than bursting. Offline
        # runs pass nothing and stay fast.
        self.line_gap_minutes = line_gap_minutes
        self.sleeper = sleeper
        self.result: dict = {}
        out_dir.mkdir(parents=True, exist_ok=True)

    def _duty_with_media(self, member: dict, slot: str, text: str):
        voice_path = video_path = None
        if self.voice is not None:
            voice_path = self.voice.synthesize(
                member["id"], text,
                self.out_dir / "voice" / f"{self.date.isoformat()}-{slot}.wav")
            if voice_path:
                self.result.setdefault("voice", {})[slot] = str(voice_path)
        if self.video is not None:
            video_path = self.video.generate(
                member, slot, self.date.toordinal() + (0 if slot == "morning" else 1),
                self.out_dir / "video" / f"{self.date.isoformat()}-{slot}.mp4")
            if video_path:
                self.result.setdefault("video", {})[slot] = str(video_path)
        self.poster.post("duty", member["name"], text, file_path=video_path or voice_path)

    def morning(self):
        member = duty_member(self.date, "morning")
        text = duty_text(self.llm, member, "morning", self.weather, self.seed)
        self._duty_with_media(member, "morning", text)
        self.result["morning"] = text

    def living(self, cluster_order: list[str] | None = None):
        if not self.seed:
            return
        # A one-line signpost first: the conversation runs in the
        # present progressive, so a glance should still be able to
        # tell what is being talked about.
        self.poster.post("living", "リビング",
                         f"―― {self.seed['sourceMember']}の「{self.seed['topic']}」の話 ――")
        posted = {"n": 0}

        def on_line(t):
            if posted["n"] > 0 and self.line_gap_minutes and self.sleeper:
                self.sleeper(self.line_gap_minutes())
            posted["n"] += 1
            self.poster.post("living", t["name"], t["text"])

        transcript, pool_line = run_session(
            self.seed, cluster_order or DEFAULT_CLUSTER_ORDER, self.llm,
            on_line=on_line)
        self.result["session"] = transcript
        self.result["pool_line"] = pool_line

    def evening(self):
        member = duty_member(self.date, "evening")
        text = duty_text(self.llm, member, "evening", None, None)
        self._duty_with_media(member, "evening", text)
        self.result["evening"] = text

    def diary(self, site_export_path: Path | None = None):
        writer = writer_for(self.date)
        structure, _ = build_diary(self.date, self.events)
        meta, md = diary_prose(self.llm, writer, self.date, self.events, structure,
                               yesterday_seed=self.seed)
        thread = meta.get("thread") or {}
        diary_post = f"{meta['title']}\n{meta['siteExcerpt']}"
        if thread:
            diary_post += (f"\n\n―― いまの話 ――\n前提: {thread['premise']}"
                           f"\n今日の進み: {thread['progress']}"
                           f"\n残っている問い: {thread['question']}")
        self.poster.post("diary", writer["name"], diary_post)
        self.result["diary"] = meta
        (self.out_dir / f"diary-{self.date.isoformat()}.md").write_text(md, encoding="utf-8")
        (self.out_dir / f"diary-{self.date.isoformat()}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        if site_export_path is not None:
            existing = (json.loads(site_export_path.read_text(encoding="utf-8"))
                        if site_export_path.exists() else None)
            site = merge(existing, build_entry(meta, md))
            (self.out_dir / "diary-site.json").write_text(
                json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
        self.result["seed"] = meta["seed"]


def run_day(llm, poster, date: datetime.date, weather: dict | None,
            yesterday_seed: dict | None, events: list[dict],
            out_dir: Path, cluster_order: list[str] | None = None,
            site_export_path: Path | None = None, voice=None, video=None) -> dict:
    day = Day(llm, poster, date, weather, yesterday_seed, events, out_dir,
              voice=voice, video=video)
    day.morning()
    day.living(cluster_order)
    day.evening()
    day.diary(site_export_path)
    return day.result
