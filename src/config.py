"""Config loading for sweet-home.

Rules (docs/SPEC_v0.md): nothing secret or environment-specific is
hardcoded in code. Everything comes from a .env file. Values wrapped
in full-width parentheses in .env.example are placeholders; if any
required placeholder remains, live mode must refuse to start.
"""

from pathlib import Path

PLACEHOLDER_MARK = "（"

REQUIRED_FOR_LIVE = [
    "DISCORD_BOT_TOKEN",
    "DISCORD_GUILD_ID",
    "DISCORD_CHANNEL_LUNACHANNEL_ID",
    "OLLAMA_MODEL",
]


def load_env(path: str | Path) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def placeholders(cfg: dict[str, str]) -> list[str]:
    return [k for k, v in cfg.items() if v.startswith(PLACEHOLDER_MARK)]


def check_live_ready(cfg: dict[str, str]) -> list[str]:
    """Return the list of problems that block live mode (empty = ready)."""
    problems = []
    for key in REQUIRED_FOR_LIVE:
        if key not in cfg or cfg[key].startswith(PLACEHOLDER_MARK):
            problems.append(f"{key} is unset or still a placeholder")
    return problems
