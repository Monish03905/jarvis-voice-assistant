"""Tasks, calendar events and the daily agenda."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

import backend.db as db

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_PRIORITY_WORDS = {
    "urgent": 1, "high": 1, "important": 1, "critical": 1,
    "medium": 2, "normal": 2, "low": 3, "someday": 3,
}


def parse_priority(text: str) -> int:
    lowered = (text or "").lower()
    for word, value in _PRIORITY_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return value
    return 2


def parse_when(when: str, base: Optional[datetime] = None) -> Optional[str]:
    """Turn spoken time phrases into an ISO timestamp (minutes precision)."""
    text = (when or "").strip().lower()
    if not text:
        return None
    now = base or datetime.now()
    day = now.date()
    explicit_day = False

    if re.search(r"\bday after tomorrow\b", text):
        day = now.date() + timedelta(days=2)
        explicit_day = True
    elif re.search(r"\btomorrow\b", text):
        day = now.date() + timedelta(days=1)
        explicit_day = True
    elif re.search(r"\b(today|tonight)\b", text):
        day = now.date()
        explicit_day = True

    if not explicit_day:
        iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if iso:
            try:
                day = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
                explicit_day = True
            except ValueError:
                pass

    if not explicit_day:
        dated = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?"
            r"(january|february|march|april|may|june|july|august|september|october|november|december"
            r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
            text,
        )
        if dated:
            try:
                day = date(now.year, _MONTHS[dated.group(2)], int(dated.group(1)))
                if day < now.date():
                    day = date(now.year + 1, day.month, day.day)
                explicit_day = True
            except ValueError:
                pass

    if not explicit_day:
        named = re.search(
            r"\b(next\s+|this\s+|on\s+|coming\s+)?"
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", text
        )
        if named:
            target = _WEEKDAYS[named.group(2)]
            ahead = (target - now.weekday()) % 7
            if named.group(1) and named.group(1).startswith("next"):
                ahead = ahead or 7
            elif ahead == 0 and not re.search(r"\bat\b|\d", text):
                ahead = 7
            day = now.date() + timedelta(days=ahead)
            explicit_day = True

    relative = re.search(
        r"\bin\s+(\d+)\s*(minutes?|mins?|hours?|hrs?|days?|weeks?)\b", text
    )
    if relative:
        value = int(relative.group(1))
        unit = relative.group(2)
        if unit.startswith("min"):
            delta = timedelta(minutes=value)
        elif unit.startswith("hour") or unit.startswith("hr"):
            delta = timedelta(hours=value)
        elif unit.startswith("week"):
            delta = timedelta(weeks=value)
        else:
            delta = timedelta(days=value)
        return (now + delta).replace(second=0, microsecond=0).isoformat(timespec="minutes")

    hour: Optional[int] = None
    minute = 0
    if re.search(r"\bnoon\b", text):
        hour = 12
    elif re.search(r"\bmidnight\b", text):
        hour = 0
        day = day + timedelta(days=1) if not explicit_day else day
    else:
        clock = (
            re.search(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", text)
            or re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)", text)
            or re.search(r"\b(\d{1,2}):(\d{2})\b", text)
            or (re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", text) if explicit_day else None)
        )
        if clock:
            hour = int(clock.group(1))
            minute = int(clock.group(2) or 0)
            meridiem = ""
            if clock.re.groups >= 3:
                meridiem = (clock.group(3) or "").replace(".", "")
            if meridiem == "pm" and hour < 12:
                hour += 12
            if meridiem == "am" and hour == 12:
                hour = 0
            if not meridiem and hour <= 7:
                hour += 12  # "at 5" in the evening is the useful default
            if not meridiem and "tonight" in text and hour < 12:
                hour += 12

    if hour is None:
        if not explicit_day:
            return None
        hour = 9

    if hour > 23 or minute > 59:
        return None
    target = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    if not explicit_day and target < now:
        target += timedelta(days=1)
    return target.isoformat(timespec="minutes")


_WHEN_TAIL = [
    r"\s+(?:by|at|on|due)\s+.+$",
    r"\s+tomorrow.*$",
    r"\s+tonight.*$",
    r"\s+next\s+\w+.*$",
    r"\s+in\s+\d+\s+\w+.*$",
]


def split_title_when(text: str) -> tuple[str, Optional[str]]:
    """Separate 'call mum tomorrow at 5' into its title and timestamp."""
    text = (text or "").strip(" .,!?")
    due = parse_when(text)
    if not due:
        return text, None
    for pattern in _WHEN_TAIL:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        candidate = text[:match.start()].strip(" ,")
        if candidate and parse_when(text[match.start():]) == due:
            return candidate, due
    return text, due


def _human(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        value = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    today = date.today()
    if value.date() == today:
        prefix = "today"
    elif value.date() == today + timedelta(days=1):
        prefix = "tomorrow"
    else:
        prefix = value.strftime("%a %d %b")
    return f"{prefix} {value.strftime('%I:%M %p').lstrip('0')}".strip()


# ------------------------------------------------------------------ tasks
def add(title: str, when: str = "", priority: int = 2) -> str:
    title = (title or "").strip(" .,!?")
    if not title:
        return "What should the task be, Sir?"
    due = parse_when(when) if when else None
    if due is None:
        title, due = split_title_when(title)
    db.add_task(title, priority, due)
    suffix = f", due {_human(due)}" if due else ""
    return f"Task added: {title}{suffix}."


def complete(match: str) -> str:
    row = db.complete_task(match=match)
    if not row:
        return f"I could not find an open task matching {match}, Sir."
    return f"Done: {row['title']}."


def list_text(include_done: bool = False) -> str:
    rows = db.list_tasks(include_done)
    if not rows:
        return "You have no open tasks, Sir."
    open_rows = [r for r in rows if r["status"] != "done"]
    done = [r for r in rows if r["status"] == "done"]
    parts: list[str] = []
    for row in open_rows[:10]:
        due = f" ({_human(row['due_at'])})" if row["due_at"] else ""
        priority = "high priority" if row["priority"] == 1 else ""
        tag = f" [{priority}]" if priority else ""
        parts.append(f"{row['title']}{due}{tag}")
    text = f"You have {len(open_rows)} open task{'s' if len(open_rows) != 1 else ''}: " + "; ".join(parts) + "."
    if include_done and done:
        text += f" {len(done)} completed."
    return text


def next_task_text() -> str:
    rows = [r for r in db.list_tasks() if r["status"] == "open"]
    if not rows:
        return "You have no open tasks, Sir."
    row = rows[0]
    due = f", due {_human(row['due_at'])}" if row["due_at"] else ""
    return f"Your next task is {row['title']}{due}."


# ------------------------------------------------------------------ events
def add_event(title: str, when: str = "", location: str = "", notes: str = "") -> str:
    title = (title or "").strip(" .,!?")
    if not title:
        return "What is the event, Sir?"
    starts = parse_when(when) if when else None
    if starts is None:
        title, starts = split_title_when(title)
    if not starts:
        starts = datetime.combine(date.today(), datetime.min.time()).replace(hour=9).isoformat(
            timespec="minutes"
        )
    db.add_event(title, starts, location=location or None, notes=notes or None)
    where = f" at {location}" if location else ""
    return f"Added to your calendar: {title}, {_human(starts)}{where}."


def agenda_text(day: Optional[str] = None) -> str:
    data = db.agenda(day)
    day_value = date.fromisoformat(data["day"])
    if day_value == date.today():
        label = "today"
    elif day_value == date.today() + timedelta(days=1):
        label = "tomorrow"
    else:
        label = day_value.strftime("%A, %d %B")
    events, tasks, reminders = data["events"], data["tasks"], data["reminders"]
    if not (events or tasks or reminders):
        upcoming = [
            task for task in db.list_tasks()
            if task["due_at"] and not task["due_at"].startswith(data["day"])
        ]
        if upcoming:
            nxt = upcoming[0]
            return (
                f"Your agenda for {label} is clear, Sir. Next up: {nxt['title']} "
                f"({_human(nxt['due_at'])})."
            )
        return f"Your agenda for {label} is clear, Sir."
    parts: list[str] = [f"Your agenda for {label}:"]
    for event in events:
        time = _event_time(event["starts_at"])
        location = f" at {event['location']}" if event.get("location") else ""
        parts.append(f"{time} {event['title']}{location}.")
    if tasks:
        parts.append("Tasks: " + "; ".join(task["title"] for task in tasks[:8]) + ".")
    if reminders:
        parts.append("Reminders: " + "; ".join(r["text"] for r in reminders[:6]) + ".")
    return " ".join(parts)


def _event_time(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return iso


def agenda_data(day: Optional[str] = None) -> dict:
    data = db.agenda(day)
    today = data["day"]
    upcoming_tasks = [
        task for task in db.list_tasks()
        if task["due_at"] and not task["due_at"].startswith(today)
    ][:6]
    upcoming_events = [
        event for event in db.list_events(limit=20)
        if not event["starts_at"].startswith(today)
    ][:4]
    return {
        "day": data["day"],
        "events": [
            {**event, "time": _event_time(event["starts_at"])} for event in data["events"]
        ],
        "tasks": data["tasks"],
        "reminders": data["reminders"],
        "upcoming_tasks": [
            {**task, "human_due": _human(task["due_at"])} for task in upcoming_tasks
        ],
        "upcoming_events": [
            {**event, "time": _event_time(event["starts_at"]), "human_due": _human(event["starts_at"])}
            for event in upcoming_events
        ],
    }
