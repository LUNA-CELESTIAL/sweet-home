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
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
