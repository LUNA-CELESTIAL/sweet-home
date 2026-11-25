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
                 temp_c: Callable[[], float], temp_limit_c: float,
                 heavy_cooldown_minutes: float = 0,
                 idle_tick_minutes: float = 5, idle_margin_minutes: float = 15):
        self.now = now_minutes
        self.sleep = sleep_minutes
        self.temp_c = temp_c
        self.temp_limit_c = temp_limit_c
        # Free-time work is checked throughout a wait, not once at
        # its start: the executor wakes every tick and offers the
        # gap to the idle hook (one piece per check). A piece only
        # starts when the margin still fits a render + cooldown
        # before the next planned job — the schedule is known and
        # the day is mostly empty, so there is no reason to sit on
        # idle time (Ruru's correction, 2026-11-25).
        self.idle_tick_minutes = idle_tick_minutes
        self.idle_margin_minutes = idle_margin_minutes
        # After a heavy job (video generation), let the machine and
        # the models settle before the next job — especially before
        # conversation generation, which reloads the LLM. Invisible
        # on a normal day (jobs sit hours apart); it only bites when
        # jobs would otherwise run back to back, e.g. after a restart.
        self.heavy_cooldown_minutes = heavy_cooldown_minutes
        self.log: list[dict] = []

    def _wait_until(self, at: float, idle: Callable[[], bool] | None) -> None:
        """Sleep until `at`, in ticks, offering the gap to free-time
        work as it passes. One piece per check; a piece runs only
        while the margin before `at` still fits it. The final sleep
        lands exactly on `at`, so planned jobs start on time."""
        while True:
            remaining = at - self.now()
            if remaining <= 0:
                return
            if idle is not None and remaining >= self.idle_margin_minutes:
                try:
                    used = idle()
                except Exception:
                    used = False
                if used:
                    # Let things settle a tick before the next check
                    # (the video pace/cooldown live in the client too).
                    self.sleep(min(self.idle_tick_minutes,
                                   max(0.0, at - self.now())))
                    continue
            self.sleep(min(remaining, self.idle_tick_minutes)
                       if idle is not None else remaining)

    def run(self, jobs: list[TimedJob], skip: set[str] | None = None,
            on_done: Callable[[str], None] | None = None,
            paused: Callable[[], bool] | None = None,
            idle: Callable[[], bool] | None = None) -> list[dict]:
        skip = skip or set()
        for job in sorted(jobs, key=lambda j: j.at):
            if job.name in skip:
                # Already completed before a restart: a lived day is
                # not re-lived. (The video seed is per-date, so a
                # re-run would even produce the identical video.)
                self.log.append({"name": job.name, "action": "skipped (done)",
                                 "at": self.now()})
                continue
            self._wait_until(job.at, idle)
            if paused is not None and paused():
                # Experiment mode, checked at the job's own moment:
                # the machine belongs to Ruru's own work right now.
                # The job is let go (and marked done, so lifting the
                # pause does not fire a catch-up burst later).
                self.log.append({"name": job.name, "action": "paused", "at": self.now()})
                if on_done is not None:
                    on_done(job.name)
                continue
            if job.heavy and not job.protected and self.temp_c() >= self.temp_limit_c:
                self.log.append({"name": job.name, "action": "dropped",
                                 "note": "thermal guard", "at": self.now()})
                continue
            job.fn()
            self.log.append({"name": job.name, "action": "run", "at": self.now()})
            if on_done is not None:
                on_done(job.name)
            if job.heavy and self.heavy_cooldown_minutes > 0:
                self.sleep(self.heavy_cooldown_minutes)
                self.log.append({"name": job.name, "action": "cooldown",
                                 "minutes": self.heavy_cooldown_minutes,
                                 "at": self.now()})
        return self.log


def day_jobs(day, site_export_path=None) -> list[TimedJob]:
    """The standard day shape. Living clusters spread across the day;
    the diary closes it. Duty video rides inside the duty jobs
    (heavy + protected); vlog jobs join here once vlog exists."""
    return [
        TimedJob(9 * 60 + 30, "morning duty", day.morning, heavy=True, protected=True),
        TimedJob(10 * 60 + 30, "living 1", lambda: day.living()),
        TimedJob(14 * 60 + 30, "living 2", lambda: day.living()),
        TimedJob(17 * 60 + 30, "living 3", lambda: day.living()),
        TimedJob(20 * 60, "evening duty", day.evening, heavy=True, protected=True),
        TimedJob(21 * 60 + 30, "diary", lambda: day.diary(site_export_path)),
    ]
