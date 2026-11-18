"""SQLite persistence for JARVIS: contacts, memories, money, reminders, history."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, date
from typing import Any, Iterable, Optional

from config import DB_PATH

_LOCK = threading.RLock()
_INITIALISED = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'any',
    handle TEXT,
    phone TEXT,
    email TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_unique
    ON contacts(lower(name), platform);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL DEFAULT 'fact',
    text TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    note TEXT,
    occurred_on TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    period TEXT NOT NULL DEFAULT 'month',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    due_at TEXT,
    done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    priority INTEGER NOT NULL DEFAULT 2,
    due_at TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT,
    location TEXT,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    text TEXT NOT NULL,
    action TEXT,
    success INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal TEXT NOT NULL,
    steps TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init() -> None:
    global _INITIALISED
    if _INITIALISED:
        return
    with _LOCK:
        if _INITIALISED:
            return
        with _connect() as conn:
            conn.executescript(SCHEMA)
        _INITIALISED = True


@contextmanager
def cursor():
    _init()
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ settings
def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with cursor() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with cursor() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


# ------------------------------------------------------------------ contacts
def upsert_contact(
    name: str,
    platform: str = "any",
    handle: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    notes: str | None = None,
) -> None:
    with cursor() as c:
        c.execute(
            """INSERT INTO contacts(name,platform,handle,phone,email,notes,created_at)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(lower(name),platform) DO UPDATE SET
                 handle=COALESCE(excluded.handle, contacts.handle),
                 phone=COALESCE(excluded.phone, contacts.phone),
                 email=COALESCE(excluded.email, contacts.email),
                 notes=COALESCE(excluded.notes, contacts.notes)""",
            (name.strip(), platform, handle, phone, email, notes, _now()),
        )


def find_contact(name: str, platform: str | None = None) -> Optional[dict]:
    with cursor() as c:
        if platform and platform != "any":
            row = c.execute(
                "SELECT * FROM contacts WHERE lower(name) LIKE ? AND (platform=? OR platform='any') "
                "ORDER BY (platform=?) DESC LIMIT 1",
                (f"%{name.lower()}%", platform, platform),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM contacts WHERE lower(name) LIKE ? ORDER BY id LIMIT 1",
                (f"%{name.lower()}%",),
            ).fetchone()
        return dict(row) if row else None


def list_contacts(platform: str | None = None) -> list[dict]:
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM contacts WHERE (? IS NULL OR platform=? OR platform='any') ORDER BY name",
            (platform, platform),
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------ memories
def remember(text: str, kind: str = "fact", importance: int = 3) -> None:
    with cursor() as c:
        c.execute(
            "INSERT INTO memories(kind,text,importance,created_at) VALUES(?,?,?,?)",
            (kind, text.strip(), importance, _now()),
        )


def recall(query: str | None = None, limit: int = 12) -> list[dict]:
    with cursor() as c:
        if query:
            rows = c.execute(
                "SELECT * FROM memories WHERE text LIKE ? ORDER BY importance DESC, id DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM memories ORDER BY importance DESC, id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------ money
def add_transaction(kind: str, amount: float, category: str = "general",
                    note: str = "", occurred_on: str | None = None) -> None:
    day = occurred_on or date.today().isoformat()
    with cursor() as c:
        c.execute(
            "INSERT INTO transactions(kind,amount,category,note,occurred_on,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (kind, float(amount), category.strip().lower() or "general", note, day, _now()),
        )


def set_budget(category: str, amount: float, period: str = "month") -> None:
    with cursor() as c:
        c.execute("DELETE FROM budgets WHERE lower(category)=? AND period=?",
                  (category.strip().lower(), period))
        c.execute(
            "INSERT INTO budgets(category,amount,period,created_at) VALUES(?,?,?,?)",
            (category.strip().lower(), float(amount), period, _now()),
        )


def money_summary(month: str | None = None) -> dict:
    month = month or date.today().strftime("%Y-%m")
    with cursor() as c:
        income = c.execute(
            "SELECT COALESCE(SUM(amount),0) v FROM transactions "
            "WHERE kind='income' AND occurred_on LIKE ?", (month + "%",)
        ).fetchone()["v"]
        spent = c.execute(
            "SELECT COALESCE(SUM(amount),0) v FROM transactions "
            "WHERE kind='expense' AND occurred_on LIKE ?", (month + "%",)
        ).fetchone()["v"]
        by_cat = c.execute(
            "SELECT category, SUM(amount) total FROM transactions "
            "WHERE kind='expense' AND occurred_on LIKE ? GROUP BY category ORDER BY total DESC",
            (month + "%",),
        ).fetchall()
        budgets = c.execute("SELECT * FROM budgets WHERE period='month'").fetchall()
        recent = c.execute(
            "SELECT * FROM transactions ORDER BY id DESC LIMIT 20"
        ).fetchall()
        return {
            "month": month,
            "income": round(income, 2),
            "spent": round(spent, 2),
            "balance": round(income - spent, 2),
            "by_category": [dict(r) for r in by_cat],
            "budgets": [dict(r) for r in budgets],
            "recent": [dict(r) for r in recent],
        }


# ------------------------------------------------------------------ reminders
def add_reminder(text: str, due_at: str | None) -> int:
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO reminders(text,due_at,done,created_at) VALUES(?,?,0,?)",
            (text, due_at, _now()),
        )
        return int(cur.lastrowid)


def due_reminders() -> list[dict]:
    now = datetime.now().isoformat(timespec="minutes")
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM reminders WHERE done=0 AND due_at IS NOT NULL AND due_at<=? "
            "ORDER BY due_at", (now,)
        ).fetchall()
        return [dict(r) for r in rows]


def complete_reminder(reminder_id: int) -> None:
    with cursor() as c:
        c.execute("UPDATE reminders SET done=1 WHERE id=?", (reminder_id,))


def list_reminders(include_done: bool = False) -> list[dict]:
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM reminders WHERE (?=1 OR done=0) ORDER BY done, due_at",
            (1 if include_done else 0,),
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------------------------------------------------------ tasks
def add_task(title: str, priority: int = 2, due_at: str | None = None) -> int:
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO tasks(title,status,priority,due_at,created_at) VALUES(?, 'open', ?, ?, ?)",
            (title.strip(), int(priority), due_at, _now()),
        )
        return int(cur.lastrowid)


def list_tasks(include_done: bool = False) -> list[dict]:
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM tasks WHERE (?=1 OR status='open') ORDER BY status, priority, due_at, id",
            (1 if include_done else 0,),
        ).fetchall()
        return [dict(r) for r in rows]


def complete_task(task_id: int | None = None, match: str | None = None) -> dict | None:
    with cursor() as c:
        row = None
        if task_id is not None:
            row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        elif match:
            row = c.execute(
                "SELECT * FROM tasks WHERE status='open' AND lower(title) LIKE ? "
                "ORDER BY priority, id LIMIT 1",
                (f"%{match.lower()}%",),
            ).fetchone()
        if not row:
            return None
        c.execute(
            "UPDATE tasks SET status='done', completed_at=? WHERE id=?",
            (_now(), row["id"]),
        )
        return dict(row)


# ------------------------------------------------------------------ events
def add_event(title: str, starts_at: str, ends_at: str | None = None,
              location: str | None = None, notes: str | None = None) -> int:
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO events(title,starts_at,ends_at,location,notes,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (title.strip(), starts_at, ends_at, location, notes, _now()),
        )
        return int(cur.lastrowid)


def list_events(day: str | None = None, limit: int = 20) -> list[dict]:
    with cursor() as c:
        if day:
            rows = c.execute(
                "SELECT * FROM events WHERE starts_at LIKE ? ORDER BY starts_at LIMIT ?",
                (f"{day}%", limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM events WHERE starts_at >= ? ORDER BY starts_at LIMIT ?",
                (datetime.now().isoformat(timespec="minutes"), limit),
            ).fetchall()
        return [dict(r) for r in rows]


def agenda(day: str | None = None) -> dict:
    day = day or date.today().isoformat()
    tasks = [t for t in list_tasks() if t["due_at"] is None or t["due_at"].startswith(day)]
    return {
        "day": day,
        "events": list_events(day),
        "tasks": tasks[:10],
        "reminders": [r for r in list_reminders() if not r["due_at"] or r["due_at"].startswith(day)],
    }


# ------------------------------------------------------------------ plans
def add_plan(goal: str, steps: list[dict], status: str = "pending") -> int:
    with cursor() as c:
        cur = c.execute(
            "INSERT INTO plans(goal,steps,status,created_at,updated_at) VALUES(?,?,?,?,?)",
            (goal, json.dumps(steps), status, _now(), _now()),
        )
        return int(cur.lastrowid)


def update_plan(plan_id: int, steps: list[dict] | None = None,
                status: str | None = None) -> None:
    with cursor() as c:
        if steps is not None:
            c.execute(
                "UPDATE plans SET steps=?, status=COALESCE(?, status), updated_at=? WHERE id=?",
                (json.dumps(steps), status, _now(), plan_id),
            )
        else:
            c.execute(
                "UPDATE plans SET status=COALESCE(?, status), updated_at=? WHERE id=?",
                (status, _now(), plan_id),
            )


def recent_plans(limit: int = 10) -> list[dict]:
    with cursor() as c:
        rows = c.execute(
            "SELECT * FROM plans ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["steps"] = json.loads(item["steps"])
            except (TypeError, json.JSONDecodeError):
                item["steps"] = []
            result.append(item)
        return result


# ------------------------------------------------------------------ history
def log_command(source: str, text: str, action: str | None, success: bool) -> None:
    with cursor() as c:
        c.execute(
            "INSERT INTO commands(source,text,action,success,created_at) VALUES(?,?,?,?,?)",
            (source, text, action, 1 if success else 0, _now()),
        )


def log_message(role: str, content: str) -> None:
    with cursor() as c:
        c.execute(
            "INSERT INTO conversations(role,content,created_at) VALUES(?,?,?)",
            (role, content, _now()),
        )


def recent_messages(limit: int = 20) -> list[dict]:
    with cursor() as c:
        rows = c.execute(
            "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


def command_stats() -> dict:
    with cursor() as c:
        total = c.execute("SELECT COUNT(*) v FROM commands").fetchone()["v"]
        ok = c.execute("SELECT COUNT(*) v FROM commands WHERE success=1").fetchone()["v"]
        top = c.execute(
            "SELECT action, COUNT(*) n FROM commands WHERE action IS NOT NULL "
            "GROUP BY action ORDER BY n DESC LIMIT 5"
        ).fetchall()
        return {"total": total, "success": ok, "top_actions": [dict(r) for r in top]}
