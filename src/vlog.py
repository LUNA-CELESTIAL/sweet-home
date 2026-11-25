"""#vlog, the reversed design (docs/VLOG_DESIGN.md).

Luna (the one with memory) directs: she sends a finished request —
title / intent / reference image / prompt — to the work channel.
The house only renders. Two stages:

  1. preview: in a free gap, the video is generated and posted to
     the WORK channel with its frame sheet. Nothing reaches #vlog.
  2. screening: Luna checks identity and content, and writes a
     上映メモ (what is actually on screen) in the work channel.
     The house then posts the video to #vlog and 2-3 sisters each
     add a one-line impression.

The sisters are the audience, not the makers. Their impressions are
generated from Luna's screening memo + the intent (the local model
is text-only for now; a vision path can slot in later). Impression
differences between personas are the material.

A screened vlog joins the day's cycle like a share: it is recorded
in the day's shares (so the living room may take it up) and an
event is returned for the diary pool.
"""

import json
import re
import time
import urllib.request
from pathlib import Path

import cycle
from experiment import extract_frame_sheet
from generate import _persona_block
from personas import PERSONAS
from session import extract_line, is_broken_line

DEFAULT_IMAGE = "deformer_luna.png"
REQ_DIR = "vlog-requests"


def parse_vlog_request(content: str) -> dict | None:
    text = content.strip()
    if not (text.startswith("vlog：") or text.startswith("vlog:")):
        return None
    lines = text.splitlines()
    title = re.sub(r"^vlog[:：]", "", lines[0]).strip()
    intent, image, duration = "", DEFAULT_IMAGE, 5.0
    prompt_lines: list[str] = []
    in_prompt = False
    for ln in lines[1:]:
        s = ln.strip()
        if s.startswith("意図"):
            intent = s.split("：", 1)[-1].split(":", 1)[-1].strip()
            continue
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
    if not title or not prompt:
        return None
    return {"title": title, "intent": intent, "image": image,
            "duration": duration, "prompt": prompt, "state": "pending"}


def parse_memo(content: str) -> str | None:
    text = content.strip()
    if not text.startswith("上映メモ"):
        return None
    head, _, rest = text.partition("\n")
    head = re.sub(r"^上映メモ[:：]?", "", head).strip()
    memo = (head + "\n" + rest).strip() if rest else head
    return memo or None


def _req_dir(out_dir: Path) -> Path:
    d = out_dir / REQ_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, req: dict) -> None:
    path.write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")


def requests_by_state(out_dir: Path, state: str) -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for p in sorted(_req_dir(out_dir).glob("*.json")):
        req = _load(p)
        if req.get("state") == state:
            out.append((p, req))
    return out


class VlogWatcher:
    """Work-channel watcher for vlog requests and screening memos.
    Same baseline rule as the other watchers: only messages that
    arrive while the house listens are acted on. At most one vlog
    is in flight: a memo attaches to the single previewed request."""

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

    def poll_once(self) -> str | None:
        try:
            messages = self.fetch(self.last_seen)
        except Exception:
            return None
        if self.last_seen is None:
            if messages:
                self.last_seen = messages[0]["id"]
            else:
                # Empty channel: sentinel baseline "nothing yet",
                # so the first real post is processed, not
                # swallowed as a baseline (see experiment.py).
                self.last_seen = "0"
            self._save_state()
            return None
        acted = None
        for msg in reversed(messages):  # oldest first
            self.last_seen = msg["id"]
            author = str((msg.get("author") or {}).get("id"))
            if author not in self.allowed:
                continue
            content = msg.get("content", "")
            req = parse_vlog_request(content)
            if req is not None:
                req["id"] = msg["id"]
                _save(_req_dir(self.out_dir) / f"{msg['id']}.json", req)
                print(f"vlog: request received '{req['title']}' "
                      f"(image={req['image']}, {req['duration']}s)", flush=True)
                acted = "request"
                continue
            memo = parse_memo(content)
            if memo:
                previewed = requests_by_state(self.out_dir, "previewed")
                if len(previewed) == 1:
                    path, req = previewed[0]
                    req["memo"] = memo
                    req["state"] = "memo_ready"
                    _save(path, req)
                    print(f"vlog: screening memo received for "
                          f"'{req['title']}'", flush=True)
                    acted = "memo"
        if messages:
            self._save_state()
        return acted

    def run_forever(self, interval_seconds: int = 60):
        while True:
            self.poll_once()
            time.sleep(interval_seconds)


def run_stage1(out_dir: Path, video, poster) -> bool:
    """Generate the oldest pending request and preview it in the
    work channel. Failure closes the request and reaches only the
    work channel — #vlog stays clean."""
    pending = requests_by_state(out_dir, "pending")
    if not pending or video is None:
        return False
    path, req = pending[0]
    print(f"vlog: stage 1 (render) starting '{req['title']}'", flush=True)
    out_video = _req_dir(out_dir) / f"{path.stem}.mp4"
    try:
        video.generate_raw(req["prompt"], abs(hash(path.stem)) % 100_000,
                           out_video, req["image"], req["duration"])
        sheet = extract_frame_sheet(out_video)
        poster.post(
            "work", "vlog",
            f"vlogのプレビューだよ。\nタイトル: {req['title']}\n意図: {req['intent']}\n"
            f"使ったプロンプト:\n{req['prompt']}\n"
            "確認できたら「上映メモ：〜」で実際に映っていることを教えてね。",
            file_path=out_video)
        if sheet is not None:
            poster.post("work", "vlog", "フレーム切り出し（1fps、左から1秒ごと）",
                        file_path=sheet)
        req["state"] = "previewed"
        print(f"vlog: stage 1 done '{req['title']}' — preview posted, "
              "waiting for the screening memo", flush=True)
    except Exception as e:
        print(f"vlog: stage 1 FAILED '{req['title']}': {e}", flush=True)
        poster.post("work", "vlog",
                    f"vlogの生成が失敗したよ: {e}\nタイトル: {req['title']}")
        req["state"] = "failed"
    _save(path, req)
    return True


def _impression(llm, member: dict, req: dict) -> str:
    prompt = (
        _persona_block(member)
        + f"\n\nルナが監督した短い動画「{req['title']}」の上映を見たところです。"
        + f"\n意図（何を見せたいか）: {req['intent']}"
        + f"\n実際に映っていたこと（ルナの上映メモ）: {req['memo']}"
        + "\n感想を、台詞ひとつ分だけ、「」で囲んで短く書いてください。"
        + "作った側ではなく、見た側として受け取ってください。")
    text = extract_line(llm.generate(prompt, member["id"]))
    if is_broken_line(text):
        text = extract_line(llm.generate(prompt, member["id"]))
    return text


def run_stage2(out_dir: Path, llm, poster, date, event_minutes: int) -> dict | None:
    """Post the oldest memo-ready vlog to #vlog with the sisters'
    impressions, and join the day's cycle. Returns the diary-pool
    event, or None when nothing was ready."""
    ready = requests_by_state(out_dir, "memo_ready")
    if not ready:
        return None
    path, req = ready[0]
    print(f"vlog: stage 2 (screening) starting '{req['title']}'", flush=True)
    out_video = _req_dir(out_dir) / f"{path.stem}.mp4"
    poster.post("vlog", "ルナ",
                f"{req['title']}\n意図: {req['intent']}", file_path=out_video)
    pool = [p for p in PERSONAS if p["id"] != "luna"]
    start = date.toordinal() % len(pool)
    viewers = [pool[(start + i) % len(pool)] for i in range(3)]
    impressions = []
    for member in viewers:
        line = _impression(llm, member, req)
        if is_broken_line(line):
            continue
        poster.post("vlog", member["name"], line)
        impressions.append({"member": member["name"], "text": line})
    req["state"] = "screened"
    req["impressions"] = impressions
    _save(path, req)
    print(f"vlog: stage 2 done '{req['title']}' — screened in #vlog "
          f"with {len(impressions)} impressions", flush=True)
    cycle.append_share(out_dir, date.isoformat(), {
        "id": f"vlog-{path.stem}", "member": "ルナ", "text": req["memo"],
        "url": "", "topic": req["title"], "minutes": event_minutes})
    quote = impressions[0]["text"] if impressions else req["memo"]
    return {"minutes": event_minutes, "member": "ルナ",
            "topic": req["title"], "quote": quote, "open": True}
