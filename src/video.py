"""ComfyUI boundary: workflow template -> 5-second video file.

The workflow JSON lives outside the code (COMFYUI_WORKFLOW_PATH in
env); the template may contain {prompt} and {seed} placeholders in
string values. The client queues the prompt, polls history, and
downloads the first produced video/gif file. Heavy by definition:
callers must go through the scheduler's budget/interval/thermal
rules, never call this directly in a loop.
"""

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


def fill_template(node, prompt: str, seed: int):
    if isinstance(node, dict):
        return {k: fill_template(v, prompt, seed) for k, v in node.items()}
    if isinstance(node, list):
        return [fill_template(v, prompt, seed) for v in node]
    if isinstance(node, str):
        return node.replace("{prompt}", prompt).replace("{seed}", str(seed))
    return node


def build_video_prompt(member: dict, slot: str) -> str:
    scene = "morning greeting, waving hand, bright room" if slot == "morning" \
        else "evening greeting, soft lamp light, waving hand"
    return f"chibi anime girl character {member['name']}, {scene}, gentle smile, 5 seconds, loopable"


class ComfyUIClient:
    def __init__(self, base_url: str, workflow_path: str, poll_seconds: int = 10,
                 timeout_seconds: int = 1800):
        if not workflow_path or workflow_path.startswith("（"):
            raise ValueError("COMFYUI_WORKFLOW_PATH is unset or still a placeholder")
        self.base_url = base_url.rstrip("/")
        self.workflow = json.loads(Path(workflow_path).read_text(encoding="utf-8"))
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def _json(self, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read())

    def _bytes(self, path: str) -> bytes:
        with urllib.request.urlopen(self.base_url + path, timeout=300) as res:
            return res.read()

    def generate(self, member: dict, slot: str, seed: int, out_path: Path) -> Path:
        workflow = fill_template(self.workflow, build_video_prompt(member, slot), seed)
        queued = self._json("/prompt", {"prompt": workflow})
        prompt_id = queued["prompt_id"]
        waited = 0
        while True:
            history = self._json(f"/history/{prompt_id}")
            entry = history.get(prompt_id) or {}
            outputs = entry.get("outputs") or {}
            for node_out in outputs.values():
                for kind in ("videos", "gifs", "images"):
                    files = node_out.get(kind) or []
                    if files:
                        f = files[0]
                        q = urllib.parse.urlencode(
                            {"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                             "type": f.get("type", "output")})
                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        out_path.write_bytes(self._bytes(f"/view?{q}"))
                        return out_path
            if waited >= self.timeout_seconds:
                raise TimeoutError(f"ComfyUI job {prompt_id} did not finish")
            time.sleep(self.poll_seconds)
            waited += self.poll_seconds
