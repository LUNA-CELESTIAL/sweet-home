"""Run ONE real conversation session with Ollama (still no Discord).

Reads .env (OLLAMA_MODEL / OLLAMA_BASE_URL), runs the Ping-tool seed
session with real generation, and prints the transcript. This is the
first place where conversation quality itself can be looked at.

Usage: python3 sim/run_real_session.py
Requires: Ollama running locally and OLLAMA_MODEL set in .env.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from config import load_env  # noqa: E402
from llm import OllamaClient  # noqa: E402
from session import run_session  # noqa: E402

SEED = {
    "topic": "Pingツール",
    "sourceMember": "ステラ",
    "quote": "機能の数だけ手を出すのではなく、静かな回線の中で本当に必要なものを選ぶ目配り",
    "note": "ステラのPingツールの話、途中で終わっていたのが気になってる。",
}


def main():
    env_path = ROOT / ".env"
    if not env_path.exists():
        print("No .env yet. Run: cp .env.example .env, then set OLLAMA_MODEL.")
        return
    cfg = load_env(env_path)
    try:
        llm = OllamaClient(cfg.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                           cfg.get("OLLAMA_MODEL", ""))
    except ValueError as e:
        print(f"Cannot start: {e}")
        print("Set OLLAMA_MODEL in .env to a model shown by `ollama list`.")
        return
    transcript, pool_line = run_session(SEED, ["luna", "stella", "spica", "stella"], llm)
    for t in transcript:
        print(f"{t['name']}: {t['text']}")
    print(f"\nevent pool: {pool_line}")


if __name__ == "__main__":
    main()
