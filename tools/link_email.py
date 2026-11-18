#!/usr/bin/env python3
"""Link mail accounts into .env without echoing secrets.

Usage:
    python tools/link_email.py                 # add or update an account
    python tools/link_email.py --list          # show linked labels
    python tools/link_email.py --test          # verify every linked account

Passwords are read with getpass (nothing is printed, nothing hits shell
history) and written only to .env, which is git-ignored.
"""

from __future__ import annotations

import argparse
import getpass
import imaplib
import re
import smtplib
import ssl
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENV_PATH = ROOT / ".env"
LABEL_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def read_env() -> list[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _quote(value: str) -> str:
    value = value or ""
    if not value:
        return ""
    if re.search(r'[\s#"\']', value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def upsert_env(updates: dict[str, str], path: Path = ENV_PATH) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    for i, line in enumerate(lines):
        match = re.match(r"^([A-Z0-9_]+)=", line)
        if match and match.group(1) in updates:
            key = match.group(1)
            lines[i] = f"{key}={_quote(updates[key])}"
            seen.add(key)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={_quote(value)}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def mail_preset(address: str) -> tuple[str, int, bool, str, int]:
    from config import mail_preset as preset

    return preset(address)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        return input(f"{prompt}{suffix}: ").strip() or default
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def test_login(address: str, password: str, smtp_host: str, smtp_port: int,
               smtp_ssl: bool, imap_host: str, imap_port: int) -> tuple[bool, str]:
    context = ssl.create_default_context()
    try:
        client = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=20)
        client.login(address, password)
        client.logout()
    except Exception as exc:
        return False, f"IMAP failed: {exc}"
    try:
        if smtp_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20, context=context)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=20)
            server.starttls(context=context)
        server.login(address, password)
        server.quit()
    except Exception as exc:
        return False, f"SMTP failed: {exc}"
    return True, "IMAP and SMTP login OK"


def link_account() -> int:
    print("\n--- Link a mail account ----------------------------------------")
    print("Gmail / Yahoo / iCloud need an app password, not your normal password.")
    print("College accounts usually work through Google Workspace or Microsoft 365;\n"
          "if auto-detection fails, accept the host prompts and ask your IT desk\n"
          "for the SMTP/IMAP host and port.")
    label = ask("Account label (personal/college/work)").lower()
    while not LABEL_RE.fullmatch(label):
        label = ask("Use lowercase letters, numbers or underscore").lower()
    address = ask("Email address")
    if "@" not in address:
        print("[X] That does not look like an email address.")
        return 2
    default_smtp, default_port, default_ssl, default_imap, default_imap_port = mail_preset(address)
    smtp_host = ask("SMTP host", default_smtp)
    smtp_port = int(ask("SMTP port", str(default_port)) or default_port)
    smtp_ssl = ask("SMTP uses implicit SSL? (y/n)", "y" if default_ssl or smtp_port == 465 else "n").lower().startswith("y")
    imap_host = ask("IMAP host", default_imap)
    imap_port = int(ask("IMAP port", str(default_imap_port)) or default_imap_port)
    display = ask("Display name", label.title())
    password = getpass.getpass("App password (hidden): ")
    if not password:
        print("[X] No password entered.")
        return 2

    print("[..] Checking credentials ...")
    ok, detail = test_login(address, password, smtp_host, smtp_port, smtp_ssl, imap_host, imap_port)
    print(("[OK] " if ok else "[!] ") + detail)
    if not ok and not ask("Save anyway? (y/n)", "n").lower().startswith("y"):
        return 1

    prefix = f"MAIL_{label.upper()}_"
    updates = {
        prefix + "ADDRESS": address,
        prefix + "PASSWORD": password,
        prefix + "SMTP_HOST": smtp_host,
        prefix + "SMTP_PORT": str(smtp_port),
        prefix + "SMTP_SSL": "true" if smtp_ssl else "false",
        prefix + "IMAP_HOST": imap_host,
        prefix + "IMAP_PORT": str(imap_port),
        prefix + "DISPLAY_NAME": display,
    }
    if not any(line.startswith("EMAIL_DEFAULT_ACCOUNT=") for line in read_env()):
        updates["EMAIL_DEFAULT_ACCOUNT"] = label
    upsert_env(updates)
    print(f"[OK] Saved {label} ({address}) to .env. Restart JARVIS to use it.")
    return 0


def list_accounts() -> int:
    labels = set()
    for line in read_env():
        match = re.match(r"^MAIL_([A-Z0-9_]+)_ADDRESS=(.*)$", line)
        if match:
            address = match.group(2).strip().strip('"')
            if address:
                labels.add((match.group(1).lower(), address))
    if not labels:
        print("No mail accounts linked yet. Run: python tools/link_email.py")
        return 1
    print("Linked mail accounts:")
    for label, address in sorted(labels):
        print(f"  - {label}: {address}")
    return 0


def test_all() -> int:
    import config as cfg

    if not cfg.EMAIL_ACCOUNTS:
        print("No mail accounts linked yet. Run: python tools/link_email.py")
        return 1
    from backend.skills import email_skill

    print(email_skill.test_account(None))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Link mail accounts to JARVIS")
    parser.add_argument("--list", action="store_true", help="show linked labels")
    parser.add_argument("--test", action="store_true", help="verify linked accounts")
    args = parser.parse_args()
    if args.list:
        return list_accounts()
    if args.test:
        return test_all()
    return link_account()


if __name__ == "__main__":
    sys.exit(main())
