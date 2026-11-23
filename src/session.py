"""Conversation session (Step 2 design, as code).

- The common packet (seed with verbatim quote + source) is built ONCE.
- Each turn is an independent generate() call for one speaker, given:
  the packet, the actual transcript so far, and ONLY that speaker's
  persona slice.
- Turn order and the stop are rules, not model decisions:
  opener -> originator -> guest -> originator (close), max 5 turns.
- After the session, exactly one line goes to the event pool.
"""

from personas import by_id


def build_packet(seed: dict) -> str:
    return (
        f"話題: {seed['topic']}\n"
        f"言い出し: {seed['sourceMember']}\n"
        f"本人の言葉(原文): 「{seed['quote']}」\n"
        f"状態: 途中で途切れた話の続き"
    )


def build_prompt(packet: str, transcript: list[dict], speaker: dict, repeat: bool = False) -> str:
    lines = [packet, "", f"あなたは{speaker['name']}。やりたいこと: {speaker['want']}"]
    lines.append(f"あなたの関心の角度: {speaker['angle']}")
    lines.append(f"しないこと: {speaker['avoid']}")
    lines += [f"声の例 (言い回しの参考。そのまま使わない): {v}" for v in speaker["voice"]]
    if transcript:
        lines.append("")
        lines.append("これまでの発言:")
        lines += [f"{t['name']}: {t['text']}" for t in transcript]
    lines.append("")
    lines.append(
        "次のあなたの発言を、台詞ひとつ分だけ、「」で囲んで書いてください。"
        "直前の人の言葉を受け止めたうえで、同調の相槌だけで終わらせず、"
        "あなたの関心の角度から新しい内容を一言足してください。"
        "話題の引用をそのまま繰り返さないでください。"
        "説明・要約・考察・例示は書かないでください。出すのは台詞だけです。"
    )
    if repeat:
        lines.append(
            "あなたはこの塊で2回目の発言です。さっきの自分の言い回しやモチーフは"
            "繰り返さず、別の側面から締めてください。"
        )
    return "\n".join(lines)


def extract_line(raw: str) -> str:
    """Keep only the utterance. Models sometimes wrap the line in an
    explanation; the last 「...」 segment is the intended line. Without
    quotes, fall back to the last non-empty line."""
    import re
    quoted = re.findall(r"「([^「」]+)」", raw)
    if quoted:
        return quoted[-1].strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def run_session(seed: dict, order: list[str], llm, on_line=None) -> tuple[list[dict], str]:
    """order: speaker ids in turn order, e.g. [opener, originator, guest, originator].
    on_line(entry) fires as each line is produced, so a live run posts
    line by line instead of going silent until the cluster is done."""
    assert len(order) <= 5, "a cluster is at most 5 turns"
    packet = build_packet(seed)
    transcript: list[dict] = []
    seen: set[str] = set()
    for pid in order:
        speaker = by_id(pid)
        prompt = build_prompt(packet, transcript, speaker, repeat=pid in seen)
        seen.add(pid)
        text = extract_line(llm.generate(prompt, pid))
        entry = {"member": pid, "name": speaker["name"], "text": text}
        transcript.append(entry)
        if on_line is not None:
            on_line(entry)
    names = "→".join(dict.fromkeys(t["name"] for t in transcript))
    pool_line = f"{seed['topic']}の続き話をした ({names})"
    return transcript, pool_line
