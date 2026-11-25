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
import edit as edit_mod
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
    theme, highlight = "", ""
    prompt_lines: list[str] = []
    in_prompt = False
    for ln in lines[1:]:
        s = ln.strip()
        if s.startswith("テーマ"):
            theme = s.split("：", 1)[-1].split(":", 1)[-1].strip()
            continue
        if s.startswith("見どころ"):
            highlight = s.split("：", 1)[-1].split(":", 1)[-1].strip()
            continue
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
    return {"title": title, "intent": intent, "theme": theme,
            "highlight": highlight, "image": image,
            "duration": duration, "prompt": prompt, "state": "pending"}


def parse_memo(content: str) -> str | None:
    text = content.strip()
    if not text.startswith("上映メモ"):
        return None
    head, _, rest = text.partition("\n")
    head = re.sub(r"^上映メモ[:：]?", "", head).strip()
    memo = (head + "\n" + rest).strip() if rest else head
    return memo or None


def split_memo_edit(memo: str) -> tuple[str, str | None]:
    """Split the 編集： line out of a screening memo. The memo body
    (what the sisters and the diary cycle read) never carries the
    edit instruction; the edit text is stored separately."""
    body_lines: list[str] = []
    edit_text: str | None = None
    for ln in memo.splitlines():
        s = ln.strip()
        if s.startswith("編集：") or s.startswith("編集:"):
            edit_text = s[len("編集"):].lstrip("：:").strip()
            continue
        body_lines.append(ln)
    return "\n".join(body_lines).strip(), edit_text


def parse_reject(content: str) -> str | None:
    """「vlog却下：<理由>」 — Luna (the director) closes a take
    without screening it. Returns the reason, or None."""
    text = content.strip()
    if not text.startswith("vlog却下"):
        return None
    head, _, rest = text.partition("\n")
    reason = re.sub(r"^vlog却下[:：]?", "", head).strip()
    reason = (reason + "\n" + rest).strip() if rest else reason
    return reason or "理由の記入なし"


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
            reason = parse_reject(content)
            if reason is not None:
                # Close the OLDEST in-flight take (pending or
                # previewed) without screening it, so it can never
                # take a memo or reach #vlog. Oldest, not "the only
                # one": a retake's preview can already be waiting
                # while the failed take is still open (2026-11-25,
                # takes 1 and 2 of 蕾のそばで) — the one being
                # rejected is always the earlier take.
                inflight = sorted(
                    requests_by_state(self.out_dir, "previewed")
                    + requests_by_state(self.out_dir, "pending"),
                    key=lambda t: t[0].name)
                if inflight:
                    path, req = inflight[0]
                    req["state"] = "rejected"
                    req["reject_reason"] = reason
                    _save(path, req)
                    print(f"vlog: take rejected '{req['title']}': {reason}",
                          flush=True)
                    acted = "reject"
                continue
            memo = parse_memo(content)
            if memo:
                previewed = requests_by_state(self.out_dir, "previewed")
                if len(previewed) == 1:
                    path, req = previewed[0]
                    body, edit_text = split_memo_edit(memo)
                    req["memo"] = body
                    req["edit"] = edit_text
                    req["state"] = "memo_ready"
                    _save(path, req)
                    print(f"vlog: screening memo received for "
                          f"'{req['title']}'"
                          + (f" (edit: {edit_text})" if edit_text else ""),
                          flush=True)
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


def run_edit(out_dir: Path, poster) -> bool:
    """Apply the memo's edit instruction to the oldest memo-ready
    take. Passthrough when there is no instruction. Failure closes
    the request as failed and reaches only the work channel — an
    unedited cut is never screened silently in its place."""
    ready = requests_by_state(out_dir, "memo_ready")
    if not ready:
        return False
    path, req = ready[0]
    print(f"vlog: edit starting '{req['title']}' "
          f"(edit: {req.get('edit') or 'そのまま'})", flush=True)
    src = _req_dir(out_dir) / f"{path.stem}.mp4"
    try:
        spec = edit_mod.parse_edit_spec(req.get("edit"))
        if edit_mod.is_passthrough(spec):
            req["edited_file"] = src.name
        else:
            out_video = _req_dir(out_dir) / f"{path.stem}-edited.mp4"
            edit_mod.apply_edit(src, spec, out_video)
            req["edited_file"] = out_video.name
            if spec["cover"] is not None:
                cover = _req_dir(out_dir) / f"{path.stem}-cover.png"
                edit_mod.extract_cover(out_video, spec["cover"], cover)
                req["cover_file"] = cover.name
        req["edit_spec"] = spec
        req["state"] = "edited"
        print(f"vlog: edit done '{req['title']}' -> {req['edited_file']}",
              flush=True)
    except Exception as e:
        print(f"vlog: edit FAILED '{req['title']}': {e}", flush=True)
        poster.post("work", "vlog",
                    f"vlogの編集が失敗したよ: {e}\nタイトル: {req['title']}")
        req["state"] = "failed"
    _save(path, req)
    return True


def _impression(llm, member: dict, req: dict) -> str:
    prompt = (
        _persona_block(member)
        + f"\n\nルナが監督した短い動画「{req['title']}」の上映を見たところです。"
        + (f"\nテーマ: {req['theme']}" if req.get("theme") else "")
        + (f"\n見どころ: {req['highlight']}" if req.get("highlight") else "")
        + f"\n意図（何を見せたいか）: {req['intent']}"
        + f"\n実際に映っていたこと（ルナの上映メモ）: {req['memo']}"
        + "\n感想を、台詞ひとつ分だけ、「」で囲んで短く書いてください。"
        + "作った側ではなく、見た側として受け取ってください。")
    text = extract_line(llm.generate(prompt, member["id"]))
    if is_broken_line(text):
        text = extract_line(llm.generate(prompt, member["id"]))
    return text


def run_stage2(out_dir: Path, llm, poster, date, event_minutes: int) -> dict | None:
    """Post the oldest edited vlog to #vlog with the sisters'
    impressions, and join the day's cycle. The presentation is the
    title plus the audience-facing テーマ / 見どころ; the 意図
    stays the director's private note (material for impressions,
    never part of the screening post). Returns the diary-pool
    event, or None when nothing was ready."""
    ready = requests_by_state(out_dir, "edited")
    if not ready:
        return None
    path, req = ready[0]
    print(f"vlog: stage 2 (screening) starting '{req['title']}'", flush=True)
    out_video = _req_dir(out_dir) / req.get("edited_file", f"{path.stem}.mp4")
    if req.get("cover_file"):
        poster.post("vlog", "ルナ", f"表紙：{req['title']}",
                    file_path=_req_dir(out_dir) / req["cover_file"])
    lines = [req["title"]]
    if req.get("theme"):
        lines.append(f"テーマ：{req['theme']}")
    if req.get("highlight"):
        lines.append(f"見どころ：{req['highlight']}")
    poster.post("vlog", "ルナ", "\n".join(lines), file_path=out_video)
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
        "url": "", "topic": req["title"], "minutes": event_minutes,
        "theme": req.get("theme", ""), "highlight": req.get("highlight", "")})
    quote = impressions[0]["text"] if impressions else req["memo"]
    return {"minutes": event_minutes, "member": "ルナ",
            "topic": req["title"], "quote": quote, "open": True}
