"""Diary -> site export verification (offline).

Builds sweet-bits' src/data/diary.json from the two prototype diaries
(2026-11-21 backtest + 2026-11-22) and checks the delivery contract:
- latest is the newest entry with full sections
- the index holds summaries only, newest first
- no seed / no raw material crosses to the site
- verbatim quotes survive; total size is far below the 64KB cap
Run: python3 sim/simulate_export.py  (stdlib only)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from export_site import build_entry, merge  # noqa: E402


def load_pair(folder: str):
    base = ROOT / "prototypes" / folder
    meta = json.loads((base / "diary.json").read_text(encoding="utf-8"))
    md = (base / "diary.md").read_text(encoding="utf-8")
    return build_entry(meta, md)


def main():
    site = merge(None, load_pair("diary-backtest-2026-11-21"))
    site = merge(site, load_pair("diary-2026-11-22"))

    out = ROOT / "export" / "diary.json"
    out.write_text(json.dumps(site, ensure_ascii=False, indent=1), encoding="utf-8")
    size = out.stat().st_size
    print(f"export/diary.json: {size} bytes, entries: {len(site['entries'])}, latest: {site['latest']['date']}")

    assert site["latest"]["date"] == "2026-11-22"
    assert [e["date"] for e in site["entries"]] == ["2026-11-22", "2026-11-21"]
    assert all("sections" not in e for e in site["entries"])
    assert "seed" not in json.dumps(site, ensure_ascii=False)
    afternoon = next(s for s in site["latest"]["sections"] if s["heading"] == "午後のこと")
    assert any("水やりみたい" in p for p in afternoon["paragraphs"])
    assert size < 64 * 1024
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
