"""Session module verification with FakeLLM (offline).

The fake replies are scripted, so this does NOT verify conversation
quality — it verifies the wiring rules from the Step 2 design:
- the packet (with the verbatim quote) is built once and shared
- each call sees only its own speaker's persona slice
- the transcript accumulates and later speakers see earlier lines
- the session stops at the ruled turn count and emits one pool line
Run: python3 sim/simulate_session.py  (stdlib only)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from llm import FakeLLM  # noqa: E402
from personas import PERSONAS  # noqa: E402
from session import run_session  # noqa: E402

SEED = {
    "topic": "Pingツール",
    "sourceMember": "ステラ",
    "quote": "機能の数だけ手を出すのではなく、静かな回線の中で本当に必要なものを選ぶ目配り",
    "note": "ステラのPingツールの話、途中で終わっていたのが気になってる。",
}

SCRIPT = {
    "luna": ["台詞はひとつだけ書きます。例えば「様子を見ます」のような形です。\n"
             "「ステラ、昨日のPingツールの話、途中で終わってたね。必要なものだけ選ぶって言ってたのが気になってるの。」"],
    "stella": ["覚えててくれたのね。機能が多いほど、使わないものを置いていく選び方に美学を感じるのよ。",
               "ふふ、決まりね。静かな回線で、必要なものだけ。"],
    "spica": ["私はWake-on-LANでお家のPCを起こすところを試してみたいな。速度テストで回線も測れるし。"],
}


def main():
    llm = FakeLLM(SCRIPT)
    transcript, pool_line = run_session(SEED, ["luna", "stella", "spica", "stella"], llm)
    for t in transcript:
        print(f"{t['name']}: {t['text']}")
    print(f"\nevent pool: {pool_line}")

    assert len(transcript) == 4 and len(llm.prompts) == 4
    assert transcript[0]["text"].startswith("ステラ、昨日のPingツール"), "noisy output was not reduced to the line"
    assert "例えば" not in transcript[0]["text"]
    for prompt, turn in zip(llm.prompts, transcript):
        assert SEED["quote"] in prompt, "seed quote must reach every call verbatim"
        speaker_wants = {p["id"]: p["want"] for p in PERSONAS}
        own = speaker_wants[turn["member"]]
        assert own in prompt
        for pid, want in speaker_wants.items():
            if pid != turn["member"]:
                assert want not in prompt, f"prompt leaked another persona slice: {pid}"
    assert transcript[0]["text"] in llm.prompts[1], "second speaker must see the first line"
    assert "Pingツールの続き話をした" in pool_line

    # Baton conditions (2026-11-25): prompts carry the answer-first
    # wording, the one-phrase pressure is gone, and passing by name
    # is allowed.
    assert "受けて返して" in llm.prompts[1], llm.prompts[1]
    assert "名前を呼んで問いかけて" in llm.prompts[1]
    assert "2〜3文でも" in llm.prompts[1]
    assert all("一言足して" not in p for p in llm.prompts), "old one-phrase pressure remains"

    # A line that calls a member by name with a question rewrites
    # the next turn: the called member answers, and their prompt
    # says the question was for them.
    llm3 = FakeLLM({
        "luna": ["「ステラ、昨日のPingの話、もう一度聞かせて？」"],
        "stella": ["「いいわよ。静かな回線で、必要なものだけ残すの。」",
                   "「決まりね、その選び方でいきましょう。」"],
        "spica": ["「私は測る係をするよ。」"],
    })
    transcript3, _ = run_session(SEED, ["luna", "spica", "stella"], llm3)
    members3 = [t["member"] for t in transcript3]
    assert members3 == ["luna", "stella", "stella"], members3
    assert "あなたへの問いかけです" in llm3.prompts[1], llm3.prompts[1]

    # Cluster shapes by role (day.py): exchange / join / widen,
    # with the seed's source member in the originator's chair.
    import datetime as _dt
    from day import cluster_order_for
    d = _dt.date(2026, 11, 26)
    o0 = cluster_order_for(SEED, d, 0)
    o1 = cluster_order_for(SEED, d, 1)
    o2 = cluster_order_for(SEED, d, 2)
    assert len(o0) == 4 and o0[1] == "stella" and o0[3] == "stella", o0
    assert o0[0] == o0[2] and o0[0] != "stella", o0  # exchange: two members
    assert len(o1) == 4 and o1[1] == "stella" and o1[2] not in (o1[0], "stella"), o1
    assert len(o2) == 5 and o2[-1] == "stella" and len(set(o2)) == 4, o2

    # Broken-line guard (live failure 2026-11-24, Stella's '...'):
    # a symbol-only reply is regenerated once; if it stays broken,
    # the turn is dropped and never reaches on_line.
    posted: list[dict] = []
    llm2 = FakeLLM({
        "luna": ["「今日は静かだね。」"],
        "stella": ["...", "「静けさは、余白に残すものよ。」"],
        "spica": ["…", "�"],
    })
    transcript2, _ = run_session(SEED, ["luna", "stella", "spica"], llm2,
                                 on_line=posted.append)
    texts2 = [t["text"] for t in transcript2]
    assert texts2 == ["今日は静かだね。", "静けさは、余白に残すものよ。"], texts2
    assert [p["text"] for p in posted] == texts2, "a dropped turn must not be posted"
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
