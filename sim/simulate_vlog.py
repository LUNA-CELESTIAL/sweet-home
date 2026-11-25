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
import edit as edit_mod  # noqa: E402
import vlog  # noqa: E402
from llm import FakeLLM  # noqa: E402
from poster import ConsolePoster  # noqa: E402
from vlog import (VlogWatcher, parse_memo, parse_reject,  # noqa: E402
                  parse_vlog_request, split_memo_edit)

REQUEST = """vlog：朝の光のなかで
意図：お家の朝の静けさを見せたい
画像：deformer_luna.png
尺：5
プロンプト：
The girl waits quietly, breathing gently, in soft morning light."""
MEMO = "上映メモ：同じルナのまま、朝の光の中で静かに待っている。顔のずれなし。"
THEMED = """vlog：蕾のそばで
テーマ：そばにいる、という日常
見どころ：最後の、カメラへの小さな微笑み
意図：蕾が16日目。そばにいる小さな日常を見せたい
画像：deformer_luna.png
尺：5
プロンプト：
The girl sits beside a small potted plant with a single closed bud."""
MEMO_EDIT = ("上映メモ：蕾のそばで静かに見ていて、最後に小さく微笑む。\n"
             "編集：ループ、表紙：2.5")


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
    REJECT = "vlog却下：目の色のドリフト（青く写っている）"
    assert parse_reject(REJECT).startswith("目の色"), parse_reject(REJECT)
    assert parse_reject(REQUEST) is None
    assert parse_vlog_request(REJECT) is None and parse_memo(REJECT) is None

    # Presentation fields and the edit vocabulary.
    themed = parse_vlog_request(THEMED)
    assert themed["theme"] == "そばにいる、という日常", themed
    assert themed["highlight"].startswith("最後の"), themed
    assert req["theme"] == "" and req["highlight"] == ""  # optional
    body, edit_text = split_memo_edit(parse_memo(MEMO_EDIT))
    assert "編集" not in body and "微笑む" in body, body
    assert edit_text == "ループ、表紙：2.5", edit_text
    spec = edit_mod.parse_edit_spec(edit_text)
    assert spec["loop"] is True and spec["cover"] == 2.5, spec
    spec2 = edit_mod.parse_edit_spec("トリミング：1.0-4.0、速度：0.5")
    assert spec2["trim"] == (1.0, 4.0) and spec2["speed"] == 0.5, spec2
    assert edit_mod.is_passthrough(edit_mod.parse_edit_spec(None))
    assert edit_mod.is_passthrough(edit_mod.parse_edit_spec("そのまま"))
    try:
        edit_mod.parse_edit_spec("キラキラ加工")
        raise AssertionError("unknown edit token must raise")
    except ValueError:
        pass

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

        # Empty channel at first start: sentinel baseline, so the
        # first real request is saved, not swallowed (2026-11-25).
        batches_e = [[],
                     [{"id": "30", "author": {"id": "bot"}, "content": REQUEST}]]
        state_e = {"i": 0}

        def fetch_e(after):
            b = batches_e[state_e["i"]] if state_e["i"] < len(batches_e) else []
            state_e["i"] += 1
            return list(reversed(b))

        watcher_e = VlogWatcher("Bot x", "work", out, out / "state-e.json",
                                {"owner", "bot"}, fetch=fetch_e)
        assert watcher_e.poll_once() is None
        assert watcher_e.poll_once() == "request"
        vlog.extract_frame_sheet = lambda p: None
        poster = ConsolePoster()
        video = FakeVideo()
        assert vlog.run_stage1(out, video, poster) is True
        work_texts = [p["text"] for p in poster.posts if p["channel"] == "work"]
        assert any("プレビュー" in t for t in work_texts), work_texts
        assert not [p for p in poster.posts if p["channel"] == "vlog"]
        assert watcher.poll_once() == "memo"

        # No edit line in the memo: the edit step passes through.
        assert vlog.run_edit(out, poster) is True
        assert vlog.requests_by_state(out, "edited"), "not edited"

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

    # Reject path: a previewed take is closed by 「vlog却下：〜」 —
    # it can no longer take a memo or be screened.
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        req3 = parse_vlog_request(REQUEST)
        req3["id"] = "40"
        req3["state"] = "previewed"
        vlog._save(vlog._req_dir(out) / "40.json", req3)
        batches_r = [
            [{"id": "41", "author": {"id": "bot"}, "content": "プレビュー投稿"}],
            [{"id": "42", "author": {"id": "bot"}, "content": REJECT}],
            [{"id": "43", "author": {"id": "bot"}, "content": MEMO}],
        ]
        state_r = {"i": 0}

        def fetch_r(after):
            b = batches_r[state_r["i"]] if state_r["i"] < len(batches_r) else []
            state_r["i"] += 1
            return list(reversed(b))

        watcher_r = VlogWatcher("Bot x", "work", out, out / "state-r.json",
                                {"owner", "bot"}, fetch=fetch_r)
        assert watcher_r.poll_once() is None  # baseline
        assert watcher_r.poll_once() == "reject"
        rejected = vlog.requests_by_state(out, "rejected")
        assert len(rejected) == 1 \
            and "目の色" in rejected[0][1]["reject_reason"], rejected
        assert watcher_r.poll_once() is None  # memo finds no previewed take
        assert vlog.requests_by_state(out, "memo_ready") == []
        assert vlog.run_stage2(out, FakeLLM({}), ConsolePoster(),
                               datetime.date(2026, 11, 26), 900) is None

    # Two takes waiting (retake previewed before take 1 was
    # closed): the reject closes the OLDEST one, and the memo then
    # attaches to the remaining take.
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        for mid in ("50", "51"):
            r = parse_vlog_request(REQUEST)
            r["id"] = mid
            r["state"] = "previewed"
            vlog._save(vlog._req_dir(out) / f"{mid}.json", r)
        batches_t = [
            [{"id": "52", "author": {"id": "bot"}, "content": "プレビュー投稿"}],
            [{"id": "53", "author": {"id": "bot"}, "content": REJECT}],
            [{"id": "54", "author": {"id": "bot"}, "content": MEMO}],
        ]
        state_t = {"i": 0}

        def fetch_t(after):
            b = batches_t[state_t["i"]] if state_t["i"] < len(batches_t) else []
            state_t["i"] += 1
            return list(reversed(b))

        watcher_t = VlogWatcher("Bot x", "work", out, out / "state-t.json",
                                {"owner", "bot"}, fetch=fetch_t)
        assert watcher_t.poll_once() is None  # baseline
        assert watcher_t.poll_once() == "reject"
        rejected = vlog.requests_by_state(out, "rejected")
        assert len(rejected) == 1 and rejected[0][0].stem == "50", rejected
        assert watcher_t.poll_once() == "memo"
        ready = vlog.requests_by_state(out, "memo_ready")
        assert len(ready) == 1 and ready[0][0].stem == "51", ready

    # Presentation + edit: themed request, memo with an edit line.
    # The screening post carries テーマ/見どころ (never 意図), the
    # cover goes first, the screened file is the edited one, and
    # impressions are fed the 見どころ.
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        r = parse_vlog_request(THEMED)
        r["id"] = "60"
        r["state"] = "previewed"
        vlog._save(vlog._req_dir(out) / "60.json", r)
        (vlog._req_dir(out) / "60.mp4").write_bytes(b"raw")
        batches_p = [
            [{"id": "61", "author": {"id": "bot"}, "content": "プレビュー"}],
            [{"id": "62", "author": {"id": "bot"}, "content": MEMO_EDIT}],
        ]
        state_p = {"i": 0}

        def fetch_p(after):
            b = batches_p[state_p["i"]] if state_p["i"] < len(batches_p) else []
            state_p["i"] += 1
            return list(reversed(b))

        watcher_p = VlogWatcher("Bot x", "work", out, out / "state-p.json",
                                {"owner", "bot"}, fetch=fetch_p)
        assert watcher_p.poll_once() is None
        assert watcher_p.poll_once() == "memo"
        _, stored = vlog.requests_by_state(out, "memo_ready")[0]
        assert "編集" not in stored["memo"], stored["memo"]
        assert stored["edit"] == "ループ、表紙：2.5", stored

        calls = []

        def fake_apply(src, spec, out_path):
            calls.append(("apply", spec["loop"], spec["cover"]))
            out_path.write_bytes(b"edited")
            return out_path

        def fake_cover(video, at, out_path):
            calls.append(("cover", at, video.name))
            out_path.write_bytes(b"png")
            return out_path

        orig_apply, orig_cover = edit_mod.apply_edit, edit_mod.extract_cover
        edit_mod.apply_edit, edit_mod.extract_cover = fake_apply, fake_cover
        try:
            poster_p = ConsolePoster()
            assert vlog.run_edit(out, poster_p) is True
        finally:
            edit_mod.apply_edit, edit_mod.extract_cover = orig_apply, orig_cover
        assert calls[0][0] == "apply" and calls[0][1] is True, calls
        assert calls[1] == ("cover", 2.5, "60-edited.mp4"), calls
        _, stored = vlog.requests_by_state(out, "edited")[0]
        assert stored["edited_file"] == "60-edited.mp4", stored

        script = {pid: ["「最後の微笑み、見たよ。」"] * 2
                  for pid in ("sirius", "spica", "stella", "selene",
                                  "nano", "hina", "kohaku")}
        llm_p = FakeLLM(script)
        date = datetime.date(2026, 11, 26)
        event = vlog.run_stage2(out, llm_p, poster_p, date, 15 * 60)
        assert event is not None
        posts = [p for p in poster_p.posts if p["channel"] == "vlog"]
        assert posts[0]["text"].startswith("表紙"), posts[0]
        assert str(posts[1]["file"]).endswith("60-edited.mp4"), posts[1]
        assert "テーマ：そばにいる" in posts[1]["text"], posts[1]
        assert "見どころ：最後の" in posts[1]["text"], posts[1]
        assert "意図" not in posts[1]["text"], posts[1]
        assert all("見どころ" in p for p in llm_p.prompts), llm_p.prompts[:1]
        shares_p = cycle.load_shares(out, date.isoformat())
        assert shares_p and shares_p[0].get("highlight", "").startswith("最後の"), shares_p
        assert shares_p[0].get("theme", "").startswith("そばにいる"), shares_p

        # Edit failure: closed as failed, #vlog stays clean.
        r2 = parse_vlog_request(THEMED)
        r2["id"] = "70"
        r2["state"] = "memo_ready"
        r2["memo"] = "蕾のそば。"
        r2["edit"] = "ループ"
        vlog._save(vlog._req_dir(out) / "70.json", r2)
        (vlog._req_dir(out) / "70.mp4").write_bytes(b"raw")

        def boom(src, spec, out_path):
            raise RuntimeError("ffmpeg said no")

        edit_mod.apply_edit = boom
        try:
            poster_f = ConsolePoster()
            assert vlog.run_edit(out, poster_f) is True
        finally:
            edit_mod.apply_edit = orig_apply
        assert vlog.requests_by_state(out, "failed"), "edit failure not closed"
        assert not [p for p in poster_f.posts if p["channel"] == "vlog"]
        assert any("編集が失敗" in p["text"] for p in poster_f.posts), poster_f.posts
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
