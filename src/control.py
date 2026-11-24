"""Discord-side control: the pause switch, operable from chat.

The house polls the work channel (#作業場, private to Ruru and the
bot) about once a minute. A message starting with 止めて from the
guild owner — or from the bot account itself, which is how Luna
relays a spoken request — raises the pause; 再開して lifts it.
The switch itself is still the plain out/PAUSE file: this module
only creates and removes it, and confirms in the channel.

Why polling: the bot speaks REST only (no gateway), and a minute of
latency is fine for a switch that is judged at job boundaries.
"""

import json
import time
import urllib.request
from pathlib import Path

PAUSE_WORDS = ("止めて", "止める", "ストップ", "pause")
RESUME_WORDS = ("再開して", "再開", "resume")


def parse_command(content: str) -> str | None:
    text = content.strip()
    if any(text.startswith(w) for w in PAUSE_WORDS):
        return "pause"
    if any(text.startswith(w) for w in RESUME_WORDS):
        return "resume"
    return None


class DiscordControl:
    def __init__(self, token: str, work_channel_id: str, pause_path: Path,
                 poster, state_path: Path, allowed_authors: set[str],
                 fetch=None):
        self.token = token if token.startswith("Bot ") else f"Bot {token}"
        self.channel_id = work_channel_id
        self.pause_path = pause_path
        self.poster = poster
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
        """Returns the action taken ('pause'/'resume') or None."""
        try:
            messages = self.fetch(self.last_seen)
        except Exception:
            return None
        if self.last_seen is None:
            # First contact: take the newest message as the baseline
            # without acting on history — a command counts only when
            # it arrives while the house is listening.
            if messages:
                self.last_seen = messages[0]["id"]
                self._save_state()
            return None
        action = None
        for msg in reversed(messages):  # oldest first
            self.last_seen = msg["id"]
            author = (msg.get("author") or {}).get("id")
            if author not in self.allowed:
                continue
            cmd = parse_command(msg.get("content", ""))
            if cmd == "pause" and not self.pause_path.exists():
                self.pause_path.parent.mkdir(parents=True, exist_ok=True)
                self.pause_path.touch()
                self.poster.post("work", "ルナ",
                                 "止めたよ。次のジョブから手放すね。再開は「再開して」で。")
                action = "pause"
            elif cmd == "resume" and self.pause_path.exists():
                self.pause_path.unlink()
                self.poster.post("work", "ルナ",
                                 "再開したよ。次のジョブから普通に動くね。")
                action = "resume"
        if messages:
            self._save_state()
        return action

    def run_forever(self, interval_seconds: int = 60):
        while True:
            self.poll_once()
            time.sleep(interval_seconds)
