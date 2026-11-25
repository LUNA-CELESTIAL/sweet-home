"""Vlog verification (offline): request -> preview in the work
channel -> screening memo -> #vlog post + sister impressions ->
cycle. Failure reaches only the work channel. The render and the
model are faked; the wiring and state machine are what is checked.
Run: python3 sim/simulate_vlog.py  (stdlib only)
"""

import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import cycle  # noqa: E402
import vlog  # noqa: E402
from llm import FakeLLM  # noqa: E402
from poster import ConsolePoster  # noqa: E402
from vlog import VlogWatcher, parse_memo, parse_vlog_request  # noqa: E402

REQUEST = """vlog：朝の光のなかで
意図：お家の朝の静けさを見せたい
画像：krea2_identity_edit_00869_.png
尺：5
プロンプト：
The girl waits quietly, breathing gently, in soft morning light."""
MEMO = "上映メモ：同じルナのまま、朝の光の中で静かに待っている。顔のずれなし。"


class FakeVideo:
    def __init__(self, fail: bool = False):
        self.calls = []
        self.fail = fail

    def generate_raw(self, prompt, seed, out_path, image, duration):
        self.calls.append((prompt, image, duration))
        if self.fail:
            raise RuntimeError("comfy said no")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"fake mp4")
        return out_path


def main():
    req = parse_vlog_request(REQUEST)
    assert req is not None and req["title"] == "朝の光のなかで", req
    assert req["intent"].startswith("お家の朝") and req["prompt"].startswith("The girl"), req
    assert parse_vlog_request("実験：べつもの") is None
    assert parse_memo(MEMO).startswith("同じルナ"), parse_memo(MEMO)
    assert parse_memo("おはよう") is None

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        batches = [
            [{"id": "20", "author": {"id": "bot"}, "content": REQUEST}],
            [{"id": "21", "author": {"id": "bot"}, "content": REQUEST}],
            [{"id": "22", "author": {"id": "bot"}, "content": MEMO}],
        ]
        state = {"i": 0}

        def fetch(after):
            b = batches[state["i"]] if state["i"] < len(batches) else []
            state["i"] += 1
            return list(reversed(b))

        watcher = VlogWatcher("Bot x", "work", out, out / "state.json",
                              {"owner", "bot"}, fetch=fetch)
        assert watcher.poll_once() is None  # baseline
        assert watcher.poll_once() == "request"
        vlog.extract_frame_sheet = lambda p: None
        poster = ConsolePoster()
        video = FakeVideo()
        assert vlog.run_stage1(out, video, poster) is True
        work_texts = [p["text"] for p in poster.posts if p["channel"] == "work"]
        assert any("プレビュー" in t for t in work_texts), work_texts
        assert not [p for p in poster.posts if p["channel"] == "vlog"]
        assert watcher.poll_once() == "memo"

        script = {pid: ["「静けさが、ちゃんと届いたよ。」"] * 2
                  for pid in ("sirius", "spica", "stella", "selene",
                              "nano", "hina", "kohaku")}
        llm = FakeLLM(script)
        date = datetime.date(2026, 11, 26)
        event = vlog.run_stage2(out, llm, poster, date, 15 * 60)
        assert event is not None and event["topic"] == "朝の光のなかで", event
        vlog_posts = [p for p in poster.posts if p["channel"] == "vlog"]
        assert vlog_posts[0]["author"] == "ルナ" and vlog_posts[0]["file"], vlog_posts
        assert len(vlog_posts) == 4, vlog_posts  # video + 3 impressions
        assert all("上映メモ" in p or "同じルナ" in p for p in llm.prompts), llm.prompts[:1]
        shares = cycle.load_shares(out, date.isoformat())
        assert any(s["topic"] == "朝の光のなかで" for s in shares), shares
        assert vlog.requests_by_state(out, "screened"), "request not closed as screened"
        assert vlog.run_stage2(out, llm, poster, date, 15 * 60) is None

        # Failure path: generation error -> work channel only.
        req2 = parse_vlog_request(REQUEST)
        req2["id"] = "99"
        vlog._save(out / "vlog-requests" / "99.json", req2)
        poster2 = ConsolePoster()
        assert vlog.run_stage1(out, FakeVideo(fail=True), poster2) is True
        assert not [p for p in poster2.posts if p["channel"] == "vlog"]
        assert vlog.requests_by_state(out, "failed"), "failure not closed"
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
