"""sweet-home scheduler (Step 3 prototype).

Design rules (see docs/SPEC_v0.md):
- All jobs go through ONE queue and run serially. Nothing overlaps.
- Heavy jobs (video) keep a minimum interval and are postponed by the
  thermal guard; a postponed heavy job YIELDS, so light jobs behind it
  are not blocked. Duty jobs are protected and always run.
- Daily budgets: videos (duty slots are reserved first) and chat
  clusters are capped.
- Chat posts inside one cluster are spaced by minutes, never batched.
- No secrets or IDs here: limits arrive via cfg (from env in real use).

Time is minutes from midnight. temp_at(minute) -> GPU temperature (C),
injected so tests can simulate a hot afternoon.
"""

from dataclasses import dataclass

HEAVY_KINDS = {"duty_video", "vlog_video"}
PRIORITY = {"duty_video": 0, "duty_text": 0, "chat_post": 1, "diary": 2, "vlog_video": 3}


@dataclass
class Job:
    name: str
    kind: str
    earliest: int
    cluster: str | None = None

    @property
    def priority(self) -> int:
        return PRIORITY[self.kind]


@dataclass
class LogEntry:
    time: int
    name: str
    action: str  # "run" | "postponed" | "dropped"
    note: str = ""


class Scheduler:
    def __init__(self, cfg: dict, temp_at):
        self.cfg = cfg
        self.temp_at = temp_at
        self.last_any = -1
        self.last_heavy = -10**9
        self.vlog_count = 0
        self.duty_total = 0
        self.clusters_seen: list[str] = []
        self.cluster_last_post: dict[str, int] = {}
        self.log: list[LogEntry] = []

    def _start_time(self, job: Job) -> int:
        t = max(job.earliest, self.last_any + 1)
        if job.kind in HEAVY_KINDS:
            t = max(t, self.last_heavy + self.cfg["VIDEO_MIN_INTERVAL_MINUTES"])
        if job.kind == "chat_post" and job.cluster in self.cluster_last_post:
            t = max(t, self.cluster_last_post[job.cluster] + self.cfg["CHAT_POST_INTERVAL_MIN_MINUTES"])
        return t

    def run(self, jobs: list[Job]) -> list[LogEntry]:
        self.duty_total = sum(1 for j in jobs if j.kind == "duty_video")
        pending = list(jobs)
        while pending:
            # Drop chat clusters beyond the daily budget.
            progressed = True
            while progressed:
                progressed = False
                for job in list(pending):
                    if job.kind == "chat_post" and job.cluster and job.cluster not in self.clusters_seen:
                        if len(self.clusters_seen) >= self.cfg["CHAT_CLUSTERS_PER_DAY"]:
                            self.log.append(LogEntry(self._start_time(job), job.name, "dropped", "cluster budget"))
                            pending.remove(job)
                            progressed = True
                        else:
                            self.clusters_seen.append(job.cluster)

            if not pending:
                break
            job = min(pending, key=lambda j: (self._start_time(j), j.priority, j.name))
            t = self._start_time(job)

            if job.kind == "vlog_video":
                if self.duty_total + self.vlog_count >= self.cfg["VIDEO_DAILY_LIMIT"]:
                    self.log.append(LogEntry(t, job.name, "dropped", "video budget (duty reserved)"))
                    pending.remove(job)
                    continue
                if self.temp_at(t) >= self.cfg["GPU_TEMP_LIMIT_C"]:
                    if t > 22 * 60:
                        self.log.append(LogEntry(t, job.name, "dropped", "thermal guard"))
                        pending.remove(job)
                    else:
                        self.log.append(LogEntry(t, job.name, "postponed", "thermal guard"))
                        job.earliest = t + 30
                    continue

            self.log.append(LogEntry(t, job.name, "run"))
            self.last_any = t
            if job.kind in HEAVY_KINDS:
                self.last_heavy = t
            if job.kind == "vlog_video":
                self.vlog_count += 1
            if job.kind == "chat_post" and job.cluster:
                self.cluster_last_post[job.cluster] = t
            pending.remove(job)
        return self.log
