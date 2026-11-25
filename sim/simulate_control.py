"""Discord control sim: 止めて / 再開して in the work channel work
the PAUSE switch; strangers and history do not.

Run: python3 sim/simulate_control.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from control import DiscordControl, parse_command  # noqa: E402
from poster import ConsolePoster  # noqa: E402

OWNER, BOT, STRANGER = "111", "222", "999"


def msg(mid, author, content):
    return {"id": mid, "author": {"id": author}, "content": content}


def main() -> None:
    assert parse_command("止めて、実験する") == "pause"
    assert parse_command("再開して") == "resume"
    assert parse_command("止めたよ。次のジョブから手放すね。再開は「再開して」で。") is None
    assert parse_command("再開したよ。次のジョブから普通に動くね。") is None
    assert parse_command("おはよう") is None

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pause = root / "PAUSE"
        poster = ConsolePoster()
        batches = [
            # first poll: baseline only, even an owner command in
            # history is not acted on
            [msg("10", OWNER, "止めて")],
            # owner pauses
            [msg("11", OWNER, "止めて、実験する")],
            # stranger is ignored; bot relay (Luna) resumes
            [msg("12", STRANGER, "再開して"), msg("13", BOT, "再開して")],
        ]
        state = {"i": 0}

        def fetch(after):
            batch = batches[state["i"]] if state["i"] < len(batches) else []
            state["i"] += 1
            return list(reversed(batch))  # API returns newest first

        ctl = DiscordControl("Bot x", "chan", pause, poster,
                             root / "state.json", {OWNER, BOT}, fetch=fetch)
        assert ctl.poll_once() is None and not pause.exists()
        assert ctl.poll_once() == "pause" and pause.exists()
        assert ctl.poll_once() == "resume" and not pause.exists()
        assert ctl.poll_once() is None
        confirmations = [p["text"] for p in poster.posts if p["channel"] == "work"]
        assert any("止めたよ" in t for t in confirmations), confirmations
        assert any("再開したよ" in t for t in confirmations), confirmations

        # Empty channel at first start: the sentinel baseline means
        # the FIRST real post is acted on, not swallowed (the
        # 2026-11-25 bug that ate the first experiment/vlog posts).
        batches2 = [[], [msg("20", OWNER, "止めて")]]
        state2 = {"i": 0}

        def fetch2(after):
            batch = batches2[state2["i"]] if state2["i"] < len(batches2) else []
            state2["i"] += 1
            return list(reversed(batch))

        ctl2 = DiscordControl("Bot x", "chan", pause, poster,
                              root / "state2.json", {OWNER, BOT}, fetch=fetch2)
        assert ctl2.poll_once() is None and not pause.exists()
        assert ctl2.poll_once() == "pause" and pause.exists()
    print("control sim OK: baseline, owner/bot commands, stranger ignored, confirmations")


if __name__ == "__main__":
    main()
