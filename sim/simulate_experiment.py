"""Experiment job verification (offline): request parsing, the
work-channel watcher, the free-time runner, and the executor's
idle hook. The render itself is faked; wiring is what is checked.
Run: python3 sim/simulate_experiment.py  (stdlib only)
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import experiment  # noqa: E402
from executor import Executor, TimedJob  # noqa: E402
from experiment import ExperimentWatcher, parse_request, run_pending  # noqa: E402
from poster import ConsolePoster  # noqa: E402

REQUEST = """実験：フレーム切り出しテスト（待ってる姿）
画像：deformer_luna.png
尺：5
プロンプト：
The girl in the image is waiting quietly in place. She breathes gently,
blinks slowly a few times, and sways very slightly."""


class FakeClock:
    def __init__(self):
        self.minutes = 0.0
        self.sleeps: list[float] = []

    def now(self):
        return self.minutes

    def sleep(self, m):
        self.sleeps.append(m)
        self.minutes += m


def main():
    req = parse_request(REQUEST)
    assert req is not None and req["image"] == "deformer_luna.png", req
    assert req["duration"] == 5.0 and req["prompt"].startswith("The girl"), req
    assert req["note"].startswith("フレーム切り出し"), req
    assert parse_request("おはよう") is None
    assert parse_request("実験：プロンプトなし") is None

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        batches = [
            [{"id": "10", "author": {"id": "owner"}, "content": REQUEST}],
            [{"id": "11", "author": {"id": "bot"}, "content": REQUEST},
             {"id": "12", "author": {"id": "stranger"}, "content": REQUEST}],
        ]
        state = {"i": 0}

        def fetch(after):
            b = batches[state["i"]] if state["i"] < len(batches) else []
            state["i"] += 1
            return list(reversed(b))

        watcher = ExperimentWatcher("Bot x", "work", out, out / "state.json",
                                    {"owner", "bot"}, fetch=fetch)
        assert watcher.poll_once() is None  # baseline: history ignored
        assert watcher.poll_once() is not None  # bot relay counts
        pending = experiment.pending_requests(out)
        assert len(pending) == 1 and pending[0].stem == "11", pending

        class FakeVideo:
            def __init__(self):
                self.calls = []

            def generate_raw(self, prompt, seed, out_path, image, duration):
                self.calls.append((prompt, image, duration))
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(b"fake mp4")
                return out_path

        video = FakeVideo()
        poster = ConsolePoster()
        experiment.extract_frame_sheet = lambda p: None  # no ffmpeg here
        assert run_pending(out, video, poster) is True
        assert video.calls and video.calls[0][1].startswith("deformer_luna"), video.calls
        texts = [p["text"] for p in poster.posts if p["channel"] == "work"]
        assert any("実験の結果" in t and "The girl" in t for t in texts), texts
        assert experiment.pending_requests(out) == []
        assert run_pending(out, video, poster) is False  # nothing left

    # Executor idle hook: a long gap invites the experiment once;
    # the job still starts at its planned time; short gaps do not.
    clock = FakeClock()
    used: list[float] = []

    def idle():
        used.append(clock.minutes)
        clock.minutes += 30  # the render consumed half an hour
        return True

    ex = Executor(clock.now, clock.sleep, temp_c=lambda: 50.0, temp_limit_c=85)
    ran: list[float] = []
    ex.run([TimedJob(120, "living", lambda: ran.append(clock.minutes)),
            TimedJob(130, "diary", lambda: None)], idle=idle)
    assert used == [0.0], used
    assert ran == [120.0], ran
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
