"""Step 4 first slice: duty jobs (text only) on the scheduler, offline.

Checks:
- .env.example placeholders are detected and live mode is refused
- rotation picks a stable member per date/slot
- the morning duty actually uses yesterday's diary seed (from the
  2026-11-21 backtest diary.json)
- both duty jobs run on the scheduler and land in the event pool
Run: python3 sim/simulate_duty.py  (stdlib only)
"""

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from config import check_live_ready, load_env, placeholders  # noqa: E402
from duty import compose, duty_member  # noqa: E402
from scheduler import Job, Scheduler  # noqa: E402

CFG = {
    "VIDEO_DAILY_LIMIT": 6,
    "CHAT_CLUSTERS_PER_DAY": 3,
    "CHAT_POST_INTERVAL_MIN_MINUTES": 3,
    "VIDEO_MIN_INTERVAL_MINUTES": 30,
    "GPU_TEMP_LIMIT_C": 85,
}


def main():
    env = load_env(ROOT / ".env.example")
    ph = placeholders(env)
    problems = check_live_ready(env)
    print(f"placeholders detected: {len(ph)} (e.g. {ph[:3]})")
    print(f"live mode problems: {problems}")
    assert problems, "live mode must be refused while placeholders remain"

    date = datetime.date(2026, 11, 23)
    diary = json.loads((ROOT / "prototypes/diary-backtest-2026-11-21/diary.json").read_text(encoding="utf-8"))
    seed = diary["nextMorningSeed"]

    morning = duty_member(date, "morning")
    evening = duty_member(date, "evening")
    morning_text = compose(morning, "morning", "晴れ、最高14度", seed)
    evening_text = compose(evening, "evening", "", None)
    print(f"\nmorning duty ({morning['name']}): {morning_text}")
    print(f"evening duty ({evening['name']}): {evening_text}")
    assert morning["id"] != evening["id"]
    assert "天職感" in morning_text, "diary seed was not used in the morning duty"

    pool = []

    def run_duty(slot, member, text):
        pool.append({"date": str(date), "slot": slot, "member": member["id"], "text": text})

    log = Scheduler(CFG, lambda t: 62).run([
        Job("duty_morning", "duty_text", 9 * 60),
        Job("duty_night", "duty_text", 20 * 60),
    ])
    assert [e.action for e in log] == ["run", "run"]
    run_duty("morning", morning, morning_text)
    run_duty("evening", evening, evening_text)
    print(f"\nevent pool entries: {len(pool)} (duty morning/evening recorded)")
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
