"""Cycle verification (offline): diary -> seed -> next day, shares
taking over the living room, and a related past topic resurfacing.

Day 1 runs on the demo seed; its diary must leave a seed built from
the day's REAL events (the living room's closing line, verbatim).
Day 2 must start from that seed — no demo topic anywhere. A morning
share overrides the living topic, and the last cluster returns to a
related past diary topic.
Run: python3 sim/simulate_cycle.py  (stdlib only)
"""

import datetime
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import cycle  # noqa: E402
from day import Day  # noqa: E402
from llm import FakeLLM  # noqa: E402
from poster import ConsolePoster  # noqa: E402
from shares import SharesWatcher  # noqa: E402

SEED0 = {
    "topic": "水やりの花", "sourceMember": "ルナ",
    "quote": "蕾がひとつ、根元に小さな葉を出した",
    "note": "花の様子が気になってる。",
}
LINE = "「蕾のそばで、今日も静かに見守るね。」"


def script(writer_lines: int = 8) -> dict:
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
    prose = ["その時間のことが、静かに綴られた。"] * writer_lines
    prose += ["今日は、言葉が次の言葉を呼ぶ日だった。",
              "TITLE: 種が届いた日\nEXCERPT: 昨日の話が今日の会話になりました。",
              "PREMISE: 花の話が続いている。\nPROGRESS: 今日も見守った。\n"
              "QUESTION: 蕾が開くのはいつか。"]
    for key in list(s):
        s[key] = s[key] + prose
    return s


def main():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        # --- Day 1: full day on SEED0; diary closes the cycle.
        d1 = datetime.date(2026, 11, 25)
        day1 = Day(FakeLLM(script()), ConsolePoster(), d1, None, SEED0, [], out)
        day1.morning()
        day1.living()
        day1.evening()
        day1.diary()
        # The hand-on rule (2026-11-28): day 1 was handed 水やりの花
        # and spent the day on it, so its diary hands nothing on.
        # The diary used to re-seed the day's own living topic every
        # night, and the house talked about it forever.
        seed1 = cycle.load_seed(out)
        assert seed1 is None, seed1
        archive = cycle.load_archive(out)
        assert len(archive) == 1 and archive[0]["date"] == d1.isoformat()

        # --- Shares watcher: baseline, then an owner's video post.
        class TZ(datetime.tzinfo):
            def utcoffset(self, dt):
                return datetime.timedelta(hours=9)

            def dst(self, dt):
                return datetime.timedelta(0)

        batches = [
            [{"id": "1", "author": {"id": "owner"}, "content": "おはよう",
              "attachments": [], "timestamp": "2026-11-26T00:30:00+00:00"}],
            [{"id": "2", "author": {"id": "owner"},
              "content": "朝の動画できた https://example.com/v",
              "attachments": [{"url": "https://cdn/x.mp4", "content_type": "video/mp4"}],
              "timestamp": "2026-11-26T01:00:00+00:00"},
             {"id": "3", "author": {"id": "bot"}, "content": "https://spam.example",
              "attachments": [], "timestamp": "2026-11-26T01:01:00+00:00"}],
        ]
        state = {"i": 0}

        def fetch(cid, after):
            b = batches[state["i"]] if state["i"] < len(batches) else []
            state["i"] += 1
            return list(reversed(b))

        watcher = SharesWatcher("Bot x", ["living"], "owner", out,
                                out / "shares-state.json", TZ(), fetch=fetch)
        assert watcher.poll_once() == []  # baseline only
        found = watcher.poll_once()
        assert len(found) == 1 and found[0]["minutes"] == 10 * 60, found

        shares = cycle.load_shares(out, "2026-11-26")
        assert len(shares) == 1 and shares[0]["topic"].startswith("朝の動画"), shares

        # Empty channel at first start: sentinel baseline, so the
        # first real share is recorded, not swallowed.
        batches_e = [[],
                     [{"id": "9", "author": {"id": "owner"},
                       "content": "これ見て https://example.com/a",
                       "attachments": [],
                       "timestamp": "2026-11-26T02:00:00+00:00"}]]
        state_e = {"i": 0}

        def fetch_e(cid, after):
            b = batches_e[state_e["i"]] if state_e["i"] < len(batches_e) else []
            state_e["i"] += 1
            return list(reversed(b))

        watcher_e = SharesWatcher("Bot x", ["vlog"], "owner", out,
                                  out / "shares-state-e.json", TZ(), fetch=fetch_e)
        assert watcher_e.poll_once() == []
        assert len(watcher_e.poll_once()) == 1

        # --- Day 2: starts from a fresh seed again (one a later
        # diary or a share left — never yesterday's echo); the share
        # takes the living room; the last cluster resurfaces a
        # related past topic.
        d2 = datetime.date(2026, 11, 26)
        cycle.append_archive(out, {
            "date": "2026-11-20", "writer": "luna", "writerName": "ルナ",
            "title": "x", "siteExcerpt": "水やりの花の蕾が膨らんだ日。",
            "topics": ["水やりの花と蕾"],
            "seed": {"topic": "水やりの花と蕾", "sourceMember": "ルナ",
                     "quote": "蕾が少し膨らんだ", "note": ""}})
        related = cycle.related_past_seed(
            cycle.load_archive(out), SEED0["topic"], {d1.isoformat(), d2.isoformat()})
        assert related is not None and related["topic"] == "水やりの花と蕾", related

        poster2 = ConsolePoster()
        day2 = Day(FakeLLM(script()), poster2, d2, None, SEED0, [], out,
                   share_seed_loader=lambda: cycle.share_to_seed(shares[-1]),
                   related_seed=related)
        day2.morning()
        assert any("水やりの花" in p for p in day2.llm.prompts), "day2 duty lost the seed"
        day2.living()
        day2.living()
        day2.living()
        headings = [p["text"] for p in poster2.posts
                    if p["channel"] == "living" and p["author"] == "リビング"]
        assert "朝の動画できた" in headings[0], headings
        assert "水やりの花と蕾" in headings[-1], headings
        # The header carries a one-line explanation under the title
        # line (composed from the seed's own material).
        assert "\n" in headings[0], headings[0]

        # share_to_seed's about: vlog shares explain themselves from
        # their presentation material; plain shares from their first
        # sentence; a bare URL gets none.
        vlog_seed = cycle.share_to_seed({
            "id": "vlog-9", "member": "ルナ", "topic": "蕾のそばで",
            "text": "窓辺の蕾のそばに座っている。最後に微笑む。",
            "highlight": "最後の、カメラへの小さな微笑み"})
        assert vlog_seed["about"].startswith("今日 #vlog で上映した5秒「蕾のそばで」"), vlog_seed
        assert "見どころ：最後の" in vlog_seed["about"], vlog_seed
        vlog_seed2 = cycle.share_to_seed({
            "id": "vlog-10", "member": "ルナ", "topic": "朝の光",
            "text": "窓辺で静かに待っている。顔のずれなし。"})
        assert "窓辺で静かに待っている" in vlog_seed2["about"], vlog_seed2
        plain_seed = cycle.share_to_seed({
            "member": "るる", "topic": "写真", "text": "昨日の写真だよ。見て。"})
        assert plain_seed["about"] == "昨日の写真だよ", plain_seed
        url_seed = cycle.share_to_seed({
            "member": "るる", "topic": "リンク", "text": "",
            "url": "https://example.com/x"})
        assert "about" not in url_seed, url_seed
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
