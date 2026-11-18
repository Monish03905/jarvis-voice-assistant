"""JARVIS agent: command routing, safety, voice lock and proactive loops."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import config as cfg
import backend.db as db
from backend.brain import brain
from backend.voice import VoiceEngine
from backend.skills import (
    browser, email_skill, files, finance, hardware, home, info, news, phone,
    planner, research, security, system_control, updater, vision,
)
from backend.skills import tasks as tasks_skill

log = logging.getLogger(__name__)

HudEmit = Callable[[Dict[str, Any]], Any]

DESTRUCTIVE = {
    "shutdown", "restart", "delete_file", "empty_recycle_bin",
    "sleep_mode", "hibernate", "apply_updates",
}

SLOW_ACTIONS = {"send_whatsapp", "send_instagram", "play_youtube", "call_contact",
                "open_whatsapp", "read_emails", "phone_diagnose", "check_updates",
                "apply_updates", "system_health", "test_email", "sync_email_contacts",
                "deep_research", "quick_research", "analyze_screen", "read_screen_text",
                "camera_look", "diagnose_slowdown", "home_status"}


def _seconds(text: str) -> int:
    match = re.search(r"in\s+(\d+)\s*(second|sec|minute|min|hour|hr)", text)
    if not match:
        return 10
    value = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("min"):
        return value * 60
    if unit.startswith("hour") or unit == "hr":
        return value * 3600
    return value


def _clean_name(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip(" .,!?\"'"))


class JarvisAgent:
    def __init__(self, hud_emit: HudEmit) -> None:
        self.voice = VoiceEngine()
        self.hud_emit = hud_emit
        self.history: list[dict] = db.recent_messages(10)
        self.pending: Optional[dict] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tasks: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._plugins = self._load_plugins()
        self._last_news_push = 0.0
        self._last_update_check = 0.0
        self._voice_warned = False
        self.mode = cfg.DEFAULT_MODE
        security.set_privacy(cfg.PRIVACY_ON_START)
        brain.set_mode(self.mode)

    # ------------------------------------------------------------------ boot
    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if security.privacy_enabled():
            log.info("Privacy mode is on at boot; microphone stays off.")
        else:
            self.voice.start(self._voice_callback, self._voice_state)
        self._tasks = [
            asyncio.create_task(self._reminder_loop(), name="reminders"),
            asyncio.create_task(self._news_loop(), name="news"),
            asyncio.create_task(self._update_loop(), name="updates"),
        ]
        await self._emit({"type": "agent", "state": "LISTENING"})
        log.info("Agent online. Voice lock=%s enrolled=%s", cfg.VOICE_LOCK_ENABLED, self.voice.enrolled)
        if self.voice.enrolled:
            await self.say("Systems online. Voice recognition active. At your service.")
        else:
            await self.say("Systems online. I have not learned your voice yet, so say: Jarvis, enroll my voice.")

    async def stop(self) -> None:
        self.voice.stop()
        for task in self._tasks:
            task.cancel()
        await self._emit({"type": "agent", "state": "OFFLINE"})

    # ------------------------------------------------------------- callbacks
    def _voice_callback(self, text: str, verified: bool, score: float) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self.handle_command(text, source="voice", verified=verified, score=score),
            self._loop,
        )

    def _voice_state(self, state: str) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._emit({"type": "voice", "state": state}), self._loop
        )

    async def _emit(self, payload: Dict[str, Any]) -> None:
        try:
            result = self.hud_emit(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def say(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        await self._emit({"type": "transcript", "speaker": "jarvis", "message": text})
        await self._emit({"type": "agent", "state": "SPEAKING"})
        await asyncio.to_thread(self.voice.speaker.speak, text)
        await self._emit({"type": "agent", "state": "LISTENING"})

    # --------------------------------------------------------------- command
    async def handle_command(self, text: str, source: str = "ui",
                             verified: bool = True, score: float = 1.0) -> str:
        try:
            return await self._handle_command(text, source, verified, score)
        except Exception as exc:
            log.exception("command failed: %s", exc)
            reply = "Something went wrong on my side, Sir. I have logged it."
            try:
                await self.say(reply)
            except Exception:
                pass
            return reply

    async def _handle_command(self, text: str, source: str,
                              verified: bool, score: float) -> str:
        text = _clean_name(text)
        if not text:
            return ""
        await self._emit({"type": "transcript", "speaker": "user", "message": text})
        db.log_message("user", text)

        # speaker lock
        if (
            source == "voice"
            and cfg.VOICE_LOCK_ENABLED
            and self.voice.enrolled
            and not verified
        ):
            reply = "I do not recognise that voice, so I will not act on it."
            db.log_command(source, text, "rejected_speaker", False)
            await self.say(reply)
            return reply
        if (
            source == "voice"
            and cfg.VOICE_LOCK_ENABLED
            and not self.voice.enrolled
            and not self._voice_warned
        ):
            self._voice_warned = True
            await self._emit({"type": "toast", "message": "Voiceprint not enrolled - say 'enroll my voice'."})

        async with self._lock:
            reply = await self._dispatch(text, source, verified)
        if reply:
            db.log_message("jarvis", reply)
            self.history.append({"role": "assistant", "content": reply})
            self.history = self.history[-16:]
        return reply

    async def _dispatch(self, text: str, source: str, verified: bool) -> str:
        if security.halted():
            answer = text.lower().strip(" .!?")
            if answer in {"resume", "stand down", "all clear", "resume operations",
                          "cancel emergency", "emergency stop off"}:
                return await self._control("resume", {})
            reply = "Emergency stop is engaged, Sir. Say resume when you want me active again."
            await self.say(reply)
            return reply

        # pending confirmation?
        if self.pending and time.time() > self.pending.get("expires", 0):
            self.pending = None
        if self.pending:
            answer = text.lower().strip(" .!?")
            if answer in {"yes", "yeah", "yep", "confirm", "do it", "proceed", "go ahead"}:
                intent = self.pending["intent"]
                self.pending = None
                if intent["action"] == "run_plan":
                    reply = await self._run_plan(
                        intent["parameters"].get("goal", ""), source, confirmed=True
                    )
                else:
                    reply = await self._run_action(intent["action"], intent["parameters"], source)
                await self.say(reply)
                return reply
            if answer in {"no", "nope", "cancel", "stop", "abort"}:
                self.pending = None
                reply = "Cancelled, Sir."
                await self.say(reply)
                return reply
            self.pending = None  # a new command supersedes the question

        if text.lower().strip(" .!?") in {"stop", "shut up", "be quiet", "silence"}:
            reply = "Standing by."
            await self.say(reply)
            return reply

        intent = self._fast_intent(text)
        origin = "fast"
        if intent is None:
            await self._emit({"type": "agent", "state": "THINKING"})
            try:
                intent = await asyncio.wait_for(
                    asyncio.to_thread(brain.parse_intent, text, self.history), timeout=25
                )
            except asyncio.TimeoutError:
                intent = {"action": "chat", "parameters": {}, "confidence": 0.0, "speech": ""}
            origin = "llm"

        action = intent.get("action", "chat")
        confidence = float(intent.get("confidence", 0.0) or 0.0)

        if action == "chat" or confidence < 0.35:
            return await self._converse(text)

        if intent.get("speech"):
            await self.say(intent["speech"])

        if action in {"set_mode", "privacy_on", "privacy_off", "emergency_stop", "resume"}:
            reply = await self._control(action, intent.get("parameters") or {})
            await self.say(reply)
            db.log_command(source, text, action, success=True)
            return reply

        if action in {"plan", "run_plan"}:
            goal = (intent.get("parameters") or {}).get("goal") or text
            reply = await self._run_plan(goal, source)
            await self.say(reply)
            db.log_command(source, text, "run_plan", success=not reply.lower().startswith(("i ", "that ")))
            return reply

        if action in DESTRUCTIVE and cfg.CONFIRM_DESTRUCTIVE:
            self.pending = {
                "intent": intent,
                "expires": time.time() + cfg.CONFIRM_TTL_SECONDS,
            }
            prompt = self._confirmation_prompt(action)
            await self.say(prompt)
            return prompt

        reply = await self._run_action(action, intent.get("parameters") or {}, source)
        await self.say(reply)
        db.log_command(source, text, action, success=not reply.lower().startswith(("i could not", "i cannot")))
        return reply

    def _confirmation_prompt(self, action: str) -> str:
        prompts = {
            "shutdown": "This will shut down the computer. Say confirm to proceed.",
            "restart": "This will restart the computer. Say confirm to proceed.",
            "delete_file": "This will send the file to the Recycle Bin. Say confirm to proceed.",
            "empty_recycle_bin": "This will permanently empty the Recycle Bin. Say confirm to proceed.",
            "sleep_mode": "This will put the computer to sleep. Say confirm to proceed.",
            "hibernate": "This will hibernate the computer. Say confirm to proceed.",
            "apply_updates": "This will upgrade installed packages. Say confirm to proceed.",
        }
        return prompts.get(action, "That action is destructive. Say confirm to proceed.")

    async def _control(self, action: str, params: dict) -> str:
        if action == "set_mode":
            mode = str(params.get("mode") or params.get("name") or "").lower().strip()
            if mode not in cfg.MODES:
                return f"I do not have a {mode or 'blank'} mode, Sir."
            self.mode = mode
            brain.set_mode(mode)
            entry = cfg.MODES[mode]
            await self._emit({"type": "mode", "mode": mode,
                              "label": entry["label"], "hint": entry["hint"]})
            return f"{entry['label']} mode engaged."

        if action == "privacy_on":
            security.set_privacy(True)
            self.voice.stop()
            await self._emit({"type": "privacy", "on": True})
            await self._emit({"type": "toast", "message": "Privacy mode: microphone and camera off."})
            return (
                "Privacy mode on. I have stopped listening and will not use the camera "
                "or screen until you switch it off."
            )

        if action == "privacy_off":
            security.set_privacy(False)
            if not self.voice.running:
                self.voice.start(self._voice_callback, self._voice_state)
            await self._emit({"type": "privacy", "on": False})
            return "Privacy mode off. Listening again, Sir."

        if action == "emergency_stop":
            security.halt()
            if self.pending:
                self.pending = None
            await self._emit({"type": "halt", "active": True})
            await self._emit({"type": "toast", "message": "Emergency stop engaged."})
            return "Emergency stop engaged. I will not execute anything until you say resume."

        if action == "resume":
            security.resume()
            await self._emit({"type": "halt", "active": False})
            return "Resumed. At your service, Sir."

        return "That control is not recognised, Sir."

    async def _run_plan(self, goal: str, source: str, confirmed: bool = False) -> str:
        goal = (goal or "").strip()
        await self._emit({"type": "agent", "state": "THINKING"})
        try:
            steps, note = await asyncio.wait_for(
                asyncio.to_thread(planner.make_plan, goal, self.history), timeout=35
            )
        except asyncio.TimeoutError:
            return "Planning took too long, Sir. Ask me again in a moment."
        if not steps:
            await self._emit({"type": "plan", "status": "failed", "goal": goal, "steps": []})
            return note

        if not confirmed and cfg.CONFIRM_DESTRUCTIVE and planner.needs_confirmation(steps):
            self.pending = {
                "intent": {"action": "run_plan", "parameters": {"goal": goal}},
                "expires": time.time() + cfg.CONFIRM_TTL_SECONDS,
            }
            prompt = (
                f"This plan will {planner.describe(steps)}, including an external message. "
                "Say confirm to proceed."
            )
            await self._emit({"type": "plan", "status": "pending", "goal": goal, "steps": steps})
            return prompt

        run = planner.PlanRun(goal, steps)
        await self._emit({"type": "plan", "status": "running", "id": run.id,
                          "goal": goal, "steps": run.steps})
        last = ""
        failed = False
        for index, step in enumerate(run.steps):
            if security.halted():
                run.mark(index, "skipped")
                run.finish("stopped")
                await self._emit({"type": "plan", "status": "stopped", "id": run.id,
                                  "goal": goal, "steps": run.steps})
                return "Stopped on your emergency order, Sir."
            await self._emit({"type": "plan", "status": "step", "id": run.id,
                              "goal": goal, "index": index, "steps": run.steps})
            result = await self._run_action(step["action"], step["parameters"], source)
            last = str(result)
            ok = not last.lower().startswith(("i could not", "i cannot", "that action"))
            run.mark(index, "done" if ok else "failed", last)
            await self._emit({"type": "plan", "status": "running", "id": run.id,
                              "goal": goal, "index": index, "steps": run.steps})
            if not ok:
                failed = True
                break

        status = "failed" if failed else "done"
        run.finish(status)
        await self._emit({"type": "plan", "status": status, "id": run.id,
                          "goal": goal, "steps": run.steps})
        done = sum(1 for step in run.steps if step["status"] == "done")
        if failed:
            return f"The plan stopped after {done} of {len(run.steps)} steps, Sir. {last}"
        return f"Plan complete, Sir. {done} steps done. {last}"

    # --------------------------------------------------------------- execute
    async def _run_action(self, action: str, params: dict, source: str) -> str:
        await self._emit({"type": "agent", "state": "WORKING", "action": action})
        started = time.time()
        timeout = 75 if action in SLOW_ACTIONS else 30
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.execute, action, params), timeout=timeout
            )
            ok = not str(result).lower().startswith(("i could not", "i cannot", "that action"))
        except asyncio.TimeoutError:
            result = "That took too long, Sir. I have stopped waiting."
            ok = False
        except Exception as exc:
            log.exception("action %s failed", action)
            result = f"I hit an error doing that, Sir. {exc}"
            ok = False
        elapsed = round(time.time() - started, 1)
        await self._emit({
            "type": "action", "action": action, "ok": ok,
            "message": result, "seconds": elapsed,
        })
        return str(result)

    def execute(self, action: str, p: dict) -> str:
        """Synchronous tool dispatch (runs in a worker thread)."""
        p = p or {}

        def get(*names: str, default: str = "") -> str:
            for name in names:
                value = p.get(name)
                if value not in (None, ""):
                    return str(value)
            return default

        def num(*names: str, default: int = 0) -> int:
            raw = get(*names)
            try:
                return int(float(re.sub(r"[^0-9.\-]", "", raw) or default))
            except ValueError:
                return default

        # ---- system
        if action == "open_app":
            return system_control.open_app(get("name", "app"))
        if action == "close_app":
            return system_control.close_app(get("name", "app"))
        if action == "switch_app":
            return system_control.switch_app(get("name", "app"))
        if action == "list_open_apps":
            return system_control.list_open_apps()
        if action == "minimize_all":
            return system_control.minimize_all()
        if action == "lock_screen":
            return system_control.lock_screen()
        if action == "shutdown":
            return system_control.shutdown(num("timer", "seconds", default=10))
        if action == "restart":
            return system_control.restart(num("timer", "seconds", default=10))
        if action == "cancel_shutdown":
            return system_control.cancel_shutdown()
        if action == "sleep_mode":
            return system_control.sleep_mode()
        if action == "hibernate":
            return system_control.hibernate()
        if action == "empty_recycle_bin":
            return system_control.empty_recycle_bin()
        if action == "set_volume":
            return system_control.set_volume(num("level", "volume", default=50))
        if action == "volume_up":
            return system_control.volume_up(num("step", default=10))
        if action == "volume_down":
            return system_control.volume_down(num("step", default=10))
        if action == "mute_volume":
            return system_control.mute_volume()
        if action == "unmute_volume":
            return system_control.unmute_volume()
        if action == "set_brightness":
            return system_control.set_brightness(num("level", "brightness", default=50))
        if action == "get_battery_status":
            return system_control.get_battery_status()
        if action == "get_cpu_ram_usage":
            return system_control.get_cpu_ram_usage()
        if action == "get_system_info":
            return system_control.get_system_info()
        if action == "get_ip_address":
            return system_control.get_ip_address()
        if action == "get_wifi_name":
            return system_control.get_wifi_name()
        if action == "open_network_settings":
            return system_control.open_network_settings()
        if action == "open_settings":
            return system_control.open_settings()
        if action == "task_manager":
            return system_control.task_manager()
        if action == "open_control_panel":
            return system_control.open_control_panel()
        if action == "open_device_manager":
            return system_control.open_device_manager()
        if action == "screenshot":
            return system_control.screenshot()
        if action == "type_text":
            return system_control.type_text(get("text", "value"))
        if action == "press_key":
            return system_control.press_key(get("key", "value"))
        if action == "hotkey":
            keys = p.get("keys") or get("keys")
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split("+")]
            return system_control.hotkey(*(keys or []))
        if action == "click":
            return system_control.click(num("x"), num("y"))
        if action == "scroll":
            return system_control.scroll(get("direction", default="down"), num("amount", default=500))
        if action == "copy_to_clipboard":
            return system_control.copy_to_clipboard(get("text", "value"))
        if action == "get_clipboard":
            return system_control.get_clipboard()

        # ---- media / web
        if action == "play_pause_media":
            return system_control.play_pause_media()
        if action == "next_track":
            return system_control.next_track()
        if action == "previous_track":
            return system_control.previous_track()
        if action == "stop_media":
            return system_control.stop_media()
        if action == "open_website":
            return browser.open_website(get("url", "website", "name"))
        if action == "search_google":
            return browser.search_google(get("query"))
        if action == "search_youtube":
            return browser.search_youtube(get("query"))
        if action == "play_youtube":
            return browser.play_youtube(get("query", "song", "text"))

        # ---- files
        if action == "create_folder":
            return files.create_folder(get("name", "folder"), get("location", default="Desktop"))
        if action == "create_file":
            return files.create_file(get("name", "file"), get("location", default="Desktop"),
                                      get("content"))
        if action == "write_file":
            return files.write_file(get("path", "name"), get("content", "text"))
        if action == "read_file":
            return files.read_file(get("path", "name"))
        if action == "list_files":
            return files.list_files(get("directory", "location", default="Desktop"))
        if action == "search_file":
            return files.search_file(get("name", "query"), get("location") or None)
        if action == "open_file":
            return files.open_file(get("name", "path"))
        if action == "move_file":
            return files.move_file(get("src", "source"), get("dest", "destination"))
        if action == "rename_file":
            return files.rename_file(get("old", "src"), get("new", "name"))
        if action == "delete_file":
            return files.delete_file(get("path", "name"))
        if action == "organize_folder":
            return files.organize_folder(get("directory", "folder", default="Downloads"))
        if action == "disk_usage":
            return files.disk_usage()
        if action == "find_by_content":
            return files.find_by_content(get("text", "query"), get("location") or None)

        # ---- communication
        if action == "send_whatsapp":
            contact = get("contact", "name", "to")
            phone_number = get("phone", "number")
            if not phone_number:
                saved = db.find_contact(contact, "whatsapp")
                if saved:
                    phone_number = saved.get("phone") or ""
            return browser.send_whatsapp(contact, get("message", "text", "body"), phone_number or None)
        if action == "send_instagram":
            return browser.send_instagram(get("contact", "name", "to"),
                                          get("message", "text", "body"))
        if action == "open_whatsapp":
            return browser.open_whatsapp(get("contact", "name"))
        if action == "send_email":
            return email_skill.send_email(
                get("to", "contact", "recipient"),
                get("subject"),
                get("body", "message", "text"),
                account=get("account", "from", "sender"),
            )
        if action == "read_emails":
            return email_skill.read_emails(
                num("limit", default=5),
                account=get("account", "from", "sender"),
            )
        if action == "email_accounts":
            return email_skill.accounts_summary()
        if action == "sync_email_contacts":
            return email_skill.sync_contacts(account=get("account", "from"))
        if action == "test_email":
            return email_skill.test_account(get("account", "label"))
        if action in {"call_contact", "call"}:
            return phone.call_contact(get("contact", "name", "to"))
        if action in {"hang_up_call", "end_call", "hang_up"}:
            return phone.end_call()
        if action == "mute_call":
            return phone.mute_call()
        if action == "unmute_call":
            return phone.unmute_call()
        if action == "call_volume":
            return phone.call_volume(num("level", default=50))
        if action == "phone_diagnose":
            return phone.diagnose()
        if action == "phone_status":
            status = phone.status()
            return "Phone Link is open." if status.get("open") else "Phone Link is not open, Sir."

        # ---- information
        if action == "get_time":
            return info.get_time()
        if action == "get_date":
            return info.get_date()
        if action == "get_weather":
            return info.get_weather(get("city", "location"))
        if action == "get_news":
            return news.get_news(get("category") or None, num("count", default=5))
        if action == "news_briefing":
            return news.briefing(get("category") or None, num("count", default=6))
        if action == "web_search":
            return info.web_search(get("query"))
        if action == "wikipedia_search":
            return info.wikipedia_search(get("topic", "query"))
        if action == "calculate":
            return info.calculate(get("expression", "query"))

        # ---- tasks / calendar
        if action == "add_task":
            return tasks_skill.add(
                get("title", "text", "task"),
                get("when", "due", "due_at"),
                num("priority", default=tasks_skill.parse_priority(get("title", "text"))),
            )
        if action == "list_tasks":
            return tasks_skill.list_text(include_done=bool(p.get("include_done")))
        if action == "complete_task":
            return tasks_skill.complete(get("match", "title", "task", "text"))
        if action == "next_task":
            return tasks_skill.next_task_text()
        if action == "add_event":
            return tasks_skill.add_event(
                get("title", "text", "event"),
                get("when", "time", "due_at"),
                get("location", "where"),
                get("notes"),
            )
        if action == "agenda_summary":
            return tasks_skill.agenda_text(get("day") or None)

        # ---- vision / hardware
        if action == "analyze_screen":
            return vision.analyze_screen(get("question", "query"))
        if action == "read_screen_text":
            return vision.read_screen_text()
        if action == "camera_look":
            return vision.camera_look(get("question", "query"))
        if action == "gpu_stats":
            return hardware.gpu_stats()
        if action == "temperatures":
            return hardware.temperatures()
        if action == "diagnose_slowdown":
            return hardware.diagnose_slowdown()

        # ---- home assistant
        if action == "home_status":
            return home.status()
        if action == "home_turn":
            return home.turn(get("entity", "name", "device"), get("state", default="on"))
        if action == "home_light":
            brightness = num("brightness", "level", default=0) or None
            return home.light(get("name", "entity"), get("state", default="on"), brightness)
        if action == "home_climate":
            temperature = get("temperature", "level")
            return home.climate(get("name", "entity", default="thermostat"),
                                float(temperature) if temperature else None)
        if action == "home_scene":
            return home.scene(get("name", "scene"))

        # ---- research
        if action == "deep_research":
            return research.deep_research(get("topic", "query", "text"),
                                          num("depth", default=3))
        if action == "quick_research":
            return research.quick_brief(get("topic", "query", "text"))

        # ---- money
        if action == "add_expense":
            return finance.add_expense(get("amount"), get("category", default="general"),
                                       get("note"))
        if action == "add_income":
            return finance.add_income(get("amount"), get("note"))
        if action == "set_budget":
            return finance.set_budget(get("category"), get("amount"))
        if action == "budget_status":
            return finance.budget_status()
        if action == "budget_advice":
            return finance.budget_advice(get("question", "text", "query"))
        if action == "recent_transactions":
            return finance.recent_transactions()

        # ---- memory / reminders
        if action == "remember":
            db.remember(get("text", "value", "query"))
            return "Noted, Sir."
        if action == "recall":
            items = db.recall(get("query") or None)
            if not items:
                return "I have not stored anything about that, Sir."
            return "I remember: " + "; ".join(item["text"] for item in items[:6]) + "."
        if action == "add_reminder":
            due = get("when", "time", "due_at") or None
            db.add_reminder(get("text", "reminder"), tasks_skill.parse_when(due))
            return f"Reminder set{' for ' + due if due else ''}, Sir."
        if action == "list_reminders":
            items = db.list_reminders()
            if not items:
                return "You have no reminders, Sir."
            return "Reminders: " + "; ".join(
                f"{r['text']} ({r['due_at'] or 'no time'})" for r in items[:8]
            ) + "."

        # ---- maintenance
        if action == "check_updates":
            return updater.check_updates()
        if action == "apply_updates":
            return updater.apply_updates()
        if action == "system_health":
            return updater.health_summary()
        if action == "enroll_voice":
            ok, score, mode = self.voice.enroll()
            return f"Voice profile saved with confidence {score}." if ok else "Voice enrollment failed."
        if action == "test_voice":
            ok, score = self.voice.test_voice()
            return f"Voice matched at {score}." if ok else f"Voice did not match ({score})."
        if action == "browser_login_status":
            status = browser.login_status()
            return f"WhatsApp state: {status.get('whatsapp')}. Instagram: {status.get('instagram')}."

        # ---- plugins
        if action in self._plugins:
            try:
                return str(self._plugins[action](p))
            except Exception as exc:
                return f"The {action} plugin failed, Sir. {exc}"

        return self._converse_sync(get("query") or get("text") or "")

    def _converse_sync(self, text: str) -> str:
        if not text:
            return "I am not sure what you would like me to do, Sir."
        answer = brain.chat(text, self.history)
        return answer or "My language model is offline, Sir."

    # ------------------------------------------------------------------ chat
    async def _converse(self, text: str) -> str:
        await self._emit({"type": "agent", "state": "THINKING"})
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def worker() -> None:
            try:
                for token in brain.stream_chat(text, self.history):
                    loop.call_soon_threadsafe(queue.put_nowait, token)
            except Exception as exc:
                log.warning("stream failed: %s", exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()
        buffer = ""
        spoken_upto = 0
        chunks: list[str] = []

        while True:
            token = await queue.get()
            if token is None:
                break
            buffer += token
            chunks.append(token)
            await self._emit({"type": "partial", "text": buffer})
            # speak completed sentences early
            match = re.search(r"[.!?]\s", buffer[spoken_upto:])
            if match:
                cut = spoken_upto + match.end()
                sentence = buffer[spoken_upto:cut].strip()
                spoken_upto = cut
                if sentence:
                    asyncio.create_task(asyncio.to_thread(self.voice.speaker.speak, sentence))

        reply = buffer.strip()
        if not reply:
            reply = (
                "My local brain is not responding, Sir. Start Ollama with 'ollama serve' "
                "and I will be back to full strength."
            )
            await self.say(reply)
            return reply

        tail = reply[spoken_upto:].strip()
        if tail:
            await asyncio.to_thread(self.voice.speaker.speak, tail)
        await self._emit({"type": "transcript", "speaker": "jarvis", "message": reply})
        return reply

    # ------------------------------------------------------------- fast path
    def _fast_intent(self, text: str) -> Optional[dict]:
        t = text.lower().strip(" .!?")
        original = text.strip(" .!?")

        def intent(action: str, **params) -> dict:
            return {"action": action, "parameters": params, "confidence": 0.96, "speech": ""}

        # --- power / system
        if re.fullmatch(r"(shut ?down|power off|turn off (the )?(pc|laptop|computer)|switch off)", t):
            return intent("shutdown", timer=10)
        m = re.fullmatch(r"(shut ?down|power off|reboot|restart)( (the )?(pc|laptop|computer))? in (\d+) (seconds?|minutes?|hours?)", t)
        if m:
            value = int(m.group(5))
            unit = m.group(6)
            timer = value * (3600 if unit.startswith("hour") else 60 if unit.startswith("min") else 1)
            return intent("restart" if m.group(1) in {"reboot", "restart"} else "shutdown", timer=timer)
        if re.fullmatch(r"(restart|reboot)( (the )?(pc|laptop|computer))?( now)?", t):
            return intent("restart", timer=10)
        if re.fullmatch(r"(cancel|abort|stop) (the )?(shutdown|restart)", t):
            return intent("cancel_shutdown")
        if re.fullmatch(r"(lock|lock screen|lock the screen|lock (the )?(pc|laptop|computer))", t):
            return intent("lock_screen")
        if re.fullmatch(r"(sleep|go to sleep|suspend)( (the )?(pc|laptop|computer))?", t):
            return intent("sleep_mode")
        if re.fullmatch(r"hibernate", t):
            return intent("hibernate")
        if re.fullmatch(r"(take (a )?screenshot|screenshot|screen shot)", t):
            return intent("screenshot")
        if re.fullmatch(r"(empty|clear) (the )?(recycle bin|trash)", t):
            return intent("empty_recycle_bin")
        if re.fullmatch(r"(minimi[sz]e|minimize) (all|everything|the windows)", t):
            return intent("minimize_all")
        if re.fullmatch(r"(system health|run diagnostics|health check|diagnostics)", t):
            return intent("system_health")
        if re.fullmatch(r"(check for updates|update yourself|any updates)", t):
            return intent("check_updates")
        if re.fullmatch(r"(phone diagnostic|diagnose phone|inspect phone link)", t):
            return intent("phone_diagnose")
        if re.fullmatch(r"(enroll|register|learn|save) (my )?voice( print)?", t):
            return intent("enroll_voice")
        if re.fullmatch(r"(test|verify|check) (my )?voice", t):
            return intent("test_voice")

        # --- volume / brightness
        m = re.fullmatch(r"(?:set )?(?:the )?volume (?:to )?(\d{1,3})(?: percent)?", t)
        if m:
            return intent("set_volume", level=int(m.group(1)))
        if re.fullmatch(r"(volume up|turn (it|the volume) up|louder|increase (the )?volume)", t):
            return intent("volume_up", step=10)
        if re.fullmatch(r"(volume down|turn (it|the volume) down|quieter|decrease (the )?volume)", t):
            return intent("volume_down", step=10)
        if re.fullmatch(r"(mute|mute (the )?(sound|audio|volume))", t):
            return intent("mute_volume")
        if re.fullmatch(r"(unmute|unmute (the )?(sound|audio|volume)|restore sound)", t):
            return intent("unmute_volume")
        m = re.fullmatch(r"(?:set )?(?:the )?brightness (?:to )?(\d{1,3})(?: percent)?", t)
        if m:
            return intent("set_brightness", level=int(m.group(1)))

        # --- information
        if re.fullmatch(r"(what('s| is) the time|what time is it|the time|time now)", t):
            return intent("get_time")
        if re.fullmatch(r"(what('s| is) the date|what day is it|today('s)? date)", t):
            return intent("get_date")
        m = re.fullmatch(r"brief me on\s+(.+)", t)
        if m:
            return intent("quick_research", topic=m.group(1))
        m = re.fullmatch(r"(?:what('s| is) )?(?:the )?weather(?: like)?(?: in| for| at)?\s*(.*)", t)
        if m:
            return intent("get_weather", city=m.group(2).strip())
        m = re.fullmatch(r"(world|india|technology|business|science|sports|health|ai|crypto|local) news", t)
        if m:
            return intent("get_news", category=m.group(1), count=6)
        m = re.fullmatch(r"(news|headlines|what's happening|whats happening|brief me|briefing|world news)(?: (?:about|on) (.*))?", t)
        if m:
            category = (m.group(2) or "").strip()
            return intent("news_briefing" if "brief" in t or "happening" in t else "get_news",
                          category=category, count=6)
        if "battery" in t and re.fullmatch(r"(battery|battery status|how much battery.*)", t):
            return intent("get_battery_status")
        if re.fullmatch(r"(cpu|ram|memory|cpu and ram|system load|performance)", t):
            return intent("get_cpu_ram_usage")
        if re.fullmatch(r"(system info|system information|pc specs|specs)", t):
            return intent("get_system_info")
        if re.fullmatch(r"(get )?(my )?(ip address|ip|network address)", t):
            return intent("get_ip_address")
        if re.fullmatch(r"(get )?(my )?(wifi|wi-fi)( name)?", t):
            return intent("get_wifi_name")
        m = re.fullmatch(r"(?:what(?:'s| is) )?(\d+(?:\.\d+)?)\s*(?:percent|%)\s*of\s*(\d+(?:\.\d+)?)", t)
        if m:
            return intent("calculate", expression=f"{m.group(1)}/100*{m.group(2)}")
        m = re.fullmatch(r"(calculate|what is|what's)\s+([0-9][0-9+\-*/().,%^ ]*)", t)
        if m:
            return intent("calculate", expression=m.group(2))
        m = re.fullmatch(r"(?:search (?:google|the web|the internet)(?: for)?|google)\s+(.+)", t)
        if m:
            return intent("search_google", query=m.group(1))
        m = re.fullmatch(r"(?:search youtube(?: for)?|youtube)\s+(.+)", t)
        if m:
            return intent("search_youtube", query=m.group(1))
        m = re.fullmatch(r"wikipedia\s+(.+)", t)
        if m:
            return intent("wikipedia_search", topic=m.group(1))

        # --- autonomous plans
        m = re.fullmatch(r"(?:make|create|build) (?:me )?(?:a )?plan(?: to| for)?\s+(.+)", t)
        if m:
            return intent("run_plan", goal=m.group(1))
        if (
            re.search(r"prepare (?:my )?(?:laptop|workstation|computer|pc|desk)", t)
            or re.fullmatch(r"(?:start|begin|run) (?:my )?(?:day|morning)|morning routine", t)
            or re.fullmatch(r"(?:run )?(?:a )?full (?:diagnostic|checkup)", t)
            or re.fullmatch(r"close (?:everything|all apps|all applications)", t)
            or re.fullmatch(r"organi[sz]e my downloads", t)
        ):
            return intent("run_plan", goal=original)

        # --- agenda / tasks
        if re.fullmatch(r"(?:what(?:'s| is) )?(?:my )?next task|what should i (?:do|work on) next", t):
            return intent("next_task")
        if re.fullmatch(r"(?:list|show|what are|tell me) (?:me )?(?:my )?tasks", t):
            return intent("list_tasks")
        m = re.fullmatch(r"(?:complete|finish|mark|tick off) (?:the )?(?:task )?(.+?)(?: as)? done", t)
        if m:
            return intent("complete_task", match=m.group(1))
        m = re.fullmatch(r"(?:complete|finish) (?:the )?task(?: called| named)?\s+(.+)", t)
        if m:
            return intent("complete_task", match=m.group(1))
        m = re.fullmatch(r"(?:add|create|make|new) (?:a )?task(?: to| called| named)?\s+(.+)", original, re.IGNORECASE)
        if m:
            return intent("add_task", title=m.group(1))
        if re.fullmatch(
            r"(?:what(?:'s| is)|show|tell me) (?:on )?(?:my )?(?:agenda|schedule|calendar)"
            r"(?: (?:today|for today|tomorrow))?"
            r"|what (?:do i have|is) (?:on )?(?:today|my (?:agenda|schedule))"
            r"|today(?:'s)? (?:agenda|schedule)|my (?:agenda|schedule)",
            t,
        ):
            return intent("agenda_summary", day="tomorrow" if "tomorrow" in t else "")
        m = re.fullmatch(r"(?:add|put)\s+(.+?)\s+(?:to|on)\s+my calendar(?:\s+(?:at|on|for)\s+(.+))?", original, re.IGNORECASE)
        if m:
            return intent("add_event", title=m.group(1), when=m.group(2) or "")
        m = re.fullmatch(
            r"(?:add|create|schedule|put) (?:a )?(?:meeting|event|appointment)"
            r"(?: (?:called|titled|about|for|with|to))?\s+(.+)",
            original, re.IGNORECASE,
        )
        if m:
            return intent("add_event", title=m.group(1))

        # --- vision / hardware
        if re.fullmatch(r"(?:read|scan) (?:the )?screen(?: text)?", t):
            return intent("read_screen_text")
        if re.fullmatch(
            r"(?:what(?:'s| is)|describe|look at|analyse|analyze|check) (?:on |at )?my screen"
            r"|what am i looking at|describe (?:the )?screen|screen (?:status|analysis)",
            t,
        ):
            return intent("analyze_screen", question=original)
        if re.fullmatch(
            r"(?:look|check|see) (?:through|with|at) (?:the )?(?:camera|webcam)"
            r"|(?:camera|webcam) (?:look|snapshot|check)"
            r"|what do you see|who is (?:in front of me|there|standing there)",
            t,
        ):
            return intent("camera_look", question=original)
        if re.fullmatch(
            r"(?:why is|why does) (?:my )?(?:laptop|pc|computer|system|everything|it)"
            r"(?: (?:running|working|going|so))? slow"
            r"|(?:diagnose|check) (?:the )?(?:slowdown|performance problem)"
            r"|what is slowing (?:down )?(?:my |the )?(?:laptop|pc|computer|system)",
            t,
        ):
            return intent("diagnose_slowdown")
        if re.fullmatch(r"(?:gpu|graphics card|nvidia)(?: status| usage| load| stats)?", t):
            return intent("gpu_stats")
        if re.fullmatch(r"temperatures?|(?:how hot is (?:my |the )?(?:laptop|pc|computer|gpu|cpu))", t):
            return intent("temperatures")

        # --- modes and safety
        m = re.fullmatch(
            r"(?:enter|switch to|activate|go to|use|enable|set) (?:the )?"
            r"(normal|developer|research|system|vision|security|autonomous) mode", t,
        )
        if m:
            return intent("set_mode", mode=m.group(1))
        if re.fullmatch(r"(?:privacy|private) (?:mode )?on|go private|stop watching|turn off (?:the )?camera", t):
            return intent("privacy_on")
        if re.fullmatch(r"(?:privacy|private) (?:mode )?off|stop privacy|leave privacy mode|turn camera back on", t):
            return intent("privacy_off")
        if re.fullmatch(r"(?:emergency stop|stop everything|abort everything|kill switch|freeze all actions)", t):
            return intent("emergency_stop")
        if re.fullmatch(r"(?:resume|resume operations|stand down|all clear)", t):
            return intent("resume")

        # --- home assistant
        if re.fullmatch(r"(?:home|house|smart home) (?:status|state|report)", t):
            return intent("home_status")
        m = re.fullmatch(
            r"(?:turn|switch) (on|off) (?:the )?((?:[\w'-]+ ){0,3}?)"
            r"(lights?|lamps?|bulbs?|fans?|ac|air conditioner|heater|plug|tv|television)", t,
        )
        if m:
            return intent("home_turn", state=m.group(1), entity=(m.group(2) + m.group(3)).strip())
        m = re.fullmatch(r"set (?:the )?([\w' -]*?)(?:light|lamp|bulb)s? (?:to )?(\d{1,3})(?: percent)?", t)
        if m:
            return intent("home_light", name=(m.group(1) + "light").strip(), state="on",
                          brightness=int(m.group(2)))
        m = re.fullmatch(r"set (?:the )?(thermostat|ac|air conditioner|climate|temperature)(?: to)? (\d{1,2})(?: degrees)?", t)
        if m:
            return intent("home_climate", name=m.group(1), temperature=float(m.group(2)))
        m = re.fullmatch(r"(?:activate|run|start|turn on) (?:the )?(.+?) scene", t)
        if m:
            return intent("home_scene", name=m.group(1))
        m = re.fullmatch(r"scene (\w+)", t)
        if m:
            return intent("home_scene", name=m.group(1))

        # --- research
        m = re.fullmatch(
            r"(?:do )?(?:deep research|deep dive) (?:on|into)?\s*(.+)", t
        )
        if m:
            return intent("deep_research", topic=m.group(1), depth=4)
        m = re.fullmatch(
            r"(?:research|investigate|look into|study) (?:on|into)?\s*(.+?)"
            r"(?: and (?:prepare|write|make) (?:a )?report)?", t,
        )
        if m:
            return intent("deep_research", topic=m.group(1))
        m = re.fullmatch(r"(?:prepare|write|make) (?:a )?(?:research |technical )?report (?:on|about)\s+(.+)", t)
        if m:
            return intent("deep_research", topic=m.group(1), depth=4)

        # --- media
        m = re.fullmatch(r"(?:play|put on|start playing)\s+(.+?)(?:\s+(?:on|from) youtube)?", t)
        if m and not t.startswith("play pause"):
            return intent("play_youtube", query=m.group(1).replace(" on youtube", "").strip())
        if re.fullmatch(r"(play|resume|pause|toggle) (the )?(music|song|video|playback)", t) or t in {"pause", "resume"}:
            return intent("play_pause_media")
        if re.fullmatch(r"(next|skip) (song|track)", t):
            return intent("next_track")
        if re.fullmatch(r"(previous|last|go back a) (song|track)", t):
            return intent("previous_track")
        if re.fullmatch(r"stop (the )?(music|song|playback)", t):
            return intent("stop_media")

        # --- apps
        m = re.fullmatch(r"open (?:my |the )?(desktop|downloads|documents|pictures|music|videos) folder", t)
        if m:
            return intent("list_files", directory=m.group(1))
        m = re.fullmatch(r"open (?:the )?(?:file|document)\s+(.+)", t)
        if m:
            return intent("open_file", name=m.group(1))
        m = re.fullmatch(r"open (?:the )?folder\s+(.+)", t)
        if m:
            return intent("list_files", directory=m.group(1))
        m = re.fullmatch(r"(?:open|launch|start|run)\s+(?:the\s+)?(.+?)(?:\s+app)?", t)
        if m:
            target = m.group(1).strip()
            if target in {"youtube"}:
                return intent("open_website", url="https://www.youtube.com")
            if target in {"whatsapp", "whatsapp web"}:
                return intent("open_whatsapp", contact="")
            return intent("open_app", name=target)
        m = re.fullmatch(r"(?:close|quit|kill|exit)\s+(?:the\s+)?(.+?)(?:\s+app)?", t)
        if m:
            return intent("close_app", name=m.group(1))
        m = re.fullmatch(r"(?:switch|focus|go) to\s+(?:the\s+)?(.+?)(?:\s+window)?", t)
        if m:
            return intent("switch_app", name=m.group(1))
        if re.fullmatch(r"(open|show) (task manager)", t):
            return intent("task_manager")
        if re.fullmatch(r"(open|show) (settings|windows settings)", t):
            return intent("open_settings")
        if re.fullmatch(r"(open|show) (control panel)", t):
            return intent("open_control_panel")
        if re.fullmatch(r"(open|show) (device manager)", t):
            return intent("open_device_manager")

        # --- files
        m = re.fullmatch(r"(?:create|make) (?:a |new )?folder(?: called| named)?\s+(.+?)(?:\s+(?:on|in) (?:the )?(desktop|downloads|documents|pictures))?$", t)
        if m:
            return intent("create_folder", name=m.group(1), location=m.group(2) or "Desktop")
        m = re.fullmatch(r"(?:create|make) (?:a |new )?file(?: called| named)?\s+(.+?)(?:\s+(?:on|in) (?:the )?(desktop|downloads|documents|pictures))?$", t)
        if m:
            return intent("create_file", name=m.group(1), location=m.group(2) or "Desktop")
        m = re.fullmatch(r"(?:list|show)(?: me)? (?:the )?(?:files|contents)(?: in| on)?\s*(.*)", t)
        if m:
            return intent("list_files", directory=m.group(1).strip() or "Desktop")
        m = re.fullmatch(r"(?:find|search for|locate)(?: the| a)?(?: file| folder)?(?: called| named)?\s+(.+?)(?:\s+(?:in|on) (desktop|downloads|documents|pictures))?$", t)
        if m:
            return intent("search_file", name=m.group(1), location=m.group(2) or "")
        m = re.fullmatch(r"where is(?: the)?(?: file| folder)?\s+(.+)", t)
        if m:
            return intent("search_file", name=m.group(1))
        m = re.fullmatch(r"(?:open|show)(?: the)? file\s+(.+)", t)
        if m:
            return intent("open_file", name=m.group(1))
        m = re.fullmatch(r"move\s+(.+?)\s+to\s+(.+)", t)
        if m:
            return intent("move_file", src=m.group(1), dest=m.group(2))
        m = re.fullmatch(r"rename\s+(.+?)\s+to\s+(.+)", t)
        if m:
            return intent("rename_file", old=m.group(1), new=m.group(2))
        m = re.fullmatch(r"delete(?: the)?(?: file| folder)?\s+(.+)", t)
        if m:
            return intent("delete_file", path=m.group(1))
        m = re.fullmatch(r"(?:organi[sz]e|clean up|tidy)(?: my)?\s+(downloads|desktop|documents|pictures)", t)
        if m:
            return intent("organize_folder", directory=m.group(1))
        if re.fullmatch(r"(disk space|how much (?:disk )?space.*)", t):
            return intent("disk_usage")

        # --- communication
        m = re.fullmatch(
            r"(?:send|write)(?: a)?(?: whatsapp)? message to (.+?) on whatsapp(?: saying| that says|:)?\s*(.*)",
            original, re.IGNORECASE,
        )
        if m:
            return intent("send_whatsapp", contact=m.group(1), message=m.group(2))
        m = re.fullmatch(
            r"(?:send|write)(?: a)? whatsapp(?: message)? to (.+?)(?: saying| that says|:)\s*(.*)",
            original, re.IGNORECASE,
        )
        if m:
            return intent("send_whatsapp", contact=m.group(1), message=m.group(2))
        m = re.fullmatch(r"whatsapp (.+?) (?:saying|that)\s+(.+)", original, re.IGNORECASE)
        if m:
            return intent("send_whatsapp", contact=m.group(1), message=m.group(2))
        m = re.fullmatch(
            r"(?:send|write)(?: a)?(?: instagram)? message to (.+?) on instagram(?: saying| that says|:)?\s*(.*)",
            original, re.IGNORECASE,
        )
        if m:
            return intent("send_instagram", contact=m.group(1), message=m.group(2))
        m = re.fullmatch(r"(?:dm|message) (.+?) on instagram(?: saying|:)?\s*(.*)", original, re.IGNORECASE)
        if m:
            return intent("send_instagram", contact=m.group(1), message=m.group(2))
        m = re.fullmatch(
            r"send(?: an)? email (?:from|using|with) (?:my )?(.+?)(?: account)? to (.+?)"
            r"(?: about| saying| that says|,)\s+(.+)$",
            original, re.IGNORECASE,
        )
        if m:
            account = m.group(1).strip()
            return intent("send_email",
                          account=account if email_skill.resolve_account(account) else None,
                          to=m.group(2).strip(), subject=m.group(3)[:70], body=m.group(3))
        m = re.fullmatch(
            r"send(?: an)? email to (.+?)(?: with subject| subject)\s+(.+?)(?: (?:saying|body|and say)\s+(.*))?$",
            original, re.IGNORECASE,
        )
        if m:
            return intent("send_email", to=m.group(1), subject=m.group(2), body=m.group(3) or "")
        m = re.fullmatch(
            r"send(?: an)? email to (.+?)(?: about| saying| that says|,)?\s+(.+)$",
            original, re.IGNORECASE,
        )
        if m:
            return intent("send_email", to=m.group(1), subject=m.group(2)[:70], body=m.group(2))
        m = re.fullmatch(
            r"(?:read|check|open) (?:my )?([a-z0-9 _-]+?) (?:email|emails|inbox|mail)", t
        )
        if m and email_skill.resolve_account(m.group(1).strip()) is not None:
            return intent("read_emails", limit=5, account=m.group(1).strip())
        if re.fullmatch(r"(?:which|what|list)(?: are)? (?:my )?(?:email|mail) accounts"
                        r"|(?:email|mail) accounts", t):
            return intent("email_accounts")
        if re.fullmatch(r"(?:sync|import|learn) (?:my )?(?:email|mail) contacts", t):
            return intent("sync_email_contacts")
        m = re.fullmatch(r"(?:call|phone|dial)(?:\s+to)?\s+(.+)", original, re.IGNORECASE)
        if m and " on whatsapp" not in t and " on instagram" not in t:
            return intent("call_contact", contact=m.group(1).strip())
        if re.fullmatch(r"(hang up|end (the )?call|disconnect)", t):
            return intent("hang_up_call")
        if re.fullmatch(r"(mute (the )?call|mute (the )?microphone)", t):
            return intent("mute_call")
        if re.fullmatch(r"(unmute (the )?call|unmute (the )?microphone)", t):
            return intent("unmute_call")
        m = re.fullmatch(r"(?:set )?call volume (?:to )?(\d{1,3})", t)
        if m:
            return intent("call_volume", level=int(m.group(1)))
        if re.fullmatch(r"(read|check) (my )?(emails|inbox|mail)", t):
            return intent("read_emails", limit=5)

        # --- money
        m = re.fullmatch(r"(?:i )?spent\s+([0-9][0-9,\.]*k?)\s+(?:on|for)\s+(.+)", t)
        if m:
            return intent("add_expense", amount=m.group(1), category=m.group(2))
        m = re.fullmatch(r"add(?: an)? expense(?: of)?\s+([0-9][0-9,\.]*k?)(?:\s+(?:on|for)\s+(.+))?", t)
        if m:
            return intent("add_expense", amount=m.group(1), category=m.group(2) or "general")
        m = re.fullmatch(r"add(?: an)? income(?: of)?\s+([0-9][0-9,\.]*k?)(?:\s+(.+))?", t)
        if m:
            return intent("add_income", amount=m.group(1), note=m.group(2) or "")
        m = re.fullmatch(r"set(?: a)? budget(?: for| on)?\s+(.+?)\s+(?:to|at)\s+([0-9][0-9,\.]*k?)", t)
        if m:
            return intent("set_budget", category=m.group(1), amount=m.group(2))
        m = re.fullmatch(r"set(?: a)? budget(?: of| for)?\s+([0-9][0-9,\.]*k?)\s+(?:for|on)\s+(.+)", t)
        if m:
            return intent("set_budget", category=m.group(2), amount=m.group(1))
        if re.fullmatch(r"(budget status|how(?:'s| is| much is) my budget|how much (?:have i|did i) spen[dt].*|my budget|budget)", t):
            return intent("budget_status")
        m = re.fullmatch(r"(?:give me|make me|create|plan) a budget(?: for| of| with)?\s*(.*)", t)
        if m:
            return intent("budget_advice", question=f"Build a budget. {m.group(1)}".strip())

        # --- memory
        m = re.fullmatch(r"remember (?:that )?(.+)", original, re.IGNORECASE)
        if m:
            return intent("remember", text=m.group(1))
        if re.fullmatch(r"what do you remember(?: about (.+))?", t):
            return intent("recall", query="")
        m = re.fullmatch(r"remind me to (.+?)(?: at| by| in) (.+)", original, re.IGNORECASE)
        if m:
            return intent("add_reminder", text=m.group(1), when=m.group(2))
        if re.fullmatch(r"(list|show) (my )?reminders", t):
            return intent("list_reminders")

        return None

    # ------------------------------------------------------------- plugins
    @staticmethod
    def _load_plugins() -> dict[str, Callable[[dict], Any]]:
        folder = Path(__file__).resolve().parent / "skills" / "plugins"
        actions: dict[str, Callable[[dict], Any]] = {}
        if not folder.exists():
            return actions
        for path in folder.glob("*.py"):
            if path.name.startswith("_"):
                continue
            try:
                spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{path.stem}", path)
                module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                for name, func in getattr(module, "ACTIONS", {}).items():
                    if callable(func):
                        actions[name] = func
            except Exception as exc:
                log.warning("plugin %s failed: %s", path.name, exc)
        return actions

    # ------------------------------------------------------------ proactive
    async def _reminder_loop(self) -> None:
        while True:
            try:
                for reminder in db.due_reminders():
                    await self.say(f"Reminder, Sir: {reminder['text']}")
                    db.complete_reminder(reminder["id"])
            except Exception as exc:
                log.debug("reminder loop: %s", exc)
            await asyncio.sleep(20)

    async def _news_loop(self) -> None:
        await asyncio.sleep(15)
        while True:
            try:
                now = time.time()
                if now - self._last_news_push > 900:
                    items = await asyncio.wait_for(
                        asyncio.to_thread(news.headlines, "world", 8), timeout=30
                    )
                    await self._emit({"type": "news", "items": items})
                    self._last_news_push = now
            except Exception as exc:
                log.debug("news loop: %s", exc)
            await asyncio.sleep(120)

    async def _update_loop(self) -> None:
        await asyncio.sleep(30)
        while True:
            try:
                if time.time() - self._last_update_check > 43200:
                    summary = await asyncio.to_thread(updater.check_updates)
                    if "available" in summary.lower():
                        await self._emit({"type": "toast", "message": summary})
                        await self.say(summary)
                    self._last_update_check = time.time()
            except Exception as exc:
                log.debug("update loop: %s", exc)
            await asyncio.sleep(3600)

    # ---------------------------------------------------------------- extras
    async def morning_briefing(self) -> str:
        parts = [info.get_date()]
        try:
            parts.append(await asyncio.wait_for(
                asyncio.to_thread(info.get_weather, cfg.DEFAULT_CITY), timeout=20
            ))
        except Exception:
            pass
        mail = await asyncio.to_thread(email_skill.email_summary, 5)
        if mail:
            parts.append("Your inbox: " + mail)
        headlines = await asyncio.wait_for(
            asyncio.to_thread(news.briefing, count=6), timeout=30
        )
        parts.append(headlines)
        try:
            parts.append(tasks_skill.agenda_text())
        except Exception:
            pass
        summary = "\n".join(parts)
        spoken = await asyncio.to_thread(brain.summarise, summary) or summary
        await self.say(spoken)
        return spoken
