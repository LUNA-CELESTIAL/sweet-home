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
