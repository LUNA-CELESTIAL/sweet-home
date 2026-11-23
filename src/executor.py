"""Plan-driven executor: the missing middle between the scheduler's
rules and the day's parts.

Jobs carry a planned time (minutes from midnight). The executor
sleeps until each job's time, checks the thermal guard for skippable
heavy jobs, and runs jobs one at a time, in order. Duty jobs are
protected: they run even when hot. Video spacing is additionally
enforced inside the video client itself (pace), so no path — planned
or manual — can fire two videos back to back in real operation.

Clock, sleep and temperature are injected, so the whole day can be
verified in compressed time.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class TimedJob:
    at: int  # minutes from midnight
    name: str
    fn: Callable[[], None]
    heavy: bool = False
    protected: bool = False  # duty: runs even when hot


class Executor:
    def __init__(self, now_minutes: Callable[[], float], sleep_minutes: Callable[[float], None],
                 temp_c: Callable[[], float], temp_limit_c: float):
        self.now = now_minutes
        self.sleep = sleep_minutes
        self.temp_c = temp_c
        self.temp_limit_c = temp_limit_c
        self.log: list[dict] = []

    def run(self, jobs: list[TimedJob]) -> list[dict]:
        for job in sorted(jobs, key=lambda j: j.at):
            wait = job.at - self.now()
            if wait > 0:
                self.sleep(wait)
            if job.heavy and not job.protected and self.temp_c() >= self.temp_limit_c:
                self.log.append({"name": job.name, "action": "dropped",
                                 "note": "thermal guard", "at": self.now()})
                continue
            job.fn()
            self.log.append({"name": job.name, "action": "run", "at": self.now()})
        return self.log


def day_jobs(day, site_export_path=None) -> list[TimedJob]:
    """The standard day shape. Living clusters spread across the day;
    the diary closes it. Duty video rides inside the duty jobs
    (heavy + protected); vlog jobs join here once vlog exists."""
    return [
        TimedJob(7 * 60, "morning duty", day.morning, heavy=True, protected=True),
        TimedJob(10 * 60 + 30, "living 1", lambda: day.living()),
        TimedJob(14 * 60 + 30, "living 2", lambda: day.living()),
        TimedJob(17 * 60 + 30, "living 3", lambda: day.living()),
        TimedJob(21 * 60, "evening duty", day.evening, heavy=True, protected=True),
        TimedJob(21 * 60 + 30, "diary", lambda: day.diary(site_export_path)),
    ]
