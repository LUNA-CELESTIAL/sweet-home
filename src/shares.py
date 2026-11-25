"""Shares watcher: things posted in the house become topics.

Polls the living and vlog channels (REST, about once a minute) for
messages from the guild owner that carry a link or an attachment —
a video someone made, an article, a picture. Each is recorded in
out/shares-<date>.json; the living room's first cluster of the day
picks the newest morning share up as its seed (see cycle.py).

The bot's own posts are the house talking, not shares, so only the
owner's messages count. Baseline rule as in control.py: history
from before the watcher started is never acted on.
"""

import json
import time
import urllib.request
from pathlib import Path

from cycle import append_share, share_topic

_URL_HINTS = ("http://", "https://")


class SharesWatcher:
    def __init__(self, token: str, channel_ids: list[str], owner_id: str,
                 out_dir: Path, state_path: Path, tz, fetch=None):
        self.token = token if token.startswith("Bot ") else f"Bot {token}"
        self.channel_ids = channel_ids
        self.owner_id = str(owner_id)
        self.out_dir = out_dir
        self.state_path = state_path
        self.tz = tz
        self.fetch = fetch or self._fetch_messages
        self.last_seen: dict[str, str | None] = {c: None for c in channel_ids}
        if state_path.exists():
            try:
                saved = json.loads(state_path.read_text(encoding="utf-8"))
                for c in channel_ids:
                    self.last_seen[c] = saved.get(c)
            except Exception:
                pass

    def _fetch_messages(self, channel_id: str, after: str | None) -> list[dict]:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=10"
        if after:
            url += f"&after={after}"
        req = urllib.request.Request(
            url, headers={"Authorization": self.token, "User-Agent": "sweet-home/0.1"})
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read())

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.last_seen), encoding="utf-8")

    def poll_once(self) -> list[dict]:
        import datetime
        found: list[dict] = []
        for channel_id in self.channel_ids:
            try:
                messages = self.fetch(channel_id, self.last_seen[channel_id])
            except Exception:
                continue
            if self.last_seen[channel_id] is None:
                if messages:
                    self.last_seen[channel_id] = messages[0]["id"]
                else:
                    # Sentinel baseline for an empty channel, so
                    # the first real post is processed (see
                    # experiment.py).
                    self.last_seen[channel_id] = "0"
                self._save_state()
                continue
            for msg in reversed(messages):  # oldest first
                self.last_seen[channel_id] = msg["id"]
                if str((msg.get("author") or {}).get("id")) != self.owner_id:
                    continue
                content = msg.get("content", "") or ""
                attachments = msg.get("attachments") or []
                url = ""
                for token in content.split():
                    if token.startswith(_URL_HINTS):
                        url = token
                        break
                if not url and attachments:
                    url = attachments[0].get("url", "")
                if not url and not attachments:
                    continue
                has_video = any((a.get("content_type") or "").startswith("video/")
                                for a in attachments)
                has_image = any((a.get("content_type") or "").startswith("image/")
                                for a in attachments)
                ts = datetime.datetime.fromisoformat(
                    msg["timestamp"].replace("Z", "+00:00")).astimezone(self.tz)
                share = {
                    "id": msg["id"],
                    "member": "るる",
                    "text": content,
                    "url": url,
                    "topic": share_topic(content, has_video, has_image),
                    "minutes": ts.hour * 60 + ts.minute,
                }
                append_share(self.out_dir, ts.date().isoformat(), share)
                found.append(share)
            if messages:
                self._save_state()
        return found

    def run_forever(self, interval_seconds: int = 60):
        while True:
            self.poll_once()
            time.sleep(interval_seconds)
