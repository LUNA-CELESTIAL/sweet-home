"""Generation layer for duty texts and diary prose (LLM-backed).

Same interfaces as the deterministic prototypes: duty.compose's job
and diary.build_diary's structure stay, only the sentences come from
the model now. Diary structure (sections/topics/seed) is still built
by diary.py — the model writes prose inside the structure, never the
structure itself.
"""

import datetime

from diary import block_of
from personas import by_id
from session import extract_line

BLOCK_ORDER = ["朝のこと", "昼のこと", "午後のこと", "夕方のこと", "夜のこと"]


def _persona_block(p: dict) -> str:
    lines = [f"あなたは{p['name']}。やりたいこと: {p['want']}",
             f"あなたの関心の角度: {p['angle']}", f"しないこと: {p['avoid']}"]
    lines += [f"声の例 (言い回しの参考。そのまま使わない): {v}" for v in p["voice"]]
    return "\n".join(lines)


def duty_text(llm, member: dict, slot: str, weather: str, seed: dict | None) -> str:
    if slot == "morning":
        ask = (f"朝の当番の挨拶を、台詞ひとつ分、「」で囲んで書いてください。天気は{weather}。"
               f"「おはよう、{member['name']}です」のように、自分の名前で名乗ってください。"
               "今日への一言も入れてください。")
        if seed:
            ask += (f"昨日の日記から、{seed['sourceMember']}の{seed['topic']}の話が"
                    f"途中で終わっていたことも、短く触れてください。")
    else:
        ask = ("夜の当番の挨拶を、台詞ひとつ分、「」で囲んで書いてください。"
               f"「こんばんは、{member['name']}です」のように、自分の名前で名乗ってください。"
               "一日へのねぎらいと、明日の朝への一言を入れてください。"
               "自分に話しかける形にはしないでください。")
    prompt = _persona_block(member) + "\n\n" + ask + "\n説明や例示は書かないでください。出すのは台詞だけです。"
    return extract_line(llm.generate(prompt, member["id"]))


def _section_prompt(writer: dict, block: str, evs: list[dict]) -> str:
    lines = [_persona_block(writer), "", f"今日の日記の「{block}」の節を書いてください。"]
    lines.append("材料 (この時間帯の出来事):")
    for e in evs:
        line = f"- {e['member']}の「{e['topic']}」の話"
        if e.get("quote"):
            line += f"。本人の言葉: 「{e['quote']}」"
        lines.append(line)
    lines.append(
        "書き手としての一人称で、2〜4文の短い散文にしてください。"
        "材料の引用は必要な時だけ、原文のまま使ってください。"
        "見出しや箇条書きは書かず、本文だけを出してください。")
    return "\n".join(lines)


def diary_prose(llm, writer: dict, date: datetime.date, events: list[dict],
                structure: dict) -> tuple[dict, str]:
    """structure comes from diary.build_diary. Returns (site-ready meta, md)."""
    by_block: dict[str, list[dict]] = {}
    for ev in events:
        by_block.setdefault(block_of(ev["minutes"]), []).append(ev)

    sections_md = []
    section_paras: dict[str, str] = {}
    for sec in structure["sections"]:
        block = sec["heading"]
        raw = llm.generate(_section_prompt(writer, block, by_block.get(block, [])), writer["id"])
        para = raw.strip()
        section_paras[block] = para
        sections_md.append(f"## {block} — {sec['topic']}\n{para}")

    topics_line = "、".join(structure["topics"])
    closing_prompt = (
        _persona_block(writer)
        + f"\n\n今日の日記の締め「今日わかったこと」を、書き手の一人称で2〜3文書いてください。"
        + f"今日の話題: {topics_line}。見出しは書かず、本文だけを出してください。")
    closing = llm.generate(closing_prompt, writer["id"]).strip()
    sections_md.append(f"## 今日わかったこと\n{closing}")

    meta_prompt = (
        _persona_block(writer)
        + "\n\n今日の日記に題と、サイト用の短い紹介文をつけてください。"
        + f"今日の話題: {topics_line}。"
        + "\n次の形式だけで答えてください:\nTITLE: (題を1行)\nEXCERPT: (紹介文を2文まで)")
    meta_raw = llm.generate(meta_prompt, writer["id"])
    title, excerpt = "", ""
    for ln in meta_raw.splitlines():
        if ln.startswith("TITLE:"):
            title = ln[6:].strip()
        elif ln.startswith("EXCERPT:"):
            excerpt = ln[8:].strip()
    if not title:
        title = "ある一日"
    if not excerpt:
        excerpt = closing[:80]

    meta = {
        "date": date.isoformat(),
        "writer": writer["id"],
        "writerName": writer["name"],
        "title": title,
        "siteExcerpt": excerpt,
        "topics": structure["topics"],
        "sections": structure["sections"],
        "participants": structure["participants"],
        "seed": structure["seed"],
    }
    md = f"# {date.isoformat()} の日記 — 書き手: {writer['name']}\n\n" + "\n\n".join(sections_md) + f"\n\n— {writer['name']}\n"
    return meta, md
