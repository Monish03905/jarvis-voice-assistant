"""Health checks, dependency updates and self-extension helpers."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import requests

import config as cfg

log = logging.getLogger(__name__)

TRACKED_PACKAGES = [
    "fastapi", "uvicorn", "edge-tts", "faster-whisper", "selenium",
    "feedparser", "openwakeword", "resemblyzer", "pycaw",
]


def _installed(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return ""


def _latest(package: str) -> str:
    try:
        data = requests.get(f"https://pypi.org/pypi/{package}/json", timeout=6).json()
        return data["info"]["version"]
    except Exception:
        return ""


def _ollama_ok() -> bool:
    try:
        requests.get(f"{cfg.OLLAMA_HOST}/api/tags", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def check_updates() -> str:
    outdated = []
    for package in TRACKED_PACKAGES:
        current, newest = _installed(package), _latest(package)
        if current and newest and current != newest:
            outdated.append(f"{package} {current} to {newest}")
    manifest_note = ""
    if cfg.UPDATE_MANIFEST_URL:
        try:
            data = requests.get(cfg.UPDATE_MANIFEST_URL, timeout=6).json()
            remote = str(data.get("version", ""))
            if remote and remote != cfg.VERSION:
                manifest_note = (
                    f" A new JARVIS release {remote} is available: {data.get('notes', '')[:200]}."
                )
        except Exception:
            pass
    if outdated:
        return "Updates available: " + ", ".join(outdated) + "." + manifest_note
    return f"Everything is current, Sir. JARVIS {cfg.VERSION} is up to date." + manifest_note


def apply_updates() -> str:
    """Upgrade tracked packages inside the current virtual environment."""
    packages = []
    for package in TRACKED_PACKAGES:
        current, newest = _installed(package), _latest(package)
        if current and newest and current != newest:
            packages.append(package)
    if not packages:
        return "Nothing to upgrade, Sir."
    try:
        command = ["uv", "pip", "install", "-U", "--python", sys.executable, *packages]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            return f"Updated {', '.join(packages)}, Sir. Restart me to apply them."
        log.warning("update failed: %s", result.stderr[-500:])
        return f"The update failed, Sir. {result.stderr.strip()[:200]}"
    except FileNotFoundError:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-U", *packages],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode == 0:
                return f"Updated {', '.join(packages)}, Sir. Restart me to apply them."
        except Exception as exc:
            return f"The update failed, Sir. {exc}"
    except Exception as exc:
        return f"The update failed, Sir. {exc}"
    return "I could not run the updater, Sir."


def plugins() -> list[str]:
    folder = Path(__file__).resolve().parent / "plugins"
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.py") if not p.name.startswith("_"))


def system_health() -> dict:
    from backend.skills import email_skill, phone
    from backend.voice import list_microphones

    mics = list_microphones()
    voiceprint = Path(cfg.VOICEPRINT_PATH).exists()
    chrome = Path(cfg.CHROME_PATH).exists()
    disk = shutil.disk_usage(str(Path.home().anchor))
    return {
        "version": cfg.VERSION,
        "brain": "ollama" if _ollama_ok() else "offline",
        "ollama_model": cfg.OLLAMA_MODEL,
        "microphones": mics,
        "voiceprint": voiceprint,
        "chrome": chrome,
        "email": email_skill.status(),
        "phone_link": phone.status_cached(),
        "plugins": plugins(),
        "disk_free_gb": round(disk.free / 1e9, 1),
    }


def health_summary() -> str:
    data = system_health()
    parts = [f"JARVIS {data['version']}"]
    parts.append("local brain ready" if data["brain"] == "ollama" else "local brain offline")
    parts.append("voiceprint enrolled" if data["voiceprint"] else "voiceprint missing")
    parts.append(f"{len(data['microphones'])} microphone(s)")
    parts.append("Chrome found" if data["chrome"] else "Chrome missing")
    parts.append("email configured" if data["email"]["smtp"] else "email not configured")
    if data["phone_link"].get("open"):
        parts.append("Phone Link open")
    else:
        parts.append("Phone Link closed")
    return "System check: " + ", ".join(parts) + "."
