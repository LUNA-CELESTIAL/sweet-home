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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def fill_template(node, prompt: str, seed: int, image: str = ""):
    if isinstance(node, dict):
        return {k: fill_template(v, prompt, seed, image) for k, v in node.items()}
    if isinstance(node, list):
        return [fill_template(v, prompt, seed, image) for v in node]
    if isinstance(node, str):
        if node == "{seed}":
            return seed
        return (node.replace("{prompt}", prompt).replace("{seed}", str(seed))
                .replace("{image}", image))
    return node


# Situation staging, in chibi_bot's shape: the duty line is spoken
# to camera first, then a small closing gesture. The mood describes
# the room and light only — never the character — so it cannot fight
# the first-frame image (the lesson of the identity-drift accident).
SITUATIONS = {
    "sunny": (
        "Looking straight at the camera with a cheerful expression",
        "Smiling softly and waving one hand warmly",
        "bright cozy room with warm sunbeams streaming through a window, cheerful morning atmosphere",
    ),
    "cloudy": (
        "Looking at the viewer with a gentle expression",
        "Blinking softly and offering a warm gentle wave",
        "soft overcast daylight, gentle diffuse morning light, calm atmosphere",
    ),
    "rainy": (
        "Near a window with rain droplets on the glass, turning to the camera",
        "Smiling gently and gesturing softly",
        "cozy room near a rainy window, soft warm indoor light, rainy day atmosphere outside",
    ),
    "night": (
        "Sitting in a cozy dimly lit room, turning to the viewer",
        "Smiling softly and giving a small peaceful night wave",
        "cozy room at night, dim warm lamp light, starry night sky outside the window, relaxed peaceful atmosphere",
    ),
}


def situation_for(slot: str, weather: dict | None) -> str:
    if slot != "morning":
        return "night"
    if weather and weather.get("rainy"):
        return "rainy"
    if weather and any(kw in weather.get("raw", "") for kw in ("くもり", "曇")):
        return "cloudy"
    return "sunny"


def build_video_prompt(member: dict, slot: str, speech: str | None = None,
                       weather: dict | None = None) -> str:
    """Timed H3 prompt. With a speech line, the video speaks it —
    chibi_bot's way: the phrase is embedded in the action segment
    and H3's native audio carries the voice with lip sync. The
    member's actual look anchors identity, as before."""
    look = member.get("look", "chibi anime girl")
    if not speech:
        if slot == "morning":
            action = "waves one hand cheerfully in a morning greeting and smiles at the viewer"
            light = "soft morning light"
        else:
            action = "waves one hand gently in an evening greeting and smiles warmly at the viewer"
            light = "warm evening light"
        return (
            f"Cinematic anime motion, starting from the image of {look}.\n\n"
            f"00:00-00:02 (SHOT 1): The chibi girl steps forward toward the camera with a lively motion, "
            f"her hair swaying naturally in {light}.\n\n"
            f"00:02-00:05 (SHOT 2): She {action}. Creative anime transition, vivid colors, smooth motion."
        )
    pose, closing, mood = SITUATIONS[situation_for(slot, weather)]
    return (
        f"Cinematic 2D anime motion starting from <Picture 1>. The character is {look}. "
        f"Maintain exact character design, face, and clothing from <Picture 1>. "
        f"Natural lip sync animation, speaking in Japanese. {mood}. "
        f"Smooth animation, high quality, zero distortion.\n\n"
        f"[0.00s-3.50s] {pose}, speaking the phrase: \"{speech}\".\n\n"
        f"[3.50s-5.00s] {closing}."
    )


class ComfyUIClient:
    def __init__(self, base_url: str, workflow_path: str, poll_seconds: int = 10,
                 timeout_seconds: int = 1800, pace_seconds: int = 0,
                 clock=time.monotonic, sleep=time.sleep):
        if not workflow_path or workflow_path.startswith("（"):
            raise ValueError("COMFYUI_WORKFLOW_PATH is unset or still a placeholder")
        self.base_url = base_url.rstrip("/")
        self.workflow = json.loads(Path(workflow_path).read_text(encoding="utf-8"))
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds
        # Execution-level spacing: however the jobs were planned, two
        # video generations never fire back to back — generate() waits
        # out the remainder of the interval. 0 disables (verification).
        self.pace_seconds = pace_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_gen_at: float | None = None

    def _json(self, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return json.loads(res.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:2000]
            raise RuntimeError(f"ComfyUI {path} -> HTTP {e.code}: {body}") from e

    def _bytes(self, path: str) -> bytes:
        with urllib.request.urlopen(self.base_url + path, timeout=300) as res:
            return res.read()

    def wait_ready(self, timeout_seconds: int = 180) -> None:
        """ComfyUI takes a while to open its port after (re)start, and
        systemd now restarts it automatically — so poll instead of
        failing on the first connection refused."""
        waited = 0
        while True:
            try:
                self._json("/system_stats")
                return
            except Exception:
                if waited >= timeout_seconds:
                    raise
                time.sleep(5)
                waited += 5

    def generate(self, member: dict, slot: str, seed: int, out_path: Path,
                 image: str | None = None, speech: str | None = None,
                 weather: dict | None = None) -> Path:
        if self.pace_seconds > 0 and self._last_gen_at is not None:
            remaining = self.pace_seconds - (self._clock() - self._last_gen_at)
            if remaining > 0:
                self._sleep(remaining)
        self.wait_ready()
        image = image or f"deformer_{member['id']}.png"
        workflow = fill_template(
            self.workflow, build_video_prompt(member, slot, speech, weather), seed, image)
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
                        self._last_gen_at = self._clock()
                        return out_path
            if waited >= self.timeout_seconds:
                raise TimeoutError(f"ComfyUI job {prompt_id} did not finish")
            time.sleep(self.poll_seconds)
            waited += self.poll_seconds
