"""ComfyUI client + multipart poster verification with stubs (stdlib).

A tiny HTTP server answers /prompt, /history/<id> and /view like
ComfyUI. Checks: the workflow template got the built prompt and seed,
the video bytes land on disk, and the poster's multipart body carries
both the payload_json and the file bytes.
Run: python3 sim/simulate_video.py
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
from poster import build_multipart  # noqa: E402
from video import ComfyUIClient  # noqa: E402

SEEN = {}


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        SEEN["prompt"] = json.loads(self.rfile.read(length))
        body = json.dumps({"prompt_id": "abc123"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path.startswith("/history/"):
            body = json.dumps({"abc123": {"outputs": {"9": {"videos": [
                {"filename": "duty.mp4", "subfolder": "", "type": "output"}]}}}}).encode()
            ctype = "application/json"
        elif u.path == "/view":
            assert parse_qs(u.query)["filename"][0] == "duty.mp4"
            body = b"\x00\x00\x00\x18ftypmp42-stub"
            ctype = "video/mp4"
        else:
            body, ctype = b"{}", "application/json"
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

    with tempfile.TemporaryDirectory() as td:
        wf = Path(td) / "workflow.json"
        wf.write_text(json.dumps({"1": {"inputs": {"text": "{prompt}", "seed": "{seed}"}}}),
                      encoding="utf-8")
        client = ComfyUIClient(base, str(wf), poll_seconds=0)
        out = client.generate({"name": "ステラ"}, "evening", 42, Path(td) / "out.mp4")
        assert out.read_bytes().endswith(b"stub")
        sent = SEEN["prompt"]["prompt"]["1"]["inputs"]
        assert "ステラ" in sent["text"] and sent["seed"] == 42, sent

        body, ctype = build_multipart({"content": "こんばんは"}, out)
        assert b"payload_json" in body and b"ftypmp42" in body and "multipart" in ctype
    server.shutdown()
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
