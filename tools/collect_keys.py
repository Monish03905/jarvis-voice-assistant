#!/usr/bin/env python3
"""Store optional provider API keys in .env (hidden input, no shell history).

Run:
    python tools/collect_keys.py

Keys are issued by the providers themselves; this only records the ones you
paste. Press Enter to skip any entry. The file is git-ignored.
"""

from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tools.link_email import read_env, upsert_env

CHOICES = [
    ("GEMINI_API_KEY", "Gemini", "https://aistudio.google.com/apikey"),
    ("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys"),
    ("CLAUDE_API_KEY", "Claude", "https://console.anthropic.com/settings/keys"),
    ("NEWS_API_KEY", "NewsAPI (RSS works without it)", "https://newsapi.org/register"),
]


def main() -> int:
    current = {}
    for line in read_env():
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if match:
            current[match.group(1)] = match.group(2).strip().strip('"')
    print("Optional API keys. Paste at the prompt (hidden) or press Enter to skip.")
    print("JARVIS stays fully local without any of these.\n")
    updates = {}
    for key, label, url in CHOICES:
        state = "already set" if current.get(key) else "empty"
        try:
            value = getpass.getpass(f"{label} [{state}] {url}\n  key (hidden): ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if value.strip():
            updates[key] = value.strip()
    if not updates:
        print("Nothing changed.")
        return 0
    upsert_env(updates)
    print(f"Stored {len(updates)} key(s) in .env. Restart JARVIS to use them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
