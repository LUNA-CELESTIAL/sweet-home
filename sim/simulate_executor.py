"""Executor + video pacing verification in compressed time (stdlib).

Checks: jobs run in planned order at planned times; a hot, skippable
heavy job is dropped while a protected duty job still runs; and the
video client's pace makes two back-to-back generations wait out the
full interval even when called directly.
Run: python3 sim/simulate_executor.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from executor import Executor, TimedJob  # noqa: E402
from video import ComfyUIClient  # noqa: E402


class FakeClock:
    def __init__(self):
        self.minutes = 0.0
        self.slept: list[float] = []

    def now(self):
        return self.minutes

    def sleep(self, m):
        self.slept.append(m)
        self.minutes += m


def main():
    clock = FakeClock()
    ran = []
    jobs = [
        TimedJob(21 * 60, "evening duty", lambda: ran.append("evening"),
                 heavy=True, protected=True),
        TimedJob(7 * 60, "morning duty", lambda: ran.append("morning"),
                 heavy=True, protected=True),
        TimedJob(12 * 60, "vlog", lambda: ran.append("vlog"), heavy=True),
        TimedJob(10 * 60 + 30, "living", lambda: ran.append("living")),
    ]
    hot = Executor(clock.now, clock.sleep, temp_c=lambda: 95.0, temp_limit_c=85)
    log = hot.run(jobs)
    assert ran == ["morning", "living", "evening"], ran  # vlog dropped, duty protected
    assert [e["name"] for e in log if e["action"] == "run"] == ["morning duty", "living", "evening duty"]
    assert any(e["action"] == "dropped" and e["name"] == "vlog" for e in log)
    assert clock.minutes == 21 * 60  # slept exactly up to the last job

    # Pacing: a client with pace=1800s called twice in a row sleeps ~1800s once.
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        wf = Path(td) / "w.json"
        wf.write_text(json.dumps({"1": {"inputs": {}}}), encoding="utf-8")
        t = {"now": 1000.0, "slept": []}
        client = ComfyUIClient("http://stub", str(wf), pace_seconds=1800,
                               clock=lambda: t["now"],
                               sleep=lambda s: (t["slept"].append(s), t.__setitem__("now", t["now"] + s)))
        client.wait_ready = lambda **kw: None  # stub the server away
        client._last_gen_at = 1000.0  # as if a video just finished
        t["now"] = 1100.0
        try:
            client.generate({"id": "luna", "name": "ルナ"}, "morning", 1, Path(td) / "x.mp4")
        except Exception:
            pass  # the stub server is not there; only the pacing sleep matters
        assert t["slept"] and abs(t["slept"][0] - 1700) < 1, t["slept"]
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
