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
        # Image pace: stills use their own shorter interval — after
        # the same generation, an image waits out only 300s, not the
        # video's 1800s (2026-11-27).
        t2 = {"now": 1000.0, "slept": []}
        client2 = ComfyUIClient("http://stub", str(wf), pace_seconds=1800,
                                image_pace_seconds=300,
                                clock=lambda: t2["now"],
                                sleep=lambda s: (t2["slept"].append(s), t2.__setitem__("now", t2["now"] + s)))
        client2.wait_ready = lambda **kw: None
        client2._last_gen_at = 1000.0
        t2["now"] = 1100.0
        try:
            client2.generate_image({"1": {"inputs": {}}}, Path(td) / "y.png")
        except Exception:
            pass  # stub server; only the pacing sleep matters
        assert t2["slept"] and abs(t2["slept"][0] - 200) < 1, t2["slept"]
    # Restart: jobs already done are skipped, completions are reported.
    clock2 = FakeClock()
    clock2.minutes = 6 * 60
    ran2: list[str] = []
    jobs2 = [TimedJob(7 * 60, "morning duty", lambda: ran2.append("morning"),
                      heavy=True, protected=True),
             TimedJob(10 * 60, "living 1", lambda: ran2.append("living"))]
    done_reported: list[str] = []
    ex2 = Executor(clock2.now, clock2.sleep, temp_c=lambda: 50.0, temp_limit_c=85)
    log2 = ex2.run(jobs2, skip={"morning duty"}, on_done=done_reported.append)
    assert ran2 == ["living"], ran2
    assert done_reported == ["living 1"], done_reported
    assert any(e["action"] == "skipped (done)" for e in log2)

    # Heavy cooldown: after a video job, 10 minutes pass before the
    # next job starts, even when the next job is already due.
    clock3 = FakeClock()
    order3: list[tuple[str, float]] = []
    jobs3 = [TimedJob(0, "morning duty", lambda: order3.append(("morning", clock3.minutes)),
                      heavy=True, protected=True),
             TimedJob(0, "living 1", lambda: order3.append(("living", clock3.minutes)))]
    ex3 = Executor(clock3.now, clock3.sleep, temp_c=lambda: 50.0, temp_limit_c=85,
                   heavy_cooldown_minutes=10)
    ex3.run(jobs3)
    assert order3 == [("morning", 0.0), ("living", 10.0)], order3

    # Pause flag: every job is let go and reported done, nothing runs.
    ran4: list[str] = []
    done4: list[str] = []
    ex4 = Executor(FakeClock().now, FakeClock().sleep, temp_c=lambda: 50.0, temp_limit_c=85)
    log4 = ex4.run([TimedJob(0, "morning duty", lambda: ran4.append("m"))],
                   on_done=done4.append, paused=lambda: True)
    assert ran4 == [] and done4 == ["morning duty"], (ran4, done4)
    assert log4[0]["action"] == "paused"

    # The pause is judged at the job's own moment: a flag raised
    # while the executor sleeps toward the job still lets it go,
    # and a flag lifted before the moment lets the job run.
    clock5 = FakeClock()
    ran5: list[str] = []
    ex5 = Executor(clock5.now, clock5.sleep, temp_c=lambda: 50.0, temp_limit_c=85)
    ex5.run([TimedJob(60, "living 1", lambda: ran5.append("living"))],
            paused=lambda: clock5.minutes >= 30)
    assert ran5 == [], ran5
    clock6 = FakeClock()
    ran6: list[str] = []
    ex6 = Executor(clock6.now, clock6.sleep, temp_c=lambda: 50.0, temp_limit_c=85)
    ex6.run([TimedJob(60, "living 1", lambda: ran6.append("living"))],
            paused=lambda: clock6.minutes < 30)
    assert ran6 == ["living"], ran6

    # Time-managed restarts (2026-11-26): a job is recorded as
    # started BEFORE it runs, so a house that dies mid-job never
    # re-runs it from the top on the next boot.
    clock7 = FakeClock()
    ran7: list[str] = []
    started7: list[str] = []
    ex7 = Executor(clock7.now, clock7.sleep, temp_c=lambda: 50.0, temp_limit_c=85)
    ex7.run([TimedJob(0, "living 3", lambda: ran7.append("living"))],
            on_start=started7.append)
    assert ran7 == ["living"] and started7 == ["living 3"], (ran7, started7)
    ran7b: list[str] = []
    ex7b = Executor(clock7.now, clock7.sleep, temp_c=lambda: 50.0, temp_limit_c=85)
    ex7b.run([TimedJob(0, "living 3", lambda: ran7b.append("living"))],
             skip=set(started7))
    assert ran7b == [], ran7b

    # A job far past its slot at boot is let go, not caught up —
    # and marked done so nothing reconsiders it.
    clock8 = FakeClock()
    clock8.minutes = 12 * 60
    ran8: list[str] = []
    done8: list[str] = []
    ex8 = Executor(clock8.now, clock8.sleep, temp_c=lambda: 50.0, temp_limit_c=85,
                   grace_minutes=30)
    log8 = ex8.run([TimedJob(10 * 60 + 30, "living 1", lambda: ran8.append("x"))],
                   on_done=done8.append)
    assert ran8 == [] and done8 == ["living 1"], (ran8, done8)
    assert log8[0]["action"] == "let go (past its time)", log8

    # Within the grace, a slightly late job still runs (a house
    # that boots at 20:05 still does the 20:00 duty).
    clock9 = FakeClock()
    clock9.minutes = 20 * 60 + 5
    ran9: list[str] = []
    ex9 = Executor(clock9.now, clock9.sleep, temp_c=lambda: 50.0, temp_limit_c=85,
                   grace_minutes=30)
    ex9.run([TimedJob(20 * 60, "evening duty", lambda: ran9.append("duty"),
                      heavy=True, protected=True)])
    assert ran9 == ["duty"], ran9
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
