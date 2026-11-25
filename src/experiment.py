"""Experiment jobs: one-off renders in the house's free time.

The split of labour (Ruru's design, 2026-11-25): the prompt is
written by the Luna with memory and context — never by the local
model. The house only renders, in a gap between its regular jobs,
under the usual courtesies (queue-wait, pace, thermal guard, PAUSE).

A request is a message in the work channel (#作業場) from the guild
owner or the bot account (Luna's relay), shaped like:

    実験：<what to check>
    画像：<file name in ComfyUI input>
    尺：<seconds>
    プロンプト：
    <the prompt, verbatim>

The result — the video, the prompt used, and a 1fps frame sheet —
is posted back to the work channel. It never enters the living
room or the diary cycle.
"""

import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path

DEFAULT_IMAGE = "deformer_luna.png"


def parse_request(content: str) -> dict | None:
    text = content.strip()
    if not text.startswith("実験"):
        return None
    lines = text.splitlines()
    note = lines[0].split("：", 1)[-1].split(":", 1)[-1].strip() if lines else ""
    image = DEFAULT_IMAGE
    duration = 5.0
    prompt_lines: list[str] = []
    in_prompt = False
    for ln in lines[1:]:
        s = ln.strip()
        if s.startswith("画像"):
            image = s.split("：", 1)[-1].split(":", 1)[-1].strip() or image
            continue
        if s.startswith("尺"):
            m = re.search(r"(\d+(?:\.\d+)?)", s)
            if m:
                duration = float(m.group(1))
            continue
        if s.startswith("プロンプト"):
            in_prompt = True
            continue
        if in_prompt:
            prompt_lines.append(ln)
    prompt = "\n".join(prompt_lines).strip().strip("`").strip()
    if not prompt:
        return None
    return {"note": note, "image": image, "duration": duration, "prompt": prompt}


class ExperimentWatcher:
    """Polls the work channel for experiment requests, the same
    baseline way as the control watcher: history is never acted on,
    only messages that arrive while the house listens."""

    def __init__(self, token: str, work_channel_id: str, out_dir: Path,
                 state_path: Path, allowed_authors: set[str], fetch=None):
        self.token = token if token.startswith("Bot ") else f"Bot {token}"
        self.channel_id = work_channel_id
        self.out_dir = out_dir
        self.state_path = state_path
        self.allowed = allowed_authors
        self.fetch = fetch or self._fetch_messages
        self.last_seen: str | None = None
        if state_path.exists():
            try:
                self.last_seen = json.loads(
                    state_path.read_text(encoding="utf-8")).get("last_seen")
            except Exception:
                self.last_seen = None

    def _fetch_messages(self, after: str | None) -> list[dict]:
        url = f"https://discord.com/api/v10/channels/{self.channel_id}/messages?limit=10"
        if after:
            url += f"&after={after}"
        req = urllib.request.Request(
            url, headers={"Authorization": self.token, "User-Agent": "sweet-home/0.1"})
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read())

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"last_seen": self.last_seen}), encoding="utf-8")

    def poll_once(self) -> dict | None:
        try:
            messages = self.fetch(self.last_seen)
        except Exception:
            return None
        if self.last_seen is None:
            if messages:
                self.last_seen = messages[0]["id"]
            else:
                # Empty channel: the baseline is "nothing yet".
                # The sentinel keeps the NEXT poll from treating
                # the first real post as a baseline and swallowing
                # it (2026-11-25: an empty work channel at first
                # start ate the first experiment/vlog requests).
                self.last_seen = "0"
            self._save_state()
            return None
        found = None
        for msg in reversed(messages):  # oldest first
            self.last_seen = msg["id"]
            author = str((msg.get("author") or {}).get("id"))
            if author not in self.allowed:
                continue
            req = parse_request(msg.get("content", ""))
            if req is None:
                continue
            req["id"] = msg["id"]
            req_dir = self.out_dir / "experiments"
            req_dir.mkdir(parents=True, exist_ok=True)
            (req_dir / f"{msg['id']}.json").write_text(
                json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"experiment: request received '{req['note']}' "
                  f"(image={req['image']}, {req['duration']}s)", flush=True)
            found = req
        if messages:
            self._save_state()
        return found

    def run_forever(self, interval_seconds: int = 60):
        while True:
            self.poll_once()
            time.sleep(interval_seconds)


def pending_requests(out_dir: Path) -> list[Path]:
    req_dir = out_dir / "experiments"
    if not req_dir.exists():
        return []
    return sorted(p for p in req_dir.glob("*.json")
                  if not (req_dir / f"{p.stem}.done").exists())


def extract_frame_sheet(video_path: Path) -> Path | None:
    """1fps frames tiled into one sheet (left to right, 1s apart),
    so the frames can be judged from a single image. None on any
    failure — the video post still carries the result."""
    sheet = video_path.with_name(video_path.stem + "-frames.png")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-vf", "fps=1,scale=512:-1,tile=5x1", "-frames:v", "1", str(sheet)],
            check=True, capture_output=True, timeout=120)
        return sheet if sheet.exists() else None
    except Exception:
        return None


def run_pending(out_dir: Path, video, poster) -> bool:
    """Run the oldest pending experiment, if any. Returns True when
    one ran (time was consumed). Failure is reported to the work
    channel and the request is still closed — no silent retries."""
    pending = pending_requests(out_dir)
    if not pending or video is None:
        return False
    req_path = pending[0]
    req = json.loads(req_path.read_text(encoding="utf-8"))
    print(f"experiment: starting '{req['note']}'", flush=True)
    out_video = out_dir / "experiments" / f"{req_path.stem}.mp4"
    try:
        video.generate_raw(req["prompt"], abs(hash(req_path.stem)) % 100_000,
                           out_video, req["image"], req["duration"])
        sheet = extract_frame_sheet(out_video)
        poster.post(
            "work", "実験",
            f"実験の結果だよ。\n確認したいこと: {req['note']}\n"
            f"使ったプロンプト:\n{req['prompt']}",
            file_path=out_video)
        if sheet is not None:
            poster.post("work", "実験", "フレーム切り出し（1fps、左から1秒ごと）",
                        file_path=sheet)
        else:
            poster.post("work", "実験", "フレーム切り出しはできなかった。動画の方を見てね。")
        print(f"experiment: done '{req['note']}'", flush=True)
    except Exception as e:
        print(f"experiment: FAILED '{req['note']}': {e}", flush=True)
        poster.post("work", "実験",
                    f"実験が失敗したよ: {e}\n使おうとしたプロンプト:\n{req['prompt']}")
    (req_path.parent / f"{req_path.stem}.done").touch()
    return True
