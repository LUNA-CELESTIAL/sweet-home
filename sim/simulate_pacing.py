"""Living pacing sim: in live shape, a gap passes between the lines
of a cluster (never before the first line, never in offline runs).

Run: python3 sim/simulate_pacing.py
"""

import datetime
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from day import Day  # noqa: E402
from llm import FakeLLM  # noqa: E402
from poster import ConsolePoster  # noqa: E402

SEED = {"topic": "Pingツール", "sourceMember": "ステラ",
        "quote": "静かな回線の中で本当に必要なものを選ぶ目配り",
        "note": "ステラのPingツールの話、途中で終わっていたのが気になってる。"}


def main() -> None:
    script = {
        "luna": ["「ステラ、昨日の話の続き、聞かせて。」"],
        "stella": ["「うん、必要なものだけね。」", "「決まりね。」"],
        "spica": ["「パケットを放って測ってみようかな。」"],
    }
    slept: list[float] = []
    with tempfile.TemporaryDirectory() as td:
        day = Day(FakeLLM(script), ConsolePoster(), datetime.date(2026, 11, 24),
                  None, SEED, [], Path(td),
                  line_gap_minutes=lambda: 7.0, sleeper=slept.append)
        day.living()
    # 4 lines -> 3 gaps of 7 minutes, header does not sleep
    assert slept == [7.0, 7.0, 7.0], slept
    print("pacing sim OK: gaps between living lines only")


if __name__ == "__main__":
    main()
