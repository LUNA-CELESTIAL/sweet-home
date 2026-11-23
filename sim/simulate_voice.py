"""VOICEVOX client verification with a local stub engine (stdlib only).

Spins a tiny HTTP server that answers /audio_query and /synthesis,
then checks: the wav lands on disk, both calls carry the sister's
speaker id, and a sister without an id is skipped quietly.
Run: python3 sim/simulate_voice.py
"""

import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from voice import VoicevoxClient, speaker_ids_from_config  # noqa: E402

CALLS = []


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body_in = self.rfile.read(length) if length else b""
        CALLS.append((u.path, parse_qs(u.query), body_in))
        if u.path == "/audio_query":
            body = json.dumps({"stub": True}).encode()
            ctype = "application/json"
        else:
            body = b"RIFFstub-wav-bytes"
            ctype = "audio/wav"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    cfg = {"VOICEVOX_SPEAKER_LUNA": "10", "VOICEVOX_SPEAKER_STELLA": "（話者IDを入れる）"}
    ids = speaker_ids_from_config(cfg)
    assert ids == {"luna": 10}, ids

    client = VoicevoxClient(base, ids)
    with tempfile.TemporaryDirectory() as td:
        out = client.synthesize("luna", "おはよう。", Path(td) / "luna.wav")
        assert out and out.read_bytes().startswith(b"RIFF")
        skipped = client.synthesize("stella", "こんばんは。", Path(td) / "stella.wav")
        assert skipped is None
    speakers = [q["speaker"][0] for _, q, _ in CALLS]
    assert speakers == ["10", "10"], CALLS

    client2 = VoicevoxClient(base, {"sirius": 10})
    with tempfile.TemporaryDirectory() as td:
        client2.synthesize("sirius", "嬉しい時は嬉しいって言うのが一番だよ。", Path(td) / "sirius.wav")
    synth_body = [b for path, _, b in CALLS if path == "/synthesis"][-1]
    assert b'"volumeScale": 1.15' in synth_body and b'"speedScale": 1.02' in synth_body, synth_body
    server.shutdown()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
