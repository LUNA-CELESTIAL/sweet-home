"""Resident-program verification (offline): run_day with FakeLLM and
ConsolePoster must post in channel order duty -> living x4 -> duty ->
diary, and write the diary + site export files.
Run: python3 sim/simulate_main.py  (stdlib only)
"""

import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from day import run_day  # noqa: E402
from llm import FakeLLM  # noqa: E402
from main import DEMO_EVENTS, DEMO_SEED  # noqa: E402
from poster import ConsolePoster  # noqa: E402


def main():
    script = {
        "kohaku": ["「おはよう、こはくです。昨日のPingツールの話、受け取ってるよ。」",
                   "「ステラ、昨日の話の続き、聞かせて。」", "「そっか、受け取ったよ。」"],
        "luna": ["「ステラ、昨日の話の続き、聞かせて。」", "「そっか、じゃあ決まりだね。」"],
        "stella": ["「うん、必要なものだけね。」", "「決まりね。」",
                   "「こんばんは、ステラです。明日の朝、またここで。」"],
        "spica": ["「パケットを放って測ってみようかな。」", "「うん、やってみよう。」"],
        "sirius": ["朝は当番の声から始まった。", "午後、会話が行き来した。",
                   "夜は当番の声で静かに閉じた。",
                   "言葉が次の言葉を呼ぶ日だった。",
                   "TITLE: 続きが届いた日\nEXCERPT: 昨日の続きが今日の会話になりました。",
                   "PREMISE: ステラのPingツールの話が続いている。\n"
                   "PROGRESS: 今日は測ってみる一言まで進んだ。\n"
                   "QUESTION: 測ることと、測らないでおく余白の境目。"],
    }
    poster = ConsolePoster()

    class FakeVoice:
        def __init__(self):
            self.calls = []

        def synthesize(self, member_id, text, out_path):
            self.calls.append((member_id, out_path.name))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(b"RIFFfake")
            return out_path

    voice = FakeVoice()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        llm = FakeLLM(script)
        result = run_day(llm, poster, datetime.date(2026, 11, 23),
                         {"area": "東京地方", "raw": "晴れ", "rainy": False, "pop": "10"},
                         DEMO_SEED, DEMO_EVENTS, out,
                         site_export_path=ROOT / "export" / "diary.json", voice=voice)
        channels = [p["channel"] for p in poster.posts]
        assert channels == ["duty", "living", "living", "living", "living", "living",
                            "duty", "diary"], channels
        diary_post = poster.posts[-1]["text"]
        assert "いまの話" in diary_post and "前提:" in diary_post, diary_post
        # The #日記 post carries the diary's sections themselves
        # (the day's events and words), not only title + excerpt.
        assert "## " in diary_post and "今日わかったこと" in diary_post, diary_post
        # The closing / title prompts are fed the day's events as
        # material, not just topic names, and the closing is asked
        # to stay with the scenes rather than conclude.
        assert any("材料 (今日の出来事)" in p and "結論や教訓にまとめない" in p
                   for p in llm.prompts), "closing prompt lacks material"
        assert (out / "diary-2026-11-23.md").exists() and (out / "diary-site.json").exists()
        # The diary's seed now comes from the day's own living room
        # (the closing line, verbatim), not from the passed-in events.
        assert result["seed"]["topic"] == "Pingツール", result["seed"]
        assert result["seed"]["quote"] == "決まりね。", result["seed"]
        assert voice.calls == [("kohaku", "2026-11-23-morning.wav"),
                               ("stella", "2026-11-23-evening.wav")], voice.calls
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
