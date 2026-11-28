"""Weekly prepared topics: parse, file, spend one on its date.

Checks:
- the 週間テーマ： request parses one entry per line and skips
  lines that do not parse;
- filing dedupes by date+topic, and a topic is spent only on
  its own date (date-keying is the consumption rule);
- the work-channel watcher files a posted week and acknowledges
  it in the channel;
- a Day with no share and no diary seed runs its living room on
  the prepared theme: the header names the topic and the angle,
  the packet says the topic was brought as this week's theme and
  carries NO fabricated verbatim quote;
- the diary afterwards does not hand the prepared topic on.
"""

import datetime
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cycle  # noqa: E402
from day import Day  # noqa: E402
from experiment import ExperimentWatcher  # noqa: E402
from llm import FakeLLM  # noqa: E402
from poster import ConsolePoster  # noqa: E402
from topics import (append_topics, load_queue, parse_topics_request,  # noqa: E402
                    topic_seed_for)

REQUEST = """週間テーマ：
2026-11-29｜ルナ｜待つ時間｜蕾が開くまでみたいに、結果が出る前の時間をどう過ごすか
2026-11-30｜スピカ｜測ってみたい小さなこと｜家の中で、まだ数えたことのないものを数えてみる
壊れた行｜そのまま
2026-13-40｜ルナ｜ありえない日付｜x
2026-12-01｜ステラ｜余白の決め方｜"""

LINE = "「蕾のそばで、今日も静かに見守るね。」"


def script() -> dict:
    s = {
        "luna": [LINE] * 6,
        "stella": ["「余白に残すわ。」", "「決まりね。」"] * 4,
        "spica": ["「測ってみたいな。」"] * 4,
        "kohaku": ["「おはよう、こはくです。花の話、受け取ってるよ。」"] * 2,
        "sirius": ["「こんばんは、シリウスです。明日もよろしくね。」"] * 2,
        "selene": ["「こんばんは、セレーネです。」"] * 2,
        "nano": ["「おはよう、ナノです。」"] * 2,
        "hina": ["「おはよう、ひなです。」"] * 2,
    }
    prose = ["その時間のことが、静かに綴られた。"] * 8
    prose += ["今日は、言葉が次の言葉を呼ぶ日だった。",
              "TITLE: 種が届いた日\nEXCERPT: 昨日の話が今日の会話になりました。",
              "PREMISE: 花の話が続いている。\nPROGRESS: 今日も見守った。\n"
              "QUESTION: 蕾が開くのはいつか。"]
    for key in list(s):
        s[key] = s[key] + prose
    return s


def main():
    entries = parse_topics_request(REQUEST)
    assert entries is not None and len(entries) == 3, entries
    assert entries[0] == {"date": "2026-11-29", "member": "ルナ",
                          "topic": "待つ時間",
                          "angle": "蕾が開くまでみたいに、結果が出る前の時間をどう過ごすか"}, entries[0]
    assert entries[2]["angle"] == "", entries[2]
    assert parse_topics_request("実験：ちがう依頼") is None
    assert parse_topics_request("週間テーマ：\n壊れた行だけ") is None

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        assert append_topics(out, entries) == 3
        assert append_topics(out, entries) == 0  # no duplicates
        assert len(load_queue(out)) == 3

        seed = topic_seed_for(out, "2026-11-29")
        assert seed is not None and seed["topic"] == "待つ時間", seed
        assert seed["sourceMember"] == "ルナ" and seed["prepared"] is True
        assert seed["quote"] == "", "a prepared theme has no verbatim quote"
        assert topic_seed_for(out, "2026-11-28") is None
        assert topic_seed_for(out, "2026-12-05") is None

        # --- The watcher files a posted week and acknowledges it.
        batches = [
            [{"id": "1", "author": {"id": "bot"}, "content": "おはよう"}],
            [{"id": "2", "author": {"id": "bot"}, "content": REQUEST}],
        ]
        state = {"i": 0}

        def fetch(after):
            b = batches[state["i"]] if state["i"] < len(batches) else []
            state["i"] += 1
            return list(reversed(b))

        watcher = ExperimentWatcher("Bot x", "work", out,
                                    out / "experiment-state.json",
                                    {"bot"}, fetch=fetch)
        acks = []
        watcher._post = acks.append
        assert watcher.poll_once() is None  # baseline only
        assert load_queue(out) == load_queue(out) and len(load_queue(out)) == 3
        watcher.poll_once()
        # The queue already held these entries, so nothing is new
        # and no ack is posted; file a fresh week to see the ack.
        batches.append([{"id": "3", "author": {"id": "bot"},
                         "content": "週間テーマ：\n"
                                    "2026-12-06｜ナノ｜小さい遊び｜家の中で今すぐできる遊び"}])
        watcher.poll_once()
        assert len(load_queue(out)) == 4, load_queue(out)
        assert len(acks) == 1 and "1件" in acks[0], acks

        # --- A Day on the prepared theme.
        poster = ConsolePoster()
        day = Day(FakeLLM(script()), poster,
                  datetime.date(2026, 11, 29), None, None, [], out,
                  topic_seed_loader=lambda: topic_seed_for(out, "2026-11-29"))
        day.living()
        headers = [p["text"] for p in poster.posts
                   if p["channel"] == "living" and p["author"] == "リビング"]
        assert headers and "待つ時間" in headers[0], headers
        assert "結果が出る前の時間" in headers[0], headers  # the angle line
        prompts = day.llm.prompts
        assert any("今週のテーマとして持ち寄られた話題" in p for p in prompts), \
            "packet does not say the topic is a prepared theme"
        assert not any("本人の言葉(原文)" in p for p in prompts), \
            "a prepared theme must not carry a fabricated quote"

        day.diary()
        assert day.result["seed"] is None, day.result["seed"]
        assert cycle.load_seed(out) is None, "the theme was handed on"

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
