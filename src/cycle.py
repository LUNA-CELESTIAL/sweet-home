"""The day-to-day cycle: diary -> tomorrow's seed -> living -> diary.

State lives in out/ as plain JSON, written by the day itself:
- seed.json: the seed yesterday's diary left open (a fragment:
  topic + verbatim quote + source member + one connector line).
- diary-archive.json: past diary entries (date, topics, seed,
  excerpt), newest last, so a past topic can resurface when it
  relates to what the house is talking about now.
- shares-<date>.json: things shared in the house today (a video, a
  link) that can become the living room's topic.

Seed priority for a day's living room:
  1. a fresh share from this morning (after the morning duty)
  2. yesterday's diary seed
  3. a related past diary topic (when the diary left nothing open)
The morning duty always speaks from yesterday's seed; shares come
after it by design (the greeting goes out, then the house reacts).
"""

import json
import re
from pathlib import Path


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load_seed(out_dir: Path) -> dict | None:
    seed = _read(out_dir / "seed.json")
    return seed if isinstance(seed, dict) and seed.get("topic") else None


def save_seed(out_dir: Path, seed: dict | None) -> None:
    path = out_dir / "seed.json"
    if seed:
        _write(path, seed)
    elif path.exists():
        # The diary left nothing open: do not let a stale seed
        # repeat forever. Tomorrow falls back to the archive.
        path.unlink()


def load_archive(out_dir: Path) -> list[dict]:
    data = _read(out_dir / "diary-archive.json")
    return data if isinstance(data, list) else []


def append_archive(out_dir: Path, meta: dict) -> None:
    archive = load_archive(out_dir)
    entry = {"date": meta["date"], "topics": meta.get("topics", []),
             "seed": meta.get("seed"),
             "excerpt": meta.get("siteExcerpt", "")}
    archive = [e for e in archive if e.get("date") != entry["date"]]
    archive.append(entry)
    _write(out_dir / "diary-archive.json", archive[-30:])


def _shared_run(a: str, b: str) -> int:
    """Longest common substring length (chars)."""
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k]:
                k += 1
            best = max(best, k)
    return best


def related_past_seed(archive: list[dict], current_topic: str,
                      skip_dates: set[str]) -> dict | None:
    """A past diary topic that shares a real word-run (>=3 chars)
    with the current topic, as a seed fragment. The past diary's own
    seed quote is carried verbatim when there is one."""
    best_entry, best_len = None, 2
    for entry in archive:
        if entry.get("date") in skip_dates:
            continue
        for topic in entry.get("topics", []):
            n = _shared_run(topic, current_topic)
            if n > best_len:
                best_entry, best_len = entry, n
    if best_entry is None:
        return None
    past_seed = best_entry.get("seed") or {}
    topic = past_seed.get("topic") or best_entry["topics"][0]
    return {
        "topic": topic,
        "sourceMember": past_seed.get("sourceMember", ""),
        "quote": past_seed.get("quote") or best_entry.get("excerpt", ""),
        "note": f"前に日記で話した「{topic}」の話、今日の話と関係ありそうで気になってる。",
    }


def load_shares(out_dir: Path, date_iso: str) -> list[dict]:
    data = _read(out_dir / f"shares-{date_iso}.json")
    return data if isinstance(data, list) else []


def append_share(out_dir: Path, date_iso: str, share: dict) -> None:
    shares = load_shares(out_dir, date_iso)
    if any(s.get("id") == share.get("id") for s in shares):
        return
    shares.append(share)
    _write(out_dir / f"shares-{date_iso}.json", shares)


def share_to_seed(share: dict) -> dict:
    text = (share.get("text") or "").strip()
    url = share.get("url") or ""
    quote = text if text else url
    topic = share.get("topic") or "共有されたもの"
    return {
        "topic": topic,
        "sourceMember": share.get("member", "るる"),
        "quote": quote,
        "note": f"{share.get('member', 'るる')}が置いていった「{topic}」の話。",
    }


_URL_RE = re.compile(r"https?://\S+")


def share_topic(text: str, has_video: bool, has_image: bool) -> str:
    """A short topic label for a share: its own words when it has
    any, otherwise what kind of thing it is."""
    words = _URL_RE.sub("", text).strip()
    if words:
        return words[:24]
    if has_video:
        return "動画の共有"
    if has_image:
        return "画像の共有"
    return "リンクの共有"
