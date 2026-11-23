"""sweet-home resident entry point.

Modes:
  --once   run today's full day once (poster depends on RUN_MODE)
  --serve  tick every 30s and run each job when its time comes
           (duty 09:00 / cluster 10:30 / duty 20:00 / diary 21:30)

Safety: live posting requires RUN_MODE=live AND no placeholder
values in the required env keys; otherwise the ConsolePoster is
used and nothing leaves the machine.
"""

import argparse
import datetime
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import check_live_ready, load_env  # noqa: E402
from day import run_day  # noqa: E402
from llm import OllamaClient  # noqa: E402
from poster import ConsolePoster, DiscordPoster  # noqa: E402
from voice import VoicevoxClient, speaker_ids_from_config  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

DEMO_SEED = {
    "topic": "Pingツール", "sourceMember": "ステラ",
    "quote": "機能の数だけ手を出すのではなく、静かな回線の中で本当に必要なものを選ぶ目配り",
    "note": "ステラのPingツールの話、途中で終わっていたのが気になってる。",
}
DEMO_EVENTS = [
    {"minutes": 9 * 60, "member": "こはく", "topic": "朝の当番"},
    {"minutes": 10 * 60 + 30, "member": "スピカ", "topic": "Pingツールの続き", "open": True,
     "quote": "実際に小さなパケットを放って、どの往復だけが返るか測ってみようかな"},
    {"minutes": 15 * 60, "member": "ルナ", "topic": "実生成の会話が初めて成立した", "kind": "home"},
]


def load_config() -> dict | None:
    """Config from the .env file when present; otherwise from the
    process environment (docker compose env_file injects values that
    way, and the .env file itself is never copied into the image)."""
    env_path = ROOT / ".env"
    cfg: dict[str, str] = {}
    if env_path.exists():
        cfg.update(load_env(env_path))
    cfg.update({k: v for k, v in os.environ.items()
                if k.isupper() and (k in cfg or "_" in k)})
    if "OLLAMA_MODEL" not in cfg and "RUN_MODE" not in cfg:
        return None
    return cfg


def build_runtime(cfg: dict):
    problems = check_live_ready(cfg)
    live = cfg.get("RUN_MODE") == "live" and not problems
    if cfg.get("RUN_MODE") == "live" and problems:
        print(f"RUN_MODE=live but not ready, falling back to offline: {problems}")
    llm = OllamaClient(cfg.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                       cfg.get("OLLAMA_MODEL", ""))
    if live:
        ids = {"duty": cfg["DISCORD_CHANNEL_DUTY_ID"], "living": cfg["DISCORD_CHANNEL_LIVING_ID"],
               "vlog": cfg["DISCORD_CHANNEL_VLOG_ID"], "diary": cfg["DISCORD_CHANNEL_DIARY_ID"],
               "work": cfg["DISCORD_CHANNEL_WORK_ID"]}
        return DiscordPoster(cfg["DISCORD_BOT_TOKEN"], ids), llm, True
    return ConsolePoster(), llm, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--serve", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if cfg is None:
        print("No config found: no .env file and no environment variables. "
              "cp .env.example .env (for docker compose, env_file also works).")
        return
    poster, llm, live = build_runtime(cfg)
    ids = speaker_ids_from_config(cfg)
    voice = (VoicevoxClient(cfg.get("VOICEVOX_BASE_URL", "http://localhost:50021"), ids)
             if ids else None)
    print(f"sweet-home starting (live={live}, voice={'on' if voice else 'off'})")

    if args.once:
        run_day(llm, poster, datetime.date.today(), "晴れ", DEMO_SEED, DEMO_EVENTS,
                ROOT / "out", site_export_path=ROOT / "export" / "diary.json", voice=voice)
        print("day complete")
        return

    if args.serve:
        done: set[tuple[str, str]] = set()
        while True:
            now = datetime.datetime.now()
            key = (now.date().isoformat(), f"{now.hour:02d}:{now.minute:02d}")
            if key not in done and (now.hour, now.minute) in {(21, 30)}:
                # v1: the whole day is produced by the diary-time run in
                # serve mode trials; per-job split arrives with Step 5.
                run_day(llm, poster, now.date(), "晴れ", DEMO_SEED, DEMO_EVENTS,
                        ROOT / "out", site_export_path=ROOT / "export" / "diary.json", voice=voice)
                done.add(key)
            time.sleep(30)


if __name__ == "__main__":
    main()
