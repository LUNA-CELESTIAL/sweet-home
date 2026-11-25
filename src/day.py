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

import cycle
from diary import build_diary, writer_for
from duty import duty_member
from export_site import build_entry, merge
from generate import diary_prose, duty_text
from session import run_session

LIVING_TIMES = [10 * 60 + 30, 14 * 60 + 30, 17 * 60 + 30]


def cluster_order_for(seed: dict, date: datetime.date, cluster_idx: int) -> list[str]:
    """Who talks in a living cluster, by role — not a fixed rotation
    of the whole house. The originator is the seed's source member;
    opener and guests rotate by date. The day's three clusters take
    three shapes: an exchange (two members back and forth), a join
    (a guest steps in), and a widening (two guests). A line that
    calls a member by name can still rewrite the next turn inside
    run_session."""
    from personas import PERSONAS
    ids = [p["id"] for p in PERSONAS]
    by_name = {p["name"]: p["id"] for p in PERSONAS}
    originator = by_name.get(seed.get("sourceMember", ""))
    rot = date.toordinal() % len(ids)
    ring = [ids[(rot + k) % len(ids)] for k in range(len(ids))]
    opener = next(i for i in ring if i != originator)
    if originator is None:
        # The seed came from outside the sisters (e.g. Ruru's
        # share): another sister takes the originator's chair.
        originator = next(i for i in ring if i != opener)
    guests = [i for i in ring if i not in (opener, originator)]
    if cluster_idx == 0:
        return [opener, originator, opener, originator]
    if cluster_idx == 1:
        return [opener, originator, guests[0], originator]
    return [opener, originator, guests[0], guests[1], originator]
MORNING_MINUTES = 9 * 60 + 30
EVENING_MINUTES = 20 * 60


class Day:
    def __init__(self, llm, poster, date: datetime.date, weather: dict | None,
                 yesterday_seed: dict | None, events: list[dict] | None = None,
                 out_dir: Path = Path("out"), voice=None, video=None,
                 line_gap_minutes=None, sleeper=None, llm_release=None,
                 share_seed_loader=None, related_seed: dict | None = None):
        self.llm = llm
        self.poster = poster
        self.date = date
        self.weather = weather
        self.seed = yesterday_seed
        # The day's own event pool: starts from whatever the house
        # already knows (site updates, outside events) and grows with
        # what actually happens today — duty, shares, the living
        # room. The diary is written from this, and only this.
        self.events = list(events) if events else []
        self.out_dir = out_dir
        # A fresh share from this morning (a video, a link) can take
        # over the living room's topic; loaded lazily at the first
        # cluster, because shares arrive after the morning duty.
        self.share_seed_loader = share_seed_loader
        # A past diary topic related to today's talk; the last
        # cluster of the day may return to it.
        self.related_seed = related_seed
        self._living_seed: dict | None = None
        self._living_count = 0
        self.voice = voice
        self.video = video
        # Living lines breathe: in live operation a gap (minutes, from
        # line_gap_minutes()) passes between lines of a cluster, so the
        # room feels visited over time rather than bursting. Offline
        # runs pass nothing and stay fast.
        self.line_gap_minutes = line_gap_minutes
        self.sleeper = sleeper
        # Called when a part's generation is done, to hand the GPU
        # back (live Ollama unloads its model). Offline: None.
        self.llm_release = llm_release
        self.result: dict = {}
        out_dir.mkdir(parents=True, exist_ok=True)

    def _duty_with_media(self, member: dict, slot: str, text: str):
        voice_path = video_path = None
        if self.video is not None:
            # The video speaks the line itself (H3 native audio), so
            # VOICEVOX is only the fallback for when there is no video.
            try:
                video_path = self.video.generate(
                    member, slot,
                    self.date.toordinal() + (0 if slot == "morning" else 1),
                    self.out_dir / "video" / f"{self.date.isoformat()}-{slot}.mp4",
                    speech=text, weather=self.weather if slot == "morning" else None,
                    duration=10)
            except Exception as e:
                print(f"video failed for {slot} duty, falling back to voice: {e}")
                video_path = None
            if video_path:
                self.result.setdefault("video", {})[slot] = str(video_path)
        if video_path is None and self.voice is not None:
            voice_path = self.voice.synthesize(
                member["id"], text,
                self.out_dir / "voice" / f"{self.date.isoformat()}-{slot}.wav")
            if voice_path:
                self.result.setdefault("voice", {})[slot] = str(voice_path)
        self.poster.post("duty", member["name"], text, file_path=video_path or voice_path)

    def _release(self):
        if self.llm_release is not None:
            self.llm_release()

    def morning(self):
        member = duty_member(self.date, "morning")
        text = duty_text(self.llm, member, "morning", self.weather, self.seed)
        self._release()  # hand VRAM to the video render that follows
        self._duty_with_media(member, "morning", text)
        self.result["morning"] = text
        self.events.append({"minutes": MORNING_MINUTES, "member": member["name"],
                            "topic": "朝の当番", "quote": text})

    def _effective_living_seed(self) -> dict | None:
        if self._living_seed is None:
            share_seed = None
            if self.share_seed_loader is not None:
                try:
                    share_seed = self.share_seed_loader()
                except Exception:
                    share_seed = None
            self._living_seed = share_seed or self.seed
            if share_seed:
                self.events.append({
                    "minutes": MORNING_MINUTES + 30,
                    "member": share_seed["sourceMember"],
                    "topic": share_seed["topic"],
                    "quote": share_seed["quote"]})
        # The day's last cluster may return to a related past topic.
        if (self._living_count == len(LIVING_TIMES) - 1
                and self.related_seed and self._living_seed
                and self.related_seed["topic"] != self._living_seed["topic"]):
            return self.related_seed
        return self._living_seed

    def living(self, cluster_order: list[str] | None = None):
        seed = self._effective_living_seed()
        idx = min(self._living_count, len(LIVING_TIMES) - 1)
        self._living_count += 1
        if not seed:
            return
        # A signpost first: the conversation runs in the present
        # progressive, so a glance should still be able to tell what
        # is being talked about — the header names the topic, and a
        # one-line explanation (composed by code from the seed's own
        # material, never a new generation) says which thing it is.
        header = f"―― {seed['sourceMember']}の「{seed['topic']}」の話 ――"
        about = seed.get("about") or cycle.about_for_seed(seed)
        if about:
            header += f"\n{about}"
        self.poster.post("living", "リビング", header)
        posted = {"n": 0}

        def on_line(t):
            if posted["n"] > 0 and self.line_gap_minutes and self.sleeper:
                self.sleeper(self.line_gap_minutes())
            posted["n"] += 1
            self.poster.post("living", t["name"], t["text"])

        transcript, pool_line = run_session(
            seed, cluster_order or cluster_order_for(seed, self.date, idx),
            self.llm, on_line=on_line)
        self.result["session"] = transcript
        self.result["pool_line"] = pool_line
        if transcript:
            closing = next(
                (t for t in reversed(transcript)
                 if t["name"] == seed["sourceMember"]), transcript[-1])
            self.events.append({
                "minutes": LIVING_TIMES[idx], "member": seed["sourceMember"],
                "topic": seed["topic"], "quote": closing["text"], "open": True})
        self._release()

    def evening(self):
        member = duty_member(self.date, "evening")
        text = duty_text(self.llm, member, "evening", None, None)
        self._release()  # hand VRAM to the video render that follows
        self._duty_with_media(member, "evening", text)
        self.result["evening"] = text
        self.events.append({"minutes": EVENING_MINUTES, "member": member["name"],
                            "topic": "夜の当番", "quote": text})

    def diary(self, site_export_path: Path | None = None):
        writer = writer_for(self.date)
        structure, _ = build_diary(self.date, self.events)
        meta, md = diary_prose(self.llm, writer, self.date, self.events, structure,
                               yesterday_seed=self.seed)
        self._release()
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
        # Close the cycle: tonight's diary leaves tomorrow's seed
        # and joins the archive its future topics may resurface from.
        cycle.save_seed(self.out_dir, meta["seed"])
        cycle.append_archive(self.out_dir, meta)


def run_day(llm, poster, date: datetime.date, weather: dict | None,
            yesterday_seed: dict | None, events: list[dict] | None = None,
            out_dir: Path = Path("out"), cluster_order: list[str] | None = None,
            site_export_path: Path | None = None, voice=None, video=None,
            share_seed_loader=None, related_seed: dict | None = None) -> dict:
    day = Day(llm, poster, date, weather, yesterday_seed, events, out_dir,
              voice=voice, video=video,
              share_seed_loader=share_seed_loader, related_seed=related_seed)
    day.morning()
    day.living(cluster_order)
    day.evening()
    day.diary(site_export_path)
    return day.result
