"""Generated day verification with FakeLLM (offline).

One full day wired together: morning duty (generated) -> conversation
session -> evening duty (generated) -> diary (generated prose inside
the diary.py structure) -> site export. The fake replies are scripted;
this verifies wiring, prompt contents and parsing — not prose quality.
Run: python3 sim/simulate_generated_day.py  (stdlib only)
"""

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from diary import build_diary, writer_for  # noqa: E402
from duty import duty_member  # noqa: E402
from export_site import build_entry  # noqa: E402
from generate import diary_prose, duty_text  # noqa: E402
from llm import FakeLLM  # noqa: E402
from session import run_session  # noqa: E402

DATE = datetime.date(2026, 11, 23)
YESTERDAY_SEED = {
    "topic": "Pingツール", "sourceMember": "ステラ",
    "quote": "機能の数だけ手を出すのではなく、静かな回線の中で本当に必要なものを選ぶ目配り",
    "note": "ステラのPingツールの話、途中で終わっていたのが気になってる。",
}
EVENTS = [
    {"minutes": 9 * 60, "member": "こはく", "topic": "朝の当番"},
    {"minutes": 10 * 60 + 30, "member": "スピカ", "topic": "Pingツールの続き", "open": True,
     "quote": "実際に小さなパケットを放って、どの往復だけが返るか測ってみようかな"},
    {"minutes": 15 * 60, "member": "ルナ", "topic": "実生成の会話が初めて成立した", "kind": "home"},
]


def main():
    writer = writer_for(DATE)
    script = {
        "kohaku": ["「おはようございます、こはくです。今日は晴れ、最高14度。昨日のPingツールの話、続きが気になっています。」"],
        "luna": ["「ステラ、昨日のPingツールの話、途中で終わってたね。」"],
        "stella": ["「覚えててくれたのね。必要なものだけ、ね。」",
                   "「ふふ、決まりね。」",
                   "「こんばんは、ステラです。今日も一日おつかれさまでした。明日の朝、またここで。」"],
        "spica": ["「実際に小さなパケットを放って、どの往復だけが返るか測ってみようかな。」"],
    }
    script.setdefault(writer["id"], []).extend([
        "朝は当番の声から始まった。昨日の続きを気にかける声が、お家に残っていた。",
        "午後、会話が初めて本当に行き来した。試してみる、という一言が次を呼んだ。",
        "今日は、言葉が誰かの中で残って、次の言葉を呼ぶ日だった。",
        "TITLE: 続きが届いた日\nEXCERPT: 昨日の途切れた話が、今日の会話になりました。",
        "PREMISE: ステラのPingツールの話が続いている。\n"
        "PROGRESS: 今日は測ってみる一言まで進んだ。\n"
        "QUESTION: 測ることと、測らないでおく余白の境目。",
    ])
    llm = FakeLLM(script)

    morning_member = duty_member(DATE, "morning")
    morning = duty_text(llm, morning_member, "morning",
                        {"area": "東京地方", "raw": "晴れ", "rainy": False, "pop": "0"},
                        YESTERDAY_SEED)
    print(f"morning duty ({morning_member['name']}): {morning}")
    assert morning_member["id"] == "kohaku" and "Pingツール" in llm.prompts[0]

    transcript, pool_line = run_session(YESTERDAY_SEED, ["luna", "stella", "spica", "stella"], llm)
    print(f"session: {len(transcript)} turns / {pool_line}")

    evening_member = duty_member(DATE, "evening")
    evening = duty_text(llm, evening_member, "evening", None, None)
    print(f"evening duty ({evening_member['name']}): {evening}")

    structure, _ = build_diary(DATE, EVENTS)
    meta, md = diary_prose(llm, writer, DATE, EVENTS, structure)
    print(f"\ndiary by {writer['name']}: {meta['title']}")
    print(md)
    assert meta["title"] == "続きが届いた日"
    assert meta["seed"]["topic"] == "Pingツールの続き"
    assert meta["thread"]["premise"].startswith("ステラのPingツール"), meta["thread"]
    assert meta["thread"]["question"].startswith("測ることと"), meta["thread"]
    entry = build_entry(meta, md)
    assert entry["title"] == "続きが届いた日" and len(entry["sections"]) >= 3
    print("site export entry OK:", json.dumps(entry, ensure_ascii=False)[:80], "...")
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
