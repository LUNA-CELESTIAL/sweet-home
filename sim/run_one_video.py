"""Generate exactly ONE duty video on the real machine (thermal check).

Deliberately single-shot: the old bot's failure was unbounded video
generation. This trial measures time and output for one 5s video so
the heat cost is known before video joins the daily plan.

Usage: python3 sim/run_one_video.py [member_id] [slot]
Defaults: stella evening. Needs .env with COMFYUI_WORKFLOW_PATH.
Watch GPU temperature in another terminal while it runs.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from config import load_env  # noqa: E402
from personas import by_id  # noqa: E402
from video import ComfyUIClient  # noqa: E402


def main():
    member_id = sys.argv[1] if len(sys.argv) > 1 else "stella"
    slot = sys.argv[2] if len(sys.argv) > 2 else "evening"
    env_path = ROOT / ".env"
    cfg = {}
    if env_path.exists():
        cfg = load_env(env_path)
    import os
    cfg.update({k: v for k, v in os.environ.items() if k.isupper()})
    wf = cfg.get("COMFYUI_WORKFLOW_PATH", "")
    if not wf or wf.startswith("（"):
        print("COMFYUI_WORKFLOW_PATH is not set in .env yet.")
        return
    client = ComfyUIClient(cfg.get("COMFYUI_BASE_URL", "http://localhost:8188"), wf)
    member = by_id(member_id)
    out = ROOT / "out" / "video" / f"trial-{member_id}-{slot}.mp4"
    start = time.time()
    client.generate(member, slot, 42, out)
    elapsed = time.time() - start
    print(f"done: {out} ({out.stat().st_size // 1024} KB) in {elapsed:.0f}s "
          f"for {member['name']} / {slot}")


if __name__ == "__main__":
    main()
