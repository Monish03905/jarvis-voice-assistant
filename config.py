"""JARVIS configuration.

Everything is overridable through environment variables or the .env file.
The defaults are tuned for a local-first setup: Ollama for reasoning,
Edge-TTS for speech, and faster-whisper for transcription.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

def _env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    return default if value is None else value.strip()

def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, "true" if default else "false").lower() in {"1", "true", "yes", "on"}

def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default

def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------- identity
USER_NAME = _env("USER_NAME", "Sir")
ASSISTANT_NAME = _env("ASSISTANT_NAME", "JARVIS")
WAKE_WORD = _env("WAKE_WORD", "hey jarvis").lower()
USER_TITLE = _env("USER_TITLE", USER_NAME)

# ---------------------------------------------------------------- paths
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "jarvis.db"
VOICEPRINT_PATH = DATA_DIR / "voiceprint.npy"
LOG_DIR = ROOT / "logs"
ASSETS_DIR = ROOT / "assets"
FRONTEND_BUILD = ROOT / "frontend" / "build"

# Large, machine-local caches live outside OneDrive so they are not synced.
CACHE_DIR = Path(os.getenv("LOCALAPPDATA", str(DATA_DIR))) / "JARVIS"
MODELS_DIR = CACHE_DIR / "models"
CHROME_PROFILE_DIR = Path(os.getenv("JARVIS_CHROME_PROFILE", str(CACHE_DIR / "chrome-profile")))

for _d in (DATA_DIR, LOG_DIR, ASSETS_DIR, CACHE_DIR, CHROME_PROFILE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- brain
# auto = try Ollama first, then cloud providers that have a real key.
BRAIN_PROVIDER = _env("BRAIN_PROVIDER", "auto").lower()
OLLAMA_HOST = _env("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "qwen3.5:4b")
OLLAMA_FAST_MODEL = _env("OLLAMA_FAST_MODEL", "qwen3:0.6b")
OLLAMA_TIMEOUT = _env_int("OLLAMA_TIMEOUT", 120)

GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")
CLAUDE_API_KEY = _env("CLAUDE_API_KEY")
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-sonnet-4-20250514")

AI_TEMPERATURE = _env_float("AI_TEMPERATURE", 0.6)
AI_MAX_TOKENS = _env_int("AI_MAX_TOKENS", 600)

# ---------------------------------------------------------------- voice
STT_MODEL = _env("STT_MODEL", "base.en")          # tiny.en is faster, small.en smarter
STT_DEVICE = _env("STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = _env("STT_COMPUTE_TYPE", "int8")
WAKE_ENGINE = _env("WAKE_ENGINE", "openwakeword").lower()  # openwakeword | whisper
WAKE_THRESHOLD = _env_float("WAKE_THRESHOLD", 0.55)
MIC_DEVICE = os.getenv("MIC_DEVICE") or None

TTS_ENGINE = _env("TTS_ENGINE", "edge").lower()   # edge | elevenlabs | pyttsx3
TTS_VOICE = _env("TTS_VOICE", "en-GB-RyanNeural")
TTS_RATE = _env("TTS_RATE", "+8%")
VOICE_SPEED = _env_float("VOICE_SPEED", 1.0)
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

# Speaker lock: only accept commands from the enrolled voice.
VOICE_LOCK_ENABLED = _env_bool("VOICE_LOCK_ENABLED", True)
VOICE_MATCH_THRESHOLD = _env_float("VOICE_MATCH_THRESHOLD", 0.78)
VOICE_ENROLL_SECONDS = _env_int("VOICE_ENROLL_SECONDS", 12)

# ---------------------------------------------------------------- safety
CONFIRM_DESTRUCTIVE = _env_bool("CONFIRM_DESTRUCTIVE", True)
CONFIRM_TTL_SECONDS = _env_int("CONFIRM_TTL_SECONDS", 25)
ALLOW_POWER_ACTIONS = _env_bool("ALLOW_POWER_ACTIONS", True)
ALLOW_SHELL = _env_bool("ALLOW_SHELL", False)
ALLOW_FILE_DELETE = _env_bool("ALLOW_FILE_DELETE", True)
PRIVACY_ON_START = _env_bool("PRIVACY_ON_START", False)

# ---------------------------------------------------------------- services
WEATHER_API_KEY = _env("WEATHER_API_KEY")       # optional; Open-Meteo is keyless
WEATHER_CITY = _env("WEATHER_CITY", "Vijayawada")
NEWS_API_KEY = _env("NEWS_API_KEY")             # optional; RSS is keyless
DEFAULT_CITY = _env("DEFAULT_CITY", WEATHER_CITY)
NEWS_FEEDS = _env(
    "NEWS_FEEDS",
    "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en,"
    "https://feeds.bbci.co.uk/news/world/rss.xml,"
    "https://feeds.reuters.com/reuters/worldNews",
)

SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = _env("SMTP_USER")
SMTP_PASS = _env("SMTP_PASS")
IMAP_HOST = _env("IMAP_HOST")
IMAP_PORT = _env_int("IMAP_PORT", 993)

# ---------------------------------------------------------------- mail accounts
# Any account can be added in .env as MAIL_<LABEL>_ADDRESS / MAIL_<LABEL>_PASSWORD.
# Hosts are inferred from the domain; override with MAIL_<LABEL>_SMTP_HOST etc.
EMAIL_DEFAULT_ACCOUNT = _env("EMAIL_DEFAULT_ACCOUNT", "personal").lower()

_MAIL_PRESETS = {
    "gmail.com": ("smtp.gmail.com", 587, False, "imap.gmail.com", 993),
    "googlemail.com": ("smtp.gmail.com", 587, False, "imap.gmail.com", 993),
    "outlook.com": ("smtp.office365.com", 587, False, "outlook.office365.com", 993),
    "hotmail.com": ("smtp.office365.com", 587, False, "outlook.office365.com", 993),
    "live.com": ("smtp.office365.com", 587, False, "outlook.office365.com", 993),
    "msn.com": ("smtp.office365.com", 587, False, "outlook.office365.com", 993),
    "yahoo.com": ("smtp.mail.yahoo.com", 465, True, "imap.mail.yahoo.com", 993),
    "yahoo.in": ("smtp.mail.yahoo.com", 465, True, "imap.mail.yahoo.com", 993),
    "icloud.com": ("smtp.mail.me.com", 587, False, "imap.mail.me.com", 993),
    "me.com": ("smtp.mail.me.com", 587, False, "imap.mail.me.com", 993),
    "zoho.com": ("smtp.zoho.com", 465, True, "imap.zoho.com", 993),
}


def mail_preset(address: str) -> tuple[str, int, bool, str, int]:
    domain = address.rsplit("@", 1)[-1].lower() if "@" in address else ""
    if not domain:
        return "", 587, False, "", 993
    if domain in _MAIL_PRESETS:
        return _MAIL_PRESETS[domain]
    return f"smtp.{domain}", 587, False, f"imap.{domain}", 993


def _load_mail_accounts() -> dict[str, dict]:
    labels = set()
    pattern = re.compile(
        r"MAIL_([A-Z][A-Z0-9_]*)_(ADDRESS|PASSWORD|SMTP_HOST|SMTP_PORT|SMTP_SSL|"
        r"IMAP_HOST|IMAP_PORT|DISPLAY_NAME)$"
    )
    for key in os.environ:
        m = pattern.fullmatch(key.upper())
        if m:
            labels.add(m.group(1).lower())

    accounts: dict[str, dict] = {}
    for label in sorted(labels):
        prefix = f"MAIL_{label.upper()}_"
        address = _env(prefix + "ADDRESS")
        password = _env(prefix + "PASSWORD")
        host, port, ssl, ihost, iport = mail_preset(address)
        smtp_host = _env(prefix + "SMTP_HOST", host)
        imap_host = _env(prefix + "IMAP_HOST", ihost)
        smtp_port = _env_int(prefix + "SMTP_PORT", port)
        accounts[label] = {
            "label": label,
            "display_name": _env(prefix + "DISPLAY_NAME", label.title()),
            "address": address,
            "password": password,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_ssl": _env_bool(prefix + "SMTP_SSL", ssl or smtp_port == 465),
            "imap_host": imap_host,
            "imap_port": _env_int(prefix + "IMAP_PORT", iport),
            "configured": bool(address and password and smtp_host and imap_host),
        }

    # Legacy single-account keys keep working as the "default" account.
    if SMTP_USER and SMTP_PASS and "default" not in accounts:
        host, port, ssl, ihost, iport = mail_preset(SMTP_USER)
        accounts["default"] = {
            "label": "default",
            "display_name": "Default",
            "address": SMTP_USER,
            "password": SMTP_PASS,
            "smtp_host": SMTP_HOST or host,
            "smtp_port": SMTP_PORT or port,
            "smtp_ssl": (SMTP_PORT or port) == 465,
            "imap_host": IMAP_HOST or ihost,
            "imap_port": IMAP_PORT or iport,
            "configured": True,
        }
    if "default" in accounts and EMAIL_DEFAULT_ACCOUNT == "personal":
        EMAIL_DEFAULT_ACCOUNT = "default"
    return accounts


EMAIL_ACCOUNTS = _load_mail_accounts()

# ---------------------------------------------------------------- browser
CHROME_PATH = _env(
    "CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
BROWSER_HEADLESS = _env_bool("BROWSER_HEADLESS", False)
BROWSER_LOGIN_TIMEOUT = _env_int("BROWSER_LOGIN_TIMEOUT", 180)

# ---------------------------------------------------------------- home assistant
HASS_URL = _env("HASS_URL").rstrip("/")
HASS_TOKEN = _env("HASS_TOKEN")
HASS_TIMEOUT = _env_int("HASS_TIMEOUT", 10)

# ---------------------------------------------------------------- modes
MODES = {
    "normal": {
        "label": "Normal",
        "hint": "Everyday assistant",
        "prompt": "Operate normally as a calm, precise personal assistant.",
    },
    "developer": {
        "label": "Developer",
        "hint": "Coding and development",
        "prompt": (
            "Developer mode: favour code, repositories, terminals, debugging and "
            "build tooling. Be precise about commands and file paths."
        ),
    },
    "research": {
        "label": "Research",
        "hint": "Internet research and analysis",
        "prompt": (
            "Research mode: answer with verified, sourced analysis. Separate fact "
            "from inference and cite the sources you used."
        ),
    },
    "system": {
        "label": "System",
        "hint": "Hardware and computer management",
        "prompt": (
            "System mode: focus on hardware, processes, storage, thermals and "
            "performance. Give measured values, not guesses."
        ),
    },
    "vision": {
        "label": "Vision",
        "hint": "Camera and screen analysis",
        "prompt": (
            "Vision mode: describe what is visible on screen or camera plainly, "
            "noting interfaces, text and possible problems."
        ),
    },
    "security": {
        "label": "Security",
        "hint": "Monitoring and alerts",
        "prompt": (
            "Security mode: be vigilant about permissions, unfamiliar processes, "
            "privacy and suspicious requests. Prefer refusing over risking data."
        ),
    },
    "autonomous": {
        "label": "Autonomous",
        "hint": "Multi-step task execution",
        "prompt": (
            "Autonomous mode: break requests into steps, execute safe steps "
            "without asking repeatedly, and report progress concisely."
        ),
    },
}
DEFAULT_MODE = _env("DEFAULT_MODE", "normal").lower()
if DEFAULT_MODE not in MODES:
    DEFAULT_MODE = "normal"

# ---------------------------------------------------------------- server
HOST = _env("HOST", "127.0.0.1")
PORT = _env_int("PORT", 8000)
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()
DEBUG_MODE = _env_bool("DEBUG_MODE", False)
VERSION = _env("JARVIS_VERSION", "3.0.0")
UPDATE_MANIFEST_URL = _env("UPDATE_MANIFEST_URL")

JARVIS_SYSTEM_PROMPT = f"""You are {ASSISTANT_NAME}, a personal AI assistant for {USER_TITLE}.
Speak with a calm, formal British manner. Always address the user as "{USER_TITLE}"
(never "Mr. Stark" or any invented name unless the user asks for a nickname).
Be concise, practical and a little witty. Never invent facts about the user's
system, files, contacts or accounts: if you do not know, say so and offer to
find out. You can control the user's Windows PC, browser, files, email and
phone through tools. When a request matches a tool, use it instead of only
describing it. Keep spoken answers under three sentences unless the user asks
for detail."""


def validate_config() -> list[str]:
    """Return a list of human-readable warnings (never raises)."""
    warnings: list[str] = []
    if BRAIN_PROVIDER in {"auto", "ollama"}:
        try:
            import urllib.request

            urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3).read()
        except Exception:
            warnings.append(
                f"Ollama is not reachable at {OLLAMA_HOST}. Start it with 'ollama serve'."
            )
    if not (GEMINI_API_KEY or OPENAI_API_KEY or CLAUDE_API_KEY):
        warnings.append(
            "No cloud API key configured. JARVIS will run fully local via Ollama."
        )
    if not Path(CHROME_PATH).exists():
        warnings.append(f"Chrome not found at {CHROME_PATH}; browser skills may fail.")
    return warnings


def setup_logging() -> None:
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format=fmt,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / "jarvis.log", encoding="utf-8"),
        ],
    )
