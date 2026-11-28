"""Conversation session (Step 2 design, as code).

- The common packet (seed with verbatim quote + source) is built ONCE.
- Each turn is an independent generate() call for one speaker, given:
  the packet, the actual transcript so far, and ONLY that speaker's
  persona slice.
- Turn order is a rule-side pattern (exchange / join / widen, chosen
  by the caller), max 5 turns — with one living exception: a line
  that calls another member by name with a question passes the
  baton, and that member takes the next turn.
- The baton is carried in the prompt conditions, not in per-line
  rules: answer the previous speaker's content first, then add your
  own angle. Persona shows in how a member responds, not in a motif
  inserted every line.
- After the session, exactly one line goes to the event pool.
"""

from personas import PERSONAS, by_id


def find_called_member(text: str, exclude_id: str) -> str | None:
    """A baton pass: the line names another member and asks them
    something (？). Returns that member's id, or None."""
    if "？" not in text and "?" not in text:
        return None
    for p in PERSONAS:
        if p["id"] != exclude_id and p["name"] in text:
            return p["id"]
    return None


def build_packet(seed: dict) -> str:
    if seed.get("prepared"):
        # A weekly prepared theme (topics.py): no verbatim quote
        # exists, and none is invented — the packet says where the
        # topic came from, and the named sister opens it herself.
        return (
            f"話題: {seed['topic']}\n"
            f"言い出し: {seed['sourceMember']}\n"
            f"これは今週のテーマとして持ち寄られた話題。切り口: {seed.get('note', '')}\n"
            f"状態: 今日ここから新しく開く話"
        )
    return (
        f"話題: {seed['topic']}\n"
        f"言い出し: {seed['sourceMember']}\n"
        f"本人の言葉(原文): 「{seed['quote']}」\n"
        f"状態: 途中で途切れた話の続き"
    )


def build_prompt(packet: str, transcript: list[dict], speaker: dict,
                 repeat: bool = False, called: bool = False) -> str:
    lines = [packet, "", f"あなたは{speaker['name']}。やりたいこと: {speaker['want']}"]
    lines.append(f"あなたの関心の角度: {speaker['angle']}")
    lines.append(f"しないこと: {speaker['avoid']}")
    lines += [f"声の例 (言い回しの参考。そのまま使わない): {v}" for v in speaker["voice"]]
    if transcript:
        lines.append("")
        lines.append("これまでの発言:")
        lines += [f"{t['name']}: {t['text']}" for t in transcript]
    lines.append("")
    if called:
        lines.append("直前の発言は、あなたへの問いかけです。まず、その問いに答えてください。")
    if transcript:
        lines.append(
            "次のあなたの発言を、台詞ひとつ分だけ、「」で囲んで書いてください。"
            "まず、直前の人の言葉の内容を受けて返してください（同意でも、押し返しでも、問い返しでも）。"
            "キーワードだけを拾って、自分の話で完結させないでください。"
            "そのうえで、あなたの関心の角度を足してください。"
            "受けて返す時は、2〜3文でも構いません。"
            "誰かに問いを渡したい時は、名前を呼んで問いかけてください。その人が次に答えます。"
            "あなたの人格は、決め手の言葉やモチーフを毎回入れることではなく、返し方・受け取り方に出してください。"
            "話題の引用をそのまま繰り返さないでください。"
            "説明・要約・考察・例示は書かないでください。出すのは台詞だけです。"
        )
    else:
        lines.append(
            "次のあなたの発言を、台詞ひとつ分だけ、「」で囲んで書いてください。"
            "話題の口火を切ってください。誰かに問いを渡したい時は、名前を呼んで問いかけてください。"
            "その人が次に答えます。"
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


def is_broken_line(text: str) -> bool:
    """A line with no words in it is not a line: empty, punctuation or
    symbols only ('...', '…'), or carrying a replacement character
    from a garbled decode. Seen live 2026-11-24: Stella's turn posted
    as just '...'. Such lines are regenerated once, then dropped."""
    import re
    if "�" in text:
        return True
    return not re.search(r"\w", text)


def run_session(seed: dict, order: list[str], llm, on_line=None) -> tuple[list[dict], str]:
    """order: speaker ids in turn order, e.g. [opener, originator, guest, originator].
    A line that calls another member by name with a question rewrites
    the next slot: the called member answers next.
    on_line(entry) fires as each line is produced, so a live run posts
    line by line instead of going silent until the cluster is done."""
    assert len(order) <= 5, "a cluster is at most 5 turns"
    order = list(order)
    packet = build_packet(seed)
    transcript: list[dict] = []
    seen: set[str] = set()
    called_slots: set[int] = set()
    for i, pid in enumerate(order):
        speaker = by_id(pid)
        prompt = build_prompt(packet, transcript, speaker,
                              repeat=pid in seen, called=i in called_slots)
        seen.add(pid)
        text = extract_line(llm.generate(prompt, pid))
        if is_broken_line(text):
            text = extract_line(llm.generate(prompt, pid))  # one retry
        if is_broken_line(text):
            continue  # drop the turn rather than post a non-line
        entry = {"member": pid, "name": speaker["name"], "text": text}
        transcript.append(entry)
        if on_line is not None:
            on_line(entry)
        called = find_called_member(text, pid)
        if called is not None and i + 1 < len(order):
            order[i + 1] = called
            called_slots.add(i + 1)
    names = "→".join(dict.fromkeys(t["name"] for t in transcript))
    pool_line = f"{seed['topic']}の続き話をした ({names})"
    return transcript, pool_line
