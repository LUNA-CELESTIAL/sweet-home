"""One simulated day for the Step 3 scheduler prototype.

Scenario:
- duty videos at 09:00 / 20:00 (protected)
- 4 chat clusters requested, budget is 3
- 5 vlog requests, video budget is 6 total (2 duty + max 4 vlog)
- GPU is hot (90C) between 13:00 and 16:00: vlogs must postpone, duty must run
Run: python3 sim/simulate_day.py  (stdlib only)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from scheduler import Job, Scheduler  # noqa: E402

CFG = {
    "VIDEO_DAILY_LIMIT": 6,
    "CHAT_CLUSTERS_PER_DAY": 3,
    "CHAT_POST_INTERVAL_MIN_MINUTES": 3,
    "VIDEO_MIN_INTERVAL_MINUTES": 30,
    "GPU_TEMP_LIMIT_C": 85,
}


def hm(h, m=0):
    return h * 60 + m


def fmt(t):
    return f"{t // 60:02d}:{t % 60:02d}"


def temp_at(t):
    return 90 if hm(13) <= t < hm(16) else 62


def build_jobs():
    jobs = [
        Job("duty_morning", "duty_video", hm(9)),
        Job("duty_night", "duty_video", hm(20)),
        Job("diary", "diary", hm(21, 30)),
    ]
    for i, start in enumerate([hm(9, 20), hm(14), hm(17, 30), hm(19)], start=1):
        for k in range(4):
            jobs.append(Job(f"chat_c{i}_{k + 1}", "chat_post", start, cluster=f"c{i}"))
    for i, start in enumerate([hm(10, 30), hm(12), hm(13, 30), hm(15), hm(16, 30)], start=1):
        jobs.append(Job(f"vlog_{i}", "vlog_video", start))
    return jobs


def main():
    log = Scheduler(CFG, temp_at).run(build_jobs())
    for e in log:
        print(f"{fmt(e.time)}  {e.action:9s}  {e.name}  {e.note}".rstrip())

    runs = [e for e in log if e.action == "run"]
    videos = [e for e in runs if e.name.startswith(("duty", "vlog"))]
    heavy_times = sorted(e.time for e in videos)
    clusters = {e.name.split("_")[1] for e in runs if e.name.startswith("chat_")}

    assert len(videos) <= CFG["VIDEO_DAILY_LIMIT"], "video budget exceeded"
    assert all(b - a >= CFG["VIDEO_MIN_INTERVAL_MINUTES"] for a, b in zip(heavy_times, heavy_times[1:])), "heavy interval violated"
    assert len(clusters) <= CFG["CHAT_CLUSTERS_PER_DAY"], "cluster budget exceeded"
    assert any(e.name == "duty_night" and e.action == "run" for e in log), "duty must run"
    assert not any(e.name.startswith("vlog") and e.action == "run" and hm(13) <= e.time < hm(16) for e in log), "vlog ran while hot"
    times = [e.time for e in runs]
    assert len(times) == len(set(times)), "jobs overlapped"
    print("\nALL CHECKS PASSED")
    print(f"videos run: {len(videos)} / {CFG['VIDEO_DAILY_LIMIT']}, clusters run: {len(clusters)} / {CFG['CHAT_CLUSTERS_PER_DAY']}")


if __name__ == "__main__":
    main()
