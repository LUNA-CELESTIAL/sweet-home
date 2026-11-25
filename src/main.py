"""sweet-home resident entry point.

Modes:
  --once   run today's full day once, back to back (verification)
  --serve  plan-driven operation: morning duty 09:30, living clusters
           10:30 / 14:30 / 17:30, evening duty 20:00, diary 21:30,
           with video pacing and the thermal guard active

Safety: live posting requires RUN_MODE=live AND no placeholder
values in the required env keys; otherwise the ConsolePoster is
used and nothing leaves the machine.
"""

import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import check_live_ready, load_env  # noqa: E402
from day import Day, run_day  # noqa: E402
from executor import Executor, day_jobs  # noqa: E402
from llm import OllamaClient  # noqa: E402
from poster import ConsolePoster, DiscordPoster  # noqa: E402
from video import ComfyUIClient  # noqa: E402
from voice import VoicevoxClient, speaker_ids_from_config  # noqa: E402
from weather import fetch_today  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def house_tz(cfg: dict):
    """The house lives in one timezone. Containers default to UTC, so
    never trust naive local time: resolve TZ_NAME (default Asia/Tokyo)
    explicitly, with a fixed-offset fallback if tzdata is missing."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    name = cfg.get("TZ_NAME", "Asia/Tokyo")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        if name == "Asia/Tokyo":
            return datetime.timezone(datetime.timedelta(hours=9), name)
        raise

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


def print_queue_inventory(out_dir: Path) -> None:
    """What free-time work is waiting, read from the request files
    themselves — so right after a restart the log shows whether the
    queue survived and what will run in the next gap."""
    try:
        import experiment as _exp
        import vlog as _vlog
        exp_titles = []
        for p in _exp.pending_requests(out_dir):
            try:
                exp_titles.append(json.loads(
                    p.read_text(encoding="utf-8")).get("note", p.stem))
            except Exception:
                exp_titles.append(p.stem)
        print(f"queue: experiments pending={len(exp_titles)} {exp_titles}",
              flush=True)
        for state in ("pending", "previewed", "memo_ready"):
            titles = [r.get("title", "?")
                      for _, r in _vlog.requests_by_state(out_dir, state)]
            if titles:
                print(f"queue: vlog {state}={len(titles)} {titles}", flush=True)
    except Exception as e:
        print(f"queue: inventory failed: {e}", flush=True)


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
    video = None
    wf = cfg.get("COMFYUI_WORKFLOW_PATH", "")
    if wf and not wf.startswith("（") and Path(wf).exists():
        video = ComfyUIClient(cfg.get("COMFYUI_BASE_URL", "http://localhost:8188"), wf)
    print(f"sweet-home starting (live={live}, voice={'on' if voice else 'off'}, "
          f"video={'on' if video else 'off'})")

    if args.once:
        run_day(llm, poster, datetime.date.today(),
                fetch_today(cfg.get("WEATHER_AREA_CODE", "130000")),
                DEMO_SEED, DEMO_EVENTS,
                ROOT / "out", site_export_path=ROOT / "export" / "diary.json",
                voice=voice, video=video)
        print("day complete")
        return

    if args.serve:
        TZ = house_tz(cfg)
        if live:
            # Discord-side pause control: poll #作業場 for 止めて /
            # 再開して from the guild owner (or from the bot account,
            # Luna's relay) and work the out/PAUSE switch. Failure to
            # set it up never stops the house.
            try:
                import threading
                import urllib.request as _u
                from control import DiscordControl

                def _get(path):
                    req = _u.Request(f"https://discord.com/api/v10{path}",
                                     headers={"Authorization": poster.token,
                                              "User-Agent": "sweet-home/0.1"})
                    with _u.urlopen(req, timeout=30) as res:
                        return json.loads(res.read())

                me = _get("/users/@me")
                guild = _get(f"/guilds/{cfg['DISCORD_GUILD_ID']}")
                control = DiscordControl(
                    cfg["DISCORD_BOT_TOKEN"], cfg["DISCORD_CHANNEL_WORK_ID"],
                    ROOT / "out" / "PAUSE", poster,
                    ROOT / "out" / "control-state.json",
                    {str(guild["owner_id"]), str(me["id"])})
                threading.Thread(target=control.run_forever, daemon=True).start()
                print("discord control: listening in the work channel")
                from shares import SharesWatcher
                watcher = SharesWatcher(
                    cfg["DISCORD_BOT_TOKEN"],
                    [cfg["DISCORD_CHANNEL_LIVING_ID"], cfg["DISCORD_CHANNEL_VLOG_ID"]],
                    str(guild["owner_id"]), ROOT / "out",
                    ROOT / "out" / "shares-state.json", TZ)
                threading.Thread(target=watcher.run_forever, daemon=True).start()
                print("shares watcher: listening in living/vlog")
                from experiment import ExperimentWatcher
                exp_watcher = ExperimentWatcher(
                    cfg["DISCORD_BOT_TOKEN"], cfg["DISCORD_CHANNEL_WORK_ID"],
                    ROOT / "out", ROOT / "out" / "experiment-state.json",
                    {str(guild["owner_id"]), str(me["id"])})
                threading.Thread(target=exp_watcher.run_forever, daemon=True).start()
                print("experiment watcher: listening in the work channel")
                from vlog import VlogWatcher
                vlog_watcher = VlogWatcher(
                    cfg["DISCORD_BOT_TOKEN"], cfg["DISCORD_CHANNEL_WORK_ID"],
                    ROOT / "out", ROOT / "out" / "vlog-state.json",
                    {str(guild["owner_id"]), str(me["id"])})
                threading.Thread(target=vlog_watcher.run_forever, daemon=True).start()
                print("vlog watcher: listening in the work channel")
            except Exception as e:
                print(f"discord control unavailable (house continues): {e}")
        # Plan-driven: each part of the day runs at its planned time,
        # heavy jobs keep their interval (enforced again inside the
        # video client), and the thermal guard can drop skippable
        # heavy work. Jobs whose time has already passed run at once,
        # so a mid-day start still completes the day.
        pace = int(cfg.get("VIDEO_MIN_INTERVAL_MINUTES", "30")) * 60
        if video is not None:
            video.pace_seconds = pace

        def now_minutes() -> float:
            n = datetime.datetime.now(TZ)
            return n.hour * 60 + n.minute + n.second / 60

        def temp_c() -> float:
            temps = []
            for zone in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
                try:
                    temps.append(int(zone.read_text().strip()) / 1000)
                except Exception:
                    pass
            return max(temps) if temps else 40.0

        import json as _json
        import random as _random
        gap_lo = float(cfg.get("CHAT_POST_INTERVAL_MIN_MINUTES", "3"))
        gap_hi = float(cfg.get("CHAT_POST_INTERVAL_MAX_MINUTES", "3"))

        while True:
            today = datetime.datetime.now(TZ).date()
            state_path = ROOT / "out" / f"state-{today.isoformat()}.json"
            done: set[str] = set()
            if state_path.exists():
                try:
                    done = set(_json.loads(state_path.read_text(encoding="utf-8"))["done"])
                except Exception:
                    done = set()

            def mark_done(name: str, _done=done, _path=state_path):
                _done.add(name)
                _path.parent.mkdir(parents=True, exist_ok=True)
                _path.write_text(_json.dumps({"done": sorted(_done)},
                                             ensure_ascii=False), encoding="utf-8")

            import cycle as _cycle
            seed = _cycle.load_seed(ROOT / "out") or DEMO_SEED
            archive = _cycle.load_archive(ROOT / "out")
            yesterday = (today - datetime.timedelta(days=1)).isoformat()
            related = _cycle.related_past_seed(
                archive, seed["topic"], {yesterday, today.isoformat()})

            def share_seed_loader(_today=today):
                shares = [s for s in _cycle.load_shares(
                    ROOT / "out", _today.isoformat())
                    if s.get("minutes", 0) > 9 * 60 + 30]
                return _cycle.share_to_seed(shares[-1]) if shares else None

            day = Day(llm, poster, today,
                      fetch_today(cfg.get("WEATHER_AREA_CODE", "130000")),
                      seed, [],
                      ROOT / "out", voice=voice, video=video,
                      line_gap_minutes=lambda: _random.uniform(gap_lo, gap_hi),
                      sleeper=lambda m: time.sleep(m * 60),
                      llm_release=getattr(llm, "release", None),
                      share_seed_loader=share_seed_loader,
                      related_seed=related)
            executor = Executor(now_minutes, lambda m: time.sleep(m * 60),
                                temp_c, float(cfg.get("GPU_TEMP_LIMIT_C", "85")),
                                heavy_cooldown_minutes=float(
                                    cfg.get("VIDEO_COOLDOWN_MINUTES", "10")))

            idle_state = {"last": None}

            def idle_free_time() -> bool:
                # Free-time work, one piece per gap, under the same
                # promises: not while paused, not while hot. The
                # video client itself adds pace and queue-wait.
                # Order: experiments, then vlog stage 1 (render),
                # then vlog stage 2 (screening + impressions).
                # The no-work outcomes are logged only when they
                # change, so the log shows state, not noise; pieces
                # that run log themselves in their own modules.
                def note(category: str, message: str | None = None):
                    if category != idle_state["last"]:
                        if message:
                            print(message, flush=True)
                        idle_state["last"] = category

                if (ROOT / "out" / "PAUSE").exists():
                    note("blocked-pause",
                         "free time: hands off (experiment mode / PAUSE)")
                    return False
                if video is None:
                    note("blocked-novid",
                         "free time: no video client — renders cannot run")
                    return False
                if temp_c() >= float(cfg.get("GPU_TEMP_LIMIT_C", "85")):
                    note("blocked-hot", "free time: too hot — holding off")
                    return False
                from experiment import run_pending
                if run_pending(ROOT / "out", video, poster):
                    idle_state["last"] = "ran"
                    return True
                import vlog as _vlog
                if _vlog.run_stage1(ROOT / "out", video, poster):
                    idle_state["last"] = "ran"
                    return True
                event = _vlog.run_stage2(ROOT / "out", llm, poster, today,
                                         int(now_minutes()))
                if event is not None:
                    day.events.append(event)
                    idle_state["last"] = "ran"
                    return True
                note("none", "free time: nothing pending")
                return False

            print_queue_inventory(ROOT / "out")
            executor.run(day_jobs(day, site_export_path=ROOT / "export" / "diary.json"),
                         skip=done, on_done=mark_done,
                         paused=lambda: (ROOT / "out" / "PAUSE").exists(),
                         idle=idle_free_time)
            print(f"day complete ({today})")
            # sleep to just past midnight, then build the next day
            now = datetime.datetime.now(TZ)
            nxt = (now + datetime.timedelta(days=1)).replace(hour=0, minute=5,
                                                             second=0, microsecond=0)
            time.sleep(max(60.0, (nxt - now).total_seconds()))


if __name__ == "__main__":
    main()
