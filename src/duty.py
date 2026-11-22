"""Duty (morning / evening greeting) — text-first slice of Step 4.

Rotation is by date so the same day always picks the same sister.
The morning text must be able to carry yesterday's diary seed: that
is the visible proof that memory is being used. Generation here is a
deterministic offline composition (no LLM) so the wiring can be
tested anywhere; the Ollama-backed generator replaces `compose`
behind the same interface on the real machine.
"""

import datetime

from personas import PERSONAS


def duty_member(date: datetime.date, slot: str) -> dict:
    idx = date.toordinal() % len(PERSONAS)
    if slot == "evening":
        idx = (idx + 4) % len(PERSONAS)  # evening is a different sister
    return PERSONAS[idx]


def compose(member: dict, slot: str, weather: str, seed: str | None) -> str:
    name = member["name"]
    if slot == "morning":
        text = f"おはようございます、{name}です。今日は{weather}。"
        if seed:
            text += f"昨日の日記からひとつ。{seed}"
        text += f"今日も{member['want']}、そんな一日にしたいです。"
        return text
    text = f"こんばんは、{name}です。今日も一日おつかれさまでした。"
    text += f"明日の朝、またここで会いましょう。"
    return text
