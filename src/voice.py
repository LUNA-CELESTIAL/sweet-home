"""VOICEVOX boundary: text -> wav file, per-sister speaker ids from env.

The client talks to a local VOICEVOX engine (audio_query -> synthesis).
Speaker ids are never hardcoded: they come from VOICEVOX_SPEAKER_<ID>
env values, and a sister without an id is simply skipped (text-only).
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path


class VoicevoxClient:
    def __init__(self, base_url: str, speaker_ids: dict[str, int]):
        self.base_url = base_url.rstrip("/")
        self.speaker_ids = speaker_ids

    def _post(self, path: str, payload: dict | None, params: dict) -> bytes:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        data = json.dumps(payload).encode() if payload is not None else b""
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as res:
            return res.read()

    def synthesize(self, member_id: str, text: str, out_path: Path) -> Path | None:
        speaker = self.speaker_ids.get(member_id)
        if speaker is None:
            return None
        query = json.loads(self._post("/audio_query", None, {"text": text, "speaker": speaker}))
        wav = self._post("/synthesis", query, {"speaker": speaker})
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(wav)
        return out_path


def speaker_ids_from_config(cfg: dict) -> dict[str, int]:
    ids = {}
    for key, value in cfg.items():
        if key.startswith("VOICEVOX_SPEAKER_") and value and not value.startswith("（"):
            ids[key.removeprefix("VOICEVOX_SPEAKER_").lower()] = int(value)
    return ids
