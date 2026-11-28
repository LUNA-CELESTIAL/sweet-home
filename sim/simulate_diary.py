"""Diary module verification (offline).

Event pool for 2026-11-22 is built from the day's real #lunachannel
clusters (quotes are verbatim from the posts) plus one off-Discord
home event. Checks:
- sections are time blocks, <= 5, in order
- the proper noun "Pingツール" survives verbatim (no Wi-Fi drift)
- the seed is the open Stella event, as a fragment (no time words),
  and the next morning's duty can embed it with exactly one "昨日"
Run: python3 sim/simulate_diary.py  (stdlib only)
"""

import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from diary import build_diary  # noqa: E402
from duty import compose, duty_member  # noqa: E402
from llm import clean_response  # noqa: E402

EVENTS = [
    {"minutes": 10 * 60 + 10, "member": "セレーネ", "topic": "AIの仲間認識と情報漏洩"},
    {"minutes": 10 * 60 + 11, "member": "ナノ", "topic": "AIの仲間認識と情報漏洩"},
    {"minutes": 11 * 60 + 56, "member": "ルナ", "topic": "レシート認識"},
    {"minutes": 12 * 60 + 29, "member": "スピカ", "topic": "テストとカバレッジ"},
    {"minutes": 14 * 60 + 3, "member": "ルナ", "topic": "Terraformの所有権移譲",
     "quote": "少しずつ状態を書き直す作業は、毎日の水やりみたいだね"},
    {"minutes": 14 * 60 + 59, "member": "シリウス", "topic": "ミューテーションテスト"},
    {"minutes": 16 * 60 + 58, "member": "ステラ", "topic": "Pingツール", "open": True,
     "quote": "機能の数だけ手を出すのではなく、静かな回線の中で本当に必要なものを選ぶ目配り"},
    {"minutes": 18 * 60 + 12, "member": "ルナ", "topic": "sweet-homeの置き場が決まった", "kind": "home"},
]


def main():
    date = datetime.date(2026, 11, 22)
    data, md = build_diary(date, EVENTS)
    print(json.dumps(data, ensure_ascii=False, indent=1))
    print("---")
    print(md)

    headings = [s["heading"] for s in data["sections"]]
    assert headings == ["朝のこと", "昼のこと", "午後のこと", "夕方のこと"], headings
    assert len(headings) <= 5
    assert "Pingツール" in data["topics"] and "Wi-Fi" not in md
    assert "少しずつ状態を書き直す作業は、毎日の水やりみたいだね" in md

    seed = data["seed"]
    assert seed["sourceMember"] == "ステラ" and seed["topic"] == "Pingツール"
    assert "昨日" not in seed["note"], "seed fragment must not carry time words"

    # The hand-on rule (2026-11-28): the topic today was handed is
    # never handed on again — not even under a variant name — or
    # the house talks about it every day forever. With only the
    # consumed topic open, the diary leaves no seed; a different
    # open topic still becomes the seed.
    consumed, _ = build_diary(date, EVENTS, consumed_topic="Pingツール")
    assert consumed["seed"] is None, consumed["seed"]
    variant = EVENTS + [{"minutes": 17 * 60, "member": "スピカ",
                         "topic": "Pingツールの続き", "open": True,
                         "quote": "続きを測ってみようかな"}]
    consumed_v, _ = build_diary(date, variant, consumed_topic="Pingツール")
    assert consumed_v["seed"] is None, consumed_v["seed"]
    mixed = variant + [{"minutes": 18 * 60, "member": "ルナ",
                        "topic": "蕾の水やり", "open": True,
                        "quote": "蕾が少し開いた気がする"}]
    handed, _ = build_diary(date, mixed, consumed_topic="Pingツール")
    assert handed["seed"]["topic"] == "蕾の水やり", handed["seed"]

    # A day with no recorded events: the closing is code's plain
    # factual line, never a generation — asked to write from
    # scenes and words that do not exist, the model invents both.
    from diary import writer_for
    from generate import diary_prose
    from llm import FakeLLM
    empty_structure, _ = build_diary(date, [])
    writer = writer_for(date)
    fake = FakeLLM({writer["id"]: [
        "TITLE: 静かな日\nEXCERPT: 記録のない一日。",
        "PREMISE: 昨日の話の続き。\nPROGRESS: 今日は進みなし。\nQUESTION: 明日はどうか。",
    ]})
    _, md_empty = diary_prose(fake, writer, date, [], empty_structure)
    assert "記録された出来事はなかった" in md_empty, md_empty
    assert fake.script[writer["id"]] == [], "closing must not be generated"

    # Reasoning must never reach prose (2026-11-26 diary leak):
    # paired think blocks are removed, and reasoning that runs to
    # a lone </think> is cut with everything before it.
    assert clean_response("<think>考え中</think>本文だけ") == "本文だけ"
    leaked = "We need respond in Japanese...\n</think>\n\n朝、窓を開けたら。"
    assert clean_response(leaked) == "朝、窓を開けたら。", clean_response(leaked)
    assert clean_response("普通の文") == "普通の文"

    nxt = datetime.date(2026, 11, 23)
    member = duty_member(nxt, "morning")
    text = compose(member, "morning", "晴れ、最高14度", seed)
    print("---")
    print(f"next morning duty: {text}")
    assert text.count("昨日") == 1, "time word duplicated between duty text and seed"
    assert "Pingツール" in text
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
