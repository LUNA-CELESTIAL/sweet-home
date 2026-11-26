"""LLM client boundary for sweet-home.

Everything generative goes through a client with one method,
generate(prompt) -> str. Offline work uses FakeLLM; the real machine
uses OllamaClient (stdlib urllib, model/URL from env config — never
hardcoded here). One call generates ONE utterance for ONE speaker;
there is deliberately no API for writing a whole conversation at
once.
"""

import json
import re
import urllib.request


def clean_response(text: str) -> str:
    """Remove a thinking model's reasoning from a response before
    anyone downstream treats it as prose. Two shapes occur: paired
    <think>...</think> blocks, and — the 2026-11-26 diary leak —
    reasoning that runs from the start of the response to a lone
    </think>, the opening tag never arriving. Line-shaped outputs
    (duty, living) were already immune via extract_line; prose
    outputs (diary sections, closings, impressions) were not."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    return text.strip()


class FakeLLM:
    """Scripted client for offline tests: replies keyed by speaker id."""

    def __init__(self, script: dict[str, list[str]]):
        self.script = {k: list(v) for k, v in script.items()}
        self.prompts: list[str] = []

    def generate(self, prompt: str, speaker_id: str) -> str:
        self.prompts.append(prompt)
        return self.script[speaker_id].pop(0)


class OllamaClient:
    def __init__(self, base_url: str, model: str):
        if not model or model.startswith("（"):
            raise ValueError("OLLAMA_MODEL is unset or still a placeholder")
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, speaker_id: str = "") -> str:
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as res:
            return clean_response(json.loads(res.read())["response"])

    def release(self) -> None:
        """Unload the model from VRAM (keep_alive: 0), the way
        luna-tech-web did: the house does not squat GPU memory
        between its short bursts of work, so Ruru's own experiments
        find the machine as they left it. Never raises."""
        try:
            body = json.dumps({"model": self.model, "keep_alive": 0}).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/generate", data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as res:
                res.read()
        except Exception:
            pass
