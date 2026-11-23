"""Posting boundary. Offline runs use ConsolePoster (prints and
records); live runs use DiscordPoster (REST, token from env).
Nothing else in the codebase knows where posts go.
"""

import json
import mimetypes
import urllib.request
import uuid
from pathlib import Path


def build_multipart(payload: dict, file_path: Path) -> tuple[bytes, str]:
    boundary = f"sweethome{uuid.uuid4().hex}"
    crlf = b"\r\n"
    body = b""
    body += f"--{boundary}".encode() + crlf
    body += b'Content-Disposition: form-data; name="payload_json"' + crlf
    body += b"Content-Type: application/json" + crlf + crlf
    body += json.dumps(payload).encode() + crlf
    body += f"--{boundary}".encode() + crlf
    body += (f'Content-Disposition: form-data; name="files[0]"; '
             f'filename="{file_path.name}"').encode() + crlf
    ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body += f"Content-Type: {ctype}".encode() + crlf + crlf
    body += file_path.read_bytes() + crlf
    body += f"--{boundary}--".encode() + crlf
    return body, f"multipart/form-data; boundary={boundary}"


class ConsolePoster:
    def __init__(self):
        self.posts: list[dict] = []

    def post(self, channel: str, author: str, text: str, file_path=None) -> None:
        self.posts.append({"channel": channel, "author": author, "text": text,
                           "file": str(file_path) if file_path else None})
        suffix = f" (+file: {file_path})" if file_path else ""
        print(f"[{channel} / {author}] {text}{suffix}")


class DiscordPoster:
    def __init__(self, token: str, channel_ids: dict[str, str]):
        if not token or token.startswith("（"):
            raise ValueError("DISCORD_BOT_TOKEN is unset or still a placeholder")
        self.token = token if token.startswith("Bot ") else f"Bot {token}"
        self.channel_ids = channel_ids

    def post(self, channel: str, author: str, text: str, file_path=None) -> None:
        cid = self.channel_ids[channel]
        payload = {"content": f"**{author}**\n{text}"}
        if file_path is not None:
            body, ctype = build_multipart(payload, Path(file_path))
        else:
            body = json.dumps(payload).encode()
            ctype = "application/json"
        req = urllib.request.Request(
            f"https://discord.com/api/v10/channels/{cid}/messages", data=body,
            method="POST",
            headers={"Authorization": self.token, "Content-Type": ctype,
                     "User-Agent": "sweet-home/0.1"})
        with urllib.request.urlopen(req, timeout=120) as res:
            res.read()
