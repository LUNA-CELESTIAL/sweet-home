"""Posting boundary. Offline runs use ConsolePoster (prints and
records); live runs use DiscordPoster (REST, token from env).
Nothing else in the codebase knows where posts go.
"""

import json
import urllib.request


class ConsolePoster:
    def __init__(self):
        self.posts: list[dict] = []

    def post(self, channel: str, author: str, text: str) -> None:
        self.posts.append({"channel": channel, "author": author, "text": text})
        print(f"[{channel} / {author}] {text}")


class DiscordPoster:
    def __init__(self, token: str, channel_ids: dict[str, str]):
        if not token or token.startswith("（"):
            raise ValueError("DISCORD_BOT_TOKEN is unset or still a placeholder")
        self.token = token if token.startswith("Bot ") else f"Bot {token}"
        self.channel_ids = channel_ids

    def post(self, channel: str, author: str, text: str) -> None:
        cid = self.channel_ids[channel]
        body = json.dumps({"content": f"**{author}**\n{text}"}).encode()
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{cid}/messages", data=body,
            method="POST",
            headers={"Authorization": self.token, "Content-Type": "application/json",
                     "User-Agent": "sweet-home/0.1"})
        with urllib.request.urlopen(req, timeout=60) as res:
            res.read()
