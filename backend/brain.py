"""JARVIS reasoning layer.

Primary provider: local Ollama (fast, private, no key needed).
Fallbacks: Gemini / OpenAI / Claude when a real key is configured.

The brain exposes three things:
  * ``chat``        - conversational reply
  * ``parse_intent``- strict-JSON tool routing
  * ``stream_chat`` - token stream for low-latency speech
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import requests

import config as cfg
import backend.db as db

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool catalogue given to the model. Keep descriptions short: they cost tokens
# on every request and local models degrade with long prompts.
# ---------------------------------------------------------------------------
TOOL_SHEET = """
SYSTEM / APPS
  open_app {name} | close_app {name} | switch_app {name} | list_open_apps
  open_settings | task_manager | open_control_panel | open_device_manager
  lock_screen | sleep_mode | hibernate | shutdown {timer} | restart {timer}
  set_volume {level} | volume_up | volume_down | mute_volume | unmute_volume
  set_brightness {level} | get_battery_status | get_cpu_ram_usage | get_system_info
  screenshot | empty_recycle_bin
  get_ip_address | get_wifi_name | open_network_settings
  type_text {text} | press_key {key} | hotkey {keys:["ctrl","s"]} | click {x,y} | scroll {direction,amount}
  copy_to_clipboard {text} | get_clipboard
WEB / MEDIA
  open_website {url} | search_google {query} | search_youtube {query} | play_youtube {query}
  play_pause_media | next_track | previous_track
FILES
  create_folder {name,location} | create_file {name,location} | list_files {directory}
  search_file {name,location} | open_file {name} | read_file {path} | write_file {path,content}
  move_file {src,dest} | rename_file {old,new} | delete_file {path} | organize_folder {directory}
  disk_usage
COMMUNICATION
  send_whatsapp {contact,message} | send_instagram {contact,message} | open_whatsapp {contact}
  send_email {to,subject,body,account?} | read_emails {limit,account?} | email_accounts
  sync_email_contacts
  call_contact {contact}
  hang_up_call | mute_call | unmute_call | call_volume {level}
INFORMATION
  get_time | get_date | get_weather {city} | get_news {category,count} | news_briefing
  web_search {query} | wikipedia_search {topic} | calculate {expression}
  deep_research {topic, depth?}
PLANNING / AGENDA
  plan {goal} | run_plan {goal}
  add_task {title,when?,priority?} | list_tasks | complete_task {match} | next_task
  add_event {title,when?,location?,notes?} | agenda_summary {day?}
VISION / HARDWARE
  analyze_screen {question?} | read_screen_text | camera_look {question?}
  gpu_stats | temperatures | diagnose_slowdown
HOME
  home_status | home_turn {entity,state} | home_light {name,state,brightness?}
  home_climate {name,temperature} | home_scene {name}
CONTROL
  set_mode {mode: normal|developer|research|system|vision|security|autonomous}
  emergency_stop | privacy_on | privacy_off
MONEY / MEMORY
  add_expense {amount,category,note} | add_income {amount,note} | set_budget {category,amount}
  budget_status | budget_advice {question}
  remember {text} | recall {query} | add_reminder {text,when} | list_reminders
MAINTENANCE
  check_updates | system_health
CONVERSATION
  chat  (use for questions, advice, explanations, small talk)
"""

INTENT_SCHEMA = {
    "action": "one action from the tool sheet, or 'chat'",
    "parameters": "object with only the arguments that action needs",
    "confidence": "0.0-1.0",
    "speech": "short natural sentence to say aloud while performing it",
}


def _now_context() -> str:
    now = datetime.now()
    return (
        f"Date: {now:%A, %d %B %Y}. Time: {now:%H:%M}. "
        f"User: {cfg.USER_TITLE}. Assistant: {cfg.ASSISTANT_NAME}."
    )


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------
class OllamaProvider:
    name = "ollama"

    def __init__(self) -> None:
        self.host = cfg.OLLAMA_HOST
        self.model = cfg.OLLAMA_MODEL

    def available(self) -> bool:
        try:
            requests.get(f"{self.host}/api/tags", timeout=2).raise_for_status()
            return True
        except Exception:
            return False

    def chat(self, system: str, messages: List[Dict[str, str]], *,
             json_mode: bool = False, model: Optional[str] = None,
             max_tokens: int = 600, temperature: Optional[float] = None) -> str:
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "think": False,
            "options": {
                "temperature": cfg.AI_TEMPERATURE if temperature is None else temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"
        r = requests.post(f"{self.host}/api/chat", json=payload, timeout=cfg.OLLAMA_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        return (data.get("message", {}) or {}).get("content", "").strip()

    def stream(self, system: str, messages: List[Dict[str, str]], *,
               model: Optional[str] = None, max_tokens: int = 400) -> Iterable[str]:
        payload = {
            "model": model or self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": True,
            "think": False,
            "options": {"temperature": cfg.AI_TEMPERATURE, "num_predict": max_tokens},
        }
        with requests.post(f"{self.host}/api/chat", json=payload,
                           timeout=cfg.OLLAMA_TIMEOUT, stream=True) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = (chunk.get("message", {}) or {}).get("content", "")
                if piece:
                    yield piece
                if chunk.get("done"):
                    break


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self.key = cfg.GEMINI_API_KEY
        self.model = cfg.GEMINI_MODEL

    def available(self) -> bool:
        return bool(self.key) and len(self.key) > 30 and not self.key.lower().startswith("your")

    def chat(self, system: str, messages: List[Dict[str, str]], *,
             json_mode: bool = False, model: Optional[str] = None,
             max_tokens: int = 600, temperature: Optional[float] = None) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model or self.model}:generateContent?key={self.key}"
        )
        contents = [
            {"role": "model" if m["role"] in {"assistant", "model"} else "user",
             "parts": [{"text": m["content"]}]}
            for m in messages
        ]
        body: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {
                "temperature": cfg.AI_TEMPERATURE if temperature is None else temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        r = requests.post(url, json=body, timeout=60)
        r.raise_for_status()
        data = r.json()
        parts = data["candidates"][0]["content"].get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()

    def stream(self, system: str, messages: List[Dict[str, str]], **kw) -> Iterable[str]:
        yield self.chat(system, messages, **kw)


class OpenAIProvider:
    name = "openai"

    def __init__(self) -> None:
        self.key = cfg.OPENAI_API_KEY
        self.model = cfg.OPENAI_MODEL

    def available(self) -> bool:
        return bool(self.key) and len(self.key) > 30 and not self.key.lower().startswith("your")

    def chat(self, system: str, messages: List[Dict[str, str]], *,
             json_mode: bool = False, model: Optional[str] = None,
             max_tokens: int = 600, temperature: Optional[float] = None) -> str:
        body = {
            "model": model or self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": cfg.AI_TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json=body, timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def stream(self, system: str, messages: List[Dict[str, str]], **kw) -> Iterable[str]:
        yield self.chat(system, messages, **kw)


class ClaudeProvider:
    name = "claude"

    def __init__(self) -> None:
        self.key = cfg.CLAUDE_API_KEY
        self.model = cfg.CLAUDE_MODEL

    def available(self) -> bool:
        return bool(self.key) and len(self.key) > 30 and not self.key.lower().startswith("your")

    def chat(self, system: str, messages: List[Dict[str, str]], *,
             json_mode: bool = False, model: Optional[str] = None,
             max_tokens: int = 600, temperature: Optional[float] = None) -> str:
        body = {
            "model": model or self.model,
            "system": system,
            "messages": [
                {"role": "assistant" if m["role"] in {"assistant", "model"} else "user",
                 "content": m["content"]}
                for m in messages
            ],
            "max_tokens": max_tokens,
            "temperature": cfg.AI_TEMPERATURE if temperature is None else temperature,
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body, timeout=60,
        )
        r.raise_for_status()
        return "".join(p.get("text", "") for p in r.json().get("content", [])).strip()

    def stream(self, system: str, messages: List[Dict[str, str]], **kw) -> Iterable[str]:
        yield self.chat(system, messages, **kw)


class Brain:
    def __init__(self) -> None:
        self.providers: List[Any] = []
        preference = cfg.BRAIN_PROVIDER
        candidates = {
            "ollama": OllamaProvider,
            "gemini": GeminiProvider,
            "openai": OpenAIProvider,
            "claude": ClaudeProvider,
        }
        if preference == "auto":
            self.providers = [OllamaProvider(), GeminiProvider(), OpenAIProvider(), ClaudeProvider()]
        elif preference in candidates:
            self.providers = [candidates[preference]()]
            # local first even when a cloud provider was requested but is down
            if preference != "ollama":
                self.providers.append(OllamaProvider())
        else:
            self.providers = [OllamaProvider()]
        self._active: Optional[Any] = None
        self._last_check = 0.0
        self.last_error = ""
        self.mode = cfg.DEFAULT_MODE

    def set_mode(self, mode: str) -> str:
        mode = (mode or "").lower().strip()
        if mode in cfg.MODES:
            self.mode = mode
        return self.mode

    def _mode_prompt(self) -> str:
        entry = cfg.MODES.get(self.mode) or cfg.MODES["normal"]
        return f"\n\nCurrent interface mode: {entry['label']}. {entry['prompt']}"

    # -------------------------------------------------------------- provider
    def _pick(self) -> Any:
        now = time.time()
        if self._active is not None and now - self._last_check < 30:
            return self._active
        for provider in self.providers:
            try:
                if provider.available():
                    self._active = provider
                    self._last_check = now
                    return provider
            except Exception as exc:  # pragma: no cover - defensive
                self.last_error = str(exc)
        self._active = None
        return None

    def status(self) -> dict:
        p = self._pick()
        return {
            "provider": getattr(p, "name", "offline"),
            "model": getattr(p, "model", ""),
            "online": p is not None,
            "error": self.last_error,
        }

    # -------------------------------------------------------------- utilities
    @staticmethod
    def _trim(messages: List[Dict[str, str]], limit: int = 14) -> List[Dict[str, str]]:
        return [{"role": m["role"], "content": m["content"]} for m in messages[-limit:]]

    @staticmethod
    def _extract_json(raw: str) -> Optional[dict]:
        raw = (raw or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            pass
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            try:
                value = json.loads(raw[start:end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def _memory_context(self, query: str) -> str:
        try:
            facts = db.recall(limit=8)
            money = db.money_summary()
            contacts = db.list_contacts()[:20]
        except Exception:
            return ""
        lines: List[str] = []
        if facts:
            lines.append("Known facts: " + "; ".join(f["text"] for f in facts))
        if contacts:
            lines.append("Known contacts: " + ", ".join(f"{c['name']} ({c['platform']})" for c in contacts))
        if money["income"] or money["spent"]:
            lines.append(
                f"This month's money: income {money['income']:.0f}, spent {money['spent']:.0f}, "
                f"balance {money['balance']:.0f}."
            )
        return "\n".join(lines)

    # -------------------------------------------------------------- public API
    def chat(self, text: str, history: List[Dict[str, str]] | None = None,
             json_mode: bool = False, max_tokens: int = 500) -> str:
        provider = self._pick()
        if provider is None:
            return ""
        system = cfg.JARVIS_SYSTEM_PROMPT + "\n\n" + _now_context() + self._mode_prompt()
        context = self._memory_context(text)
        if context:
            system += "\n\n" + context
        messages = self._trim([*(history or []), {"role": "user", "content": text}])
        try:
            return provider.chat(system, messages, json_mode=json_mode, max_tokens=max_tokens)
        except Exception as exc:
            log.warning("%s chat failed: %s", provider.name, exc)
            self.last_error = str(exc)
            self._active = None
            return ""

    def stream_chat(self, text: str, history: List[Dict[str, str]] | None = None,
                    max_tokens: int = 400) -> Iterable[str]:
        provider = self._pick()
        if provider is None:
            yield ""
            return
        system = (cfg.JARVIS_SYSTEM_PROMPT + "\n\n" + _now_context()
                  + self._mode_prompt() + "\n\nKeep the reply short and speakable.")
        messages = self._trim([*(history or []), {"role": "user", "content": text}])
        try:
            yield from provider.stream(system, messages, max_tokens=max_tokens)
        except Exception as exc:
            log.warning("stream failed: %s", exc)
            self.last_error = str(exc)
            self._active = None

    def parse_intent(self, text: str, history: List[Dict[str, str]] | None = None) -> Dict[str, Any]:
        provider = self._pick()
        fallback = {"action": "chat", "parameters": {}, "confidence": 0.0, "speech": ""}
        if provider is None:
            return fallback

        recent = "\n".join(f"{m['role']}: {m['content']}" for m in (history or [])[-4:])
        prompt = (
            f"{_now_context()}\n\n{TOOL_SHEET}\n\n"
            "Map the user's command to exactly one action. "
            "If it is a question, conversation, advice, or nothing in the list fits, use 'chat'.\n"
            "Reply with JSON only, matching:\n"
            f"{json.dumps(INTENT_SCHEMA)}\n\n"
            + (f"Recent conversation:\n{recent}\n\n" if recent else "")
            + f"User command: {text!r}"
        )
        try:
            raw = provider.chat(
                "You convert commands into JSON. Output JSON only.",
                [{"role": "user", "content": prompt}],
                json_mode=True, max_tokens=260, temperature=0.0,
            )
        except Exception as exc:
            log.warning("intent provider failed: %s", exc)
            self._active = None
            return fallback

        data = self._extract_json(raw)
        if not data:
            log.debug("unparseable intent: %r", raw[:200])
            return fallback
        action = str(data.get("action", "chat")).strip()
        params = data.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        try:
            confidence = float(data.get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.6
        return {
            "action": action,
            "parameters": params,
            "confidence": max(0.0, min(1.0, confidence)),
            "speech": str(data.get("speech") or "").strip(),
        }

    def plan(self, goal: str, history: List[Dict[str, str]] | None = None) -> List[dict]:
        """Break a goal into concrete tool steps. Returns [] when unsure."""
        provider = self._pick()
        if provider is None:
            return []
        recent = "\n".join(f"{m['role']}: {m['content']}" for m in (history or [])[-4:])
        prompt = (
            f"{_now_context()}\n\n{TOOL_SHEET}\n\n"
            "Break the user's goal into two to six concrete steps on this Windows PC. "
            "Each step must use exactly one action from the tool sheet and only the "
            "parameters it needs. Never include shutdown, restart, delete, or shell "
            "commands. Do not repeat an action that has already achieved its purpose. "
            'Reply as JSON: {"steps":[{"action":"...","parameters":{...},'
            '"say":"one short sentence"}]}\n\n'
            + (f"Recent conversation:\n{recent}\n\n" if recent else "")
            + f"Goal: {goal!r}"
        )
        try:
            raw = provider.chat(
                "You are a careful task planner. Output JSON only.",
                [{"role": "user", "content": prompt}],
                json_mode=True, max_tokens=650, temperature=0.0,
            )
        except Exception as exc:
            log.warning("planner provider failed: %s", exc)
            self._active = None
            return []
        data = self._extract_json(raw) or {}
        steps = data.get("steps")
        return steps if isinstance(steps, list) else []

    def summarise(self, text: str, max_words: int = 120) -> str:
        return self.chat(
            f"Summarise the following for a spoken briefing in under {max_words} words. "
            f"Lead with the most important item.\n\n{text}",
            max_tokens=350,
        )

    def quick_model_chat(self, text: str) -> str:
        """Use the tiny model for trivial classification tasks."""
        provider = self._pick()
        if isinstance(provider, OllamaProvider):
            try:
                return provider.chat(
                    "Answer with one word only.", [{"role": "user", "content": text}],
                    model=cfg.OLLAMA_FAST_MODEL, max_tokens=8, temperature=0.0,
                )
            except Exception:
                return ""
        return self.chat(text, max_tokens=20)


brain = Brain()
