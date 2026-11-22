"""LLM client boundary for sweet-home.

Everything generative goes through a client with one method,
generate(prompt) -> str. Offline work uses FakeLLM; the real machine
uses OllamaClient (stdlib urllib, model/URL from env config — never
hardcoded here). One call generates ONE utterance for ONE speaker;
there is deliberately no API for writing a whole conversation at
once.
"""

import json
import urllib.request


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
            return json.loads(res.read())["response"].strip()
