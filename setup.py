#!/usr/bin/env python3
"""First-run setup wizard for JARVIS.

Checks the environment, pulls the local model if needed, enrolls your voice,
and warms up the WhatsApp / Instagram browser profiles.
"""

from __future__ import annotations

import getpass
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as cfg

BANNER = r"""
+--------------------------------------------------------------+
|              J.A.R.V.I.S.  FIRST-RUN SETUP                   |
|         Just A Rather Very Intelligent System                |
+--------------------------------------------------------------+
"""


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return answer or default


def check_python() -> bool:
    if sys.version_info < (3, 10):
        print("[X] Python 3.10+ required.")
        return False
    print(f"[OK] Python {sys.version.split()[0]}")
    return True


def check_dependencies() -> bool:
    required = {
        "fastapi": "FastAPI", "uvicorn": "Uvicorn", "selenium": "Selenium",
        "sounddevice": "sounddevice", "faster_whisper": "faster-whisper",
        "edge_tts": "edge-tts", "pywinauto": "pywinauto",
        "pycaw": "pycaw", "resemblyzer": "resemblyzer",
        "openwakeword": "openwakeword", "feedparser": "feedparser",
    }
    missing = []
    for module, label in required.items():
        try:
            __import__(module)
        except Exception:
            missing.append(label)
    if missing:
        print(f"[X] Missing packages: {', '.join(missing)}")
        print("    Run: pip install -r requirements.txt")
        return False
    print("[OK] Python dependencies")
    print("[..] openWakeWord assets download automatically on first listen.")
    return True


def check_ollama() -> None:
    try:
        urllib.request.urlopen(f"{cfg.OLLAMA_HOST}/api/tags", timeout=3).read()
        print(f"[OK] Ollama at {cfg.OLLAMA_HOST}")
    except Exception:
        print("[!] Ollama is not responding.")
        print("    Install from https://ollama.com then run: ollama serve")
        return
    try:
        import json

        data = json.loads(
            urllib.request.urlopen(f"{cfg.OLLAMA_HOST}/api/tags", timeout=5).read()
        )
        names = [m.get("name", "") for m in data.get("models", [])]
        if any(name.startswith(cfg.OLLAMA_MODEL.split(":")[0]) for name in names):
            print(f"[OK] Model {cfg.OLLAMA_MODEL} present")
        else:
            print(f"[!] Model {cfg.OLLAMA_MODEL} not found (have: {', '.join(names) or 'none'})")
            if shutil.which("ollama") and ask(f"Pull {cfg.OLLAMA_MODEL} now? (y/n)", "y").lower().startswith("y"):
                subprocess.run(["ollama", "pull", cfg.OLLAMA_MODEL])
    except Exception:
        pass


def enroll_voice() -> None:
    print("\n--- Voice enrollment -------------------------------------------")
    print("JARVIS will only act on the voice it learns here.")
    if not ask("Enroll your voice now? (y/n)", "y").lower().startswith("y"):
        print("[--] Skipped. Use the HUD's 'Enroll my voice' button later.")
        return
    from backend.voice import VoiceEngine

    engine = VoiceEngine()
    ok, score, mode = engine.enroll()
    if ok:
        print(f"[OK] Voiceprint saved (quality {score:.2f}, engine {mode})")
    else:
        print("[X] Enrollment failed. Check the microphone and try again.")


def browser_logins() -> None:
    print("\n--- WhatsApp / Instagram ---------------------------------------")
    print("These logins live in a dedicated Chrome profile, stored outside OneDrive.")
    if not ask("Open WhatsApp Web to scan the QR code? (y/n)", "y").lower().startswith("y"):
        return
    try:
        from backend.skills import browser

        status = browser.login_status()
        print(f"[..] {status}")
        ask("Press Enter once you are logged in (or to skip)", "")
        browser.close_browser()
    except Exception as exc:
        print(f"[!] Browser check failed: {exc}")


def link_mail() -> None:
    print("\n--- Mail accounts ----------------------------------------------")
    print("Personal and college accounts can both be linked here.")
    print("Use an app password; it is read hidden and written only to .env.")
    if not ask("Link a mail account now? (y/n)", "y").lower().startswith("y"):
        print("[--] Skipped. Run: python tools/link_email.py")
        return
    from tools.link_email import link_account

    link_account()


def collect_keys() -> None:
    print("\n--- Optional API keys ------------------------------------------")
    print("These keys are issued by each provider after you sign in; JARVIS cannot")
    print("create them. Paste one at a time (hidden) or press Enter to skip.")
    from tools.link_email import read_env, upsert_env

    current = {}
    for line in read_env():
        match = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if match:
            current[match.group(1)] = match.group(2).strip().strip('"')
    choices = [
        ("GEMINI_API_KEY", "Gemini", "https://aistudio.google.com/apikey"),
        ("OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys"),
        ("CLAUDE_API_KEY", "Claude", "https://console.anthropic.com/settings/keys"),
        ("NEWS_API_KEY", "NewsAPI (RSS works without it)", "https://newsapi.org/register"),
    ]
    updates = {}
    for key, label, url in choices:
        state = "set" if current.get(key) else "empty"
        try:
            value = getpass.getpass(f"{label} [{state}] {url}\n  key (hidden): ")
        except (EOFError, KeyboardInterrupt):
            print()
            continue
        if value.strip():
            updates[key] = value.strip()
    if updates:
        upsert_env(updates)
        print(f"[OK] Stored {len(updates)} key(s) in .env (never printed).")
    else:
        print("[--] No keys added.")


def add_contact() -> None:
    print("\n--- Contacts ---------------------------------------------------")
    print("Contacts let you say: 'call Amma' or 'WhatsApp Ravi that I am late'.")
    if not ask("Add a contact now? (y/n)", "n").lower().startswith("y"):
        return
    import backend.db as db

    name = ask("Name")
    platform = ask("Platform (whatsapp/instagram/phone/email)", "whatsapp")
    handle = ask("Handle or username (optional)", "")
    phone = ask("Phone number for calls (optional)", "")
    email = ask("Email address (optional)", "")
    if name:
        db.upsert_contact(name, platform, handle or None, phone or None, email or None, None)
        print(f"[OK] Saved {name}")


def main() -> None:
    print(BANNER)
    print(f"Project: {ROOT}")
    print(f"Config:  {ROOT / '.env'}\n")

    if not check_python():
        sys.exit(1)
    if not check_dependencies():
        sys.exit(1)
    check_ollama()
    enroll_voice()
    browser_logins()
    link_mail()
    collect_keys()
    add_contact()

    print("\n--- Ready ------------------------------------------------------")
    print("Start everything with:  python start.py")
    print("The HUD opens at http://127.0.0.1:8000")
    print("Say 'Hey Jarvis' then your command. Press Ctrl+C to stop.")
    print("Mail tools:  python tools/link_email.py --list | --test")


if __name__ == "__main__":
    main()
