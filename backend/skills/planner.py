"""Autonomous multi-step planning and execution helpers."""

from __future__ import annotations

import logging
import re
from typing import Optional

import backend.db as db
from backend.brain import brain

log = logging.getLogger(__name__)

# Actions a plan may contain. Dangerous or irreversible actions are excluded:
# they stay individually confirmed, never buried inside a plan.
PLANNABLE = {
    "open_app", "close_app", "switch_app", "minimize_all", "list_open_apps",
    "set_volume", "set_brightness", "get_cpu_ram_usage", "get_system_info",
    "get_battery_status", "get_ip_address", "disk_usage", "screenshot",
    "open_website", "search_google", "play_youtube", "play_pause_media",
    "create_folder", "create_file", "list_files", "search_file", "open_file",
    "organize_folder", "send_email", "read_emails", "email_accounts",
    "sync_email_contacts", "send_whatsapp", "send_instagram", "open_whatsapp",
    "get_weather", "get_news", "news_briefing", "web_search", "wikipedia_search",
    "add_task", "list_tasks", "complete_task", "next_task", "add_event",
    "agenda_summary", "add_expense", "add_income", "budget_status",
    "budget_advice", "remember", "recall", "add_reminder", "list_reminders",
    "system_health", "gpu_stats", "temperatures", "diagnose_slowdown",
    "check_updates", "analyze_screen", "read_screen_text", "camera_look",
    "home_status", "home_turn", "home_light", "home_climate", "home_scene",
    "deep_research", "set_mode",
}

EXTERNAL = {"send_email", "send_whatsapp", "send_instagram", "open_whatsapp"}

MAX_STEPS = 8


def _step(action: str, **parameters) -> dict:
    return {"action": action, "parameters": parameters, "say": ""}


def heuristic_plan(goal: str) -> Optional[list[dict]]:
    """Fast, dependable plans for the workflows JARVIS should never fumble."""
    t = goal.lower().strip()

    if re.search(r"prepare (?:my )?(?:laptop|workstation|computer|pc|desk).*", t) or re.search(
        r"(?:development|coding) (?:setup|environment)", t
    ):
        steps = [
            _step("get_cpu_ram_usage"),
            _step("open_app", name="vscode"),
            _step("open_app", name="terminal"),
        ]
        folder = re.search(r"(?:workspace|project|folder)[ ]+(.+)$", t)
        if folder:
            steps.append(_step("list_files", directory=folder.group(1).strip()))
        steps.append(_step("system_health"))
        return steps

    if re.search(r"(?:start|begin|run) (?:my )?(?:day|morning)|morning routine", t):
        return [
            _step("agenda_summary"),
            _step("get_weather"),
            _step("read_emails", limit=5),
            _step("news_briefing", count=5),
        ]

    if re.search(r"(?:full|complete) (?:diagnostic|checkup)|check (?:my|the) (?:system|pc|laptop)", t):
        return [
            _step("system_health"),
            _step("get_cpu_ram_usage"),
            _step("gpu_stats"),
            _step("temperatures"),
            _step("diagnose_slowdown"),
        ]

    if re.search(r"organi[sz]e (?:my )?downloads", t):
        return [_step("organize_folder", directory="Downloads")]

    if re.search(r"(?:close|quit) (?:all|everything|my apps)", t):
        return [
            _step("close_app", name="chrome"),
            _step("close_app", name="msedge"),
            _step("close_app", name="code"),
            _step("close_app", name="Spotify"),
        ]

    return None


def make_plan(goal: str, history: Optional[list[dict]] = None) -> tuple[list[dict], str]:
    """Return (steps, note). Falls back to a single intent when planning fails."""
    goal = (goal or "").strip()
    if not goal:
        return [], "I need a goal to plan against, Sir."

    fast = heuristic_plan(goal)
    if fast:
        return fast, "Prepared from a known workflow."

    steps = brain.plan(goal, history)
    cleaned = _validate(steps)
    if cleaned:
        return cleaned, "Planned by the reasoning engine."

    intent = brain.parse_intent(goal, history)
    if intent.get("action") not in {"chat", "run_plan"}:
        return [_step(intent["action"], **(intent.get("parameters") or {}))], "Mapped to a single action."
    return [], "I could not break that into reliable steps, Sir."


def _validate(steps: list[dict]) -> list[dict]:
    result: list[dict] = []
    for raw in steps or []:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action", "")).strip()
        if action not in PLANNABLE:
            continue
        params = raw.get("parameters") or raw.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        say = str(raw.get("say") or "").strip()
        result.append({"action": action, "parameters": params, "say": say})
        if len(result) >= MAX_STEPS:
            break
    return result


def needs_confirmation(steps: list[dict]) -> bool:
    return any(step["action"] in EXTERNAL for step in steps)


def describe(steps: list[dict]) -> str:
    names = [step["action"].replace("_", " ") for step in steps]
    return ", then ".join(names)


class PlanRun:
    """Tracks one execution so the HUD and the database stay in sync."""

    def __init__(self, goal: str, steps: list[dict]) -> None:
        self.goal = goal
        self.steps = [dict(step, status="pending", result="") for step in steps]
        self.id = db.add_plan(goal, self.steps, status="running")

    def mark(self, index: int, status: str, result: str = "") -> None:
        self.steps[index]["status"] = status
        self.steps[index]["result"] = result
        db.update_plan(self.id, self.steps)

    def finish(self, status: str = "done") -> None:
        db.update_plan(self.id, self.steps, status=status)
