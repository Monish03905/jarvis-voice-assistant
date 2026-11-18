#!/usr/bin/env python3
"""Launch JARVIS: checks the environment, starts Ollama if needed, serves the HUD."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config as cfg

BANNER = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
      Just A Rather Very Intelligent System
"""


def ollama_up() -> bool:
    try:
        urllib.request.urlopen(f"{cfg.OLLAMA_HOST}/api/tags", timeout=2).read()
        return True
    except Exception:
        return False


def start_ollama() -> None:
    if ollama_up():
        print("[OK] Ollama is running.")
        return
    exe = shutil.which("ollama")
    if not exe:
        print("[WARN] Ollama not found. Install it from https://ollama.com then run:")
        print("       ollama pull " + cfg.OLLAMA_MODEL)
        return
    print("[..] Starting Ollama in the background...")
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, creationflags=flags)
    for _ in range(20):
        time.sleep(0.5)
        if ollama_up():
            print("[OK] Ollama started.")
            return
    print("[WARN] Ollama did not respond in time. Check 'ollama serve'.")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((cfg.HOST, port))
            return True
        except OSError:
            return False


def open_hud(url: str) -> None:
    for _ in range(90):
        try:
            urllib.request.urlopen(f"{url}/api/status", timeout=2).read()
            break
        except Exception:
            time.sleep(1)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Start JARVIS")
    parser.add_argument("--port", type=int, default=cfg.PORT)
    parser.add_argument("--no-browser", action="store_true", help="do not open the HUD")
    parser.add_argument("--no-voice", action="store_true", help="disable microphone loop")
    args = parser.parse_args()

    print(BANNER)
    cfg.setup_logging()

    if not (cfg.FRONTEND_BUILD / "index.html").exists():
        print("[WARN] No frontend build found. Run:  cd frontend && npm install && npm run build")
    if args.no_voice:
        os.environ["VOICE_DISABLED"] = "1"

    start_ollama()

    if not port_free(args.port):
        print(f"[ERROR] Port {args.port} is already in use. JARVIS may already be running:")
        print(f"        http://{cfg.HOST}:{args.port}")
        sys.exit(1)

    url = f"http://{cfg.HOST}:{args.port}"
    if not args.no_browser:
        threading.Thread(target=open_hud, args=(url,), daemon=True).start()

    print(f"[OK] HUD      -> {url}")
    print(f"[OK] Brain    -> {cfg.OLLAMA_MODEL} via {cfg.OLLAMA_HOST}")
    print(f"[OK] Voice    -> {'enrolled' if cfg.VOICEPRINT_PATH.exists() else 'not enrolled yet'}")
    print("[..] Starting server. Press Ctrl+C to stop.\n")

    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=cfg.HOST,
        port=args.port,
        log_level=cfg.LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nJARVIS offline.")
