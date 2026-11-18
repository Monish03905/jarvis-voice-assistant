"""Multi-account email: send through SMTP and read through IMAP.

Accounts are declared in .env as ``MAIL_<LABEL>_ADDRESS`` /
``MAIL_<LABEL>_PASSWORD`` (plus optional host/port overrides). Any number of
accounts can coexist: personal, college, work, and so on.
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import smtplib
import ssl
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Optional

import config as cfg
import backend.db as db

log = logging.getLogger(__name__)


# --------------------------------------------------------------------- helpers
def _accounts() -> dict[str, dict]:
    return cfg.EMAIL_ACCOUNTS


def configured(account: Optional[str] = None) -> bool:
    if account:
        acc = resolve_account(account)
        return bool(acc and acc["configured"])
    return any(acc["configured"] for acc in _accounts().values())


def _labels() -> str:
    return ", ".join(acc["label"] for acc in _accounts().values()) or "none"


def resolve_account(account: Optional[str]) -> Optional[dict]:
    """Turn 'college', 'my college email', or an address into an account."""
    accounts = _accounts()
    if not accounts:
        return None
    if not account:
        preferred = accounts.get(cfg.EMAIL_DEFAULT_ACCOUNT)
        if preferred and preferred["configured"]:
            return preferred
        ready = [acc for acc in accounts.values() if acc["configured"]]
        if ready:
            return ready[0]
        return preferred or next(iter(accounts.values()))
    key = account.strip().lower()
    if key in accounts:
        return accounts[key]
    for acc in accounts.values():
        if key in (acc["address"].lower(), acc["display_name"].lower()):
            return acc
    for label, acc in accounts.items():
        if label in key:
            return acc
    return None


def _resolve_address(to: str) -> Optional[str]:
    raw = (to or "").strip().strip("<>")
    if "@" in raw:
        return raw
    key = raw.lower()
    if key in {"me", "myself", "my email", "my inbox"}:
        acc = resolve_account(None)
        return acc["address"] if acc and acc["address"] else None
    if any(label in key for label in _accounts()):
        acc = resolve_account(raw)
        if acc and acc["address"]:
            return acc["address"]
    contact = db.find_contact(raw)
    if contact and contact.get("email"):
        return contact["email"]
    return None


def _smtp(account: dict) -> smtplib.SMTP:
    context = ssl.create_default_context()
    if account["smtp_ssl"]:
        return smtplib.SMTP_SSL(
            account["smtp_host"], account["smtp_port"], timeout=25, context=context
        )
    server = smtplib.SMTP(account["smtp_host"], account["smtp_port"], timeout=25)
    server.starttls(context=context)
    return server


def _imap(account: dict) -> imaplib.IMAP4_SSL:
    client = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"], timeout=25)
    client.login(account["address"], account["password"])
    return client


def _decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def _snippet(message: email.message.Message, limit: int = 180) -> str:
    try:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain" and part.get_payload(decode=True):
                    text = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace"
                    )
                    return re.sub(r"\s+", " ", text).strip()[:limit]
            return ""
        payload = message.get_payload(decode=True)
        if payload:
            return re.sub(
                r"\s+", " ",
                payload.decode(message.get_content_charset() or "utf-8", "replace"),
            ).strip()[:limit]
    except Exception:
        pass
    return ""


def _fetch_inbox(account: dict, limit: int) -> list[dict]:
    client = _imap(account)
    try:
        client.select("INBOX", readonly=True)
        status, data = client.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()[-max(1, min(limit, 15)):][::-1]
        rows = []
        for msg_id in ids:
            status, payload = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not payload:
                continue
            message = email.message_from_bytes(payload[0][1])
            rows.append(
                {
                    "sender": _decode(message.get("From", "")),
                    "subject": _decode(message.get("Subject", "(no subject)")),
                    "snippet": _snippet(message),
                }
            )
        return rows
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _unconfigured_hint(account: Optional[str]) -> str:
    if not _accounts():
        return (
            "No email account is linked yet, Sir. Run: "
            "python tools/link_email.py — it asks for the address and app password "
            "locally and never prints them."
        )
    if account:
        return (
            f"The {account} account is incomplete, Sir. Set both "
            f"MAIL_{account.upper()}_ADDRESS and MAIL_{account.upper()}_PASSWORD in .env."
        )
    return (
        f"Labels {_labels()} exist, but none has credentials yet, Sir. Run "
        "python tools/link_email.py (or fill MAIL_<LABEL>_ADDRESS and _PASSWORD)."
    )


# ------------------------------------------------------------------ public API
def send_email(to: str, subject: str, body: str, account: Optional[str] = None) -> str:
    acc = resolve_account(account)
    if acc is None:
        return f"I do not recognise that mail account, Sir. Linked accounts: {_labels()}."
    if not acc["configured"]:
        return _unconfigured_hint(acc["label"])
    address = _resolve_address(to)
    if not address:
        return (
            f"I do not have an email address for {to}, Sir. "
            "Use the full address, or save the contact first."
        )
    subject = subject or "A message from JARVIS"
    try:
        message = EmailMessage()
        message["From"] = f"{acc['display_name']} <{acc['address']}>"
        message["To"] = address
        message["Subject"] = subject
        message.set_content(body or "")
        with _smtp(acc) as server:
            server.login(acc["address"], acc["password"])
            server.send_message(message)
        return f"Email sent to {address} from your {acc['label']} account, Sir."
    except Exception as exc:
        log.warning("send_email via %s failed: %s", acc["label"], exc)
        return f"I could not send the email through {acc['label']}, Sir. {exc}"


def _read_one(acc: dict, limit: int) -> str:
    try:
        rows = _fetch_inbox(acc, limit)
    except Exception as exc:
        log.warning("read_emails via %s failed: %s", acc["label"], exc)
        return f"I could not read the {acc['label']} inbox, Sir. {exc}"
    if not rows:
        return f"Your {acc['label']} inbox is empty, Sir."
    lines = [
        f"From {row['sender']}: {row['subject']}." + (f" {row['snippet']}" if row["snippet"] else "")
        for row in rows
    ]
    return f"Latest from your {acc['label']} account. " + " | ".join(lines)


def read_emails(limit: int = 5, account: Optional[str] = None) -> str:
    if account:
        acc = resolve_account(account)
        if acc is None:
            return f"I do not recognise that mail account, Sir. Linked accounts: {_labels()}."
        if not acc["configured"]:
            return _unconfigured_hint(acc["label"])
        return _read_one(acc, limit)

    ready = [acc for acc in _accounts().values() if acc["configured"]]
    if not ready:
        return _unconfigured_hint(None)
    if len(ready) == 1:
        return _read_one(ready[0], limit)
    return " ".join(_read_one(acc, limit) for acc in ready)


def email_summary(limit: int = 8) -> str:
    """Plain text block intended for the language model."""
    ready = [acc for acc in _accounts().values() if acc["configured"]]
    if not ready:
        return ""
    blocks = []
    for acc in ready:
        try:
            rows = _fetch_inbox(acc, limit)
        except Exception:
            continue
        if not rows:
            continue
        lines = [
            f"- {row['subject']} from {row['sender']}: {row['snippet'][:120]}"
            for row in rows
        ]
        blocks.append(f"[{acc['label']}] " + "\n".join(lines))
    return "\n".join(blocks)


def accounts_summary() -> str:
    if not _accounts():
        return _unconfigured_hint(None)
    parts = []
    for acc in _accounts().values():
        if acc["configured"]:
            state = "ready"
        elif acc["address"]:
            state = "missing password"
        else:
            state = "not linked"
        parts.append(f"{acc['label']} ({acc['address'] or 'no address'}, {state})")
    return "Linked mail accounts, Sir: " + "; ".join(parts) + "."


def sync_contacts(limit: int = 40, account: Optional[str] = None) -> str:
    """Learn the people in your inbox as contacts (platform 'email')."""
    if account:
        targets = [resolve_account(account)]
    else:
        targets = [acc for acc in _accounts().values() if acc["configured"]]
    targets = [acc for acc in targets if acc]
    if not targets:
        return _unconfigured_hint(account)
    learned = 0
    for acc in targets:
        try:
            rows = _fetch_inbox(acc, limit)
        except Exception as exc:
            log.warning("sync_contacts via %s failed: %s", acc["label"], exc)
            continue
        for row in rows:
            name, address = parseaddr(row["sender"])
            if not address or "@" not in address:
                continue
            db.upsert_contact(name or address.split("@")[0], "email", email=address)
            learned += 1
    if not learned:
        return "I could not find any new email contacts, Sir."
    return f"Imported {learned} email contacts into your address book, Sir."


def test_account(account: Optional[str] = None) -> str:
    """Verify credentials without sending mail."""
    targets = (
        [resolve_account(account)]
        if account
        else [acc for acc in _accounts().values() if acc["configured"]]
    )
    targets = [acc for acc in targets if acc]
    if not targets:
        return _unconfigured_hint(account)
    results = []
    for acc in targets:
        if not acc["configured"]:
            results.append(f"{acc['label']}: not configured")
            continue
        try:
            client = _imap(acc)
            client.logout()
            with _smtp(acc) as server:
                server.login(acc["address"], acc["password"])
            results.append(f"{acc['label']}: login OK")
        except Exception as exc:
            results.append(f"{acc['label']}: failed ({exc})")
    return "; ".join(results)


def status() -> dict:
    accounts = [
        {
            "label": acc["label"],
            "address": acc["address"],
            "configured": acc["configured"],
            "smtp": acc["smtp_host"],
            "imap": acc["imap_host"],
        }
        for acc in _accounts().values()
    ]
    ready = [acc for acc in accounts if acc["configured"]]
    default = resolve_account(None)
    return {
        "smtp": bool(ready),
        "imap": bool(ready),
        "account": default["address"] if default else "",
        "default": default["label"] if default else "",
        "accounts": accounts,
    }
