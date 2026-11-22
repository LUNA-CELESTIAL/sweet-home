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


def build_prompt(packet: str, transcript: list[dict], speaker: dict) -> str:
    lines = [packet, "", f"あなたは{speaker['name']}。やりたいこと: {speaker['want']}"]
    lines += [f"声の例: {v}" for v in speaker["voice"]]
    if transcript:
        lines.append("")
        lines.append("これまでの発言:")
        lines += [f"{t['name']}: {t['text']}" for t in transcript]
    lines.append("")
    lines.append("次のあなたの発言を、台詞ひとつ分だけ書いてください。要約や考察は書かないでください。")
    return "\n".join(lines)


def run_session(seed: dict, order: list[str], llm) -> tuple[list[dict], str]:
    """order: speaker ids in turn order, e.g. [opener, originator, guest, originator]."""
    assert len(order) <= 5, "a cluster is at most 5 turns"
    packet = build_packet(seed)
    transcript: list[dict] = []
    for pid in order:
        speaker = by_id(pid)
        text = llm.generate(build_prompt(packet, transcript, speaker), pid)
        transcript.append({"member": pid, "name": speaker["name"], "text": text})
    names = "→".join(dict.fromkeys(t["name"] for t in transcript))
    pool_line = f"{seed['topic']}の続き話をした ({names})"
    return transcript, pool_line
