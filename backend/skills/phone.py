"""Microsoft Phone Link integration (calls and in-call controls).

Phone Link has no public API, so this drives the Windows app through UI
Automation. It is intentionally defensive: if the layout changes, the
``diagnose`` command writes the full control tree to
``data/phone_link_tree.txt`` so the selectors can be adjusted quickly.
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import config as cfg

log = logging.getLogger(__name__)

APP_ID = r"Microsoft.YourPhone_8wekyb3d8bbwe!App"
WINDOW_RE = re.compile(r"(phone link|your phone)", re.IGNORECASE)
CALL_BUTTON_RE = re.compile(
    r"^(call|call mobile|call now|voice call|audio call|call contact|make a call)$",
    re.IGNORECASE,
)
END_BUTTON_RE = re.compile(r"(end call|hang up|end)$", re.IGNORECASE)
MUTE_RE = re.compile(r"^(mute|mute microphone|unmute|unmute microphone)$", re.IGNORECASE)
SEARCH_RE = re.compile(r"(search|search contacts|search messages)", re.IGNORECASE)
CALLS_TAB_ID = "CallingNodeAutomationId"
SEARCH_IDS = ("SearchAutoSuggestBox", "MessagesSearchBox", "CallsSearchBox", "SearchBox")
OFFLINE_RE = re.compile(r"\boffline\b", re.IGNORECASE)


def _desktop():
    from pywinauto import Desktop

    return Desktop(backend="uia")


def launch() -> str:
    try:
        subprocess.Popen(["explorer.exe", rf"shell:AppsFolder\{APP_ID}"])
        return "Opening Phone Link, Sir."
    except Exception as exc:
        return f"I could not launch Phone Link, Sir. {exc}"


def _window(wait: float = 12.0):
    deadline = time.time() + wait
    last = None
    while time.time() < deadline:
        try:
            windows = [w for w in _desktop().windows() if WINDOW_RE.search(w.window_text() or "")]
            if windows:
                win = windows[0]
                try:
                    if win.is_minimized():
                        win.restore()
                    win.set_focus()
                except Exception:
                    pass
                return win
        except Exception as exc:
            last = exc
        time.sleep(0.7)
    if last:
        log.debug("Phone Link window error: %s", last)
    return None


def _visible_controls(window, control_type: Optional[str] = None):
    try:
        for control in window.descendants(control_type=control_type):
            try:
                if control.is_visible():
                    yield control
            except Exception:
                continue
    except Exception:
        return


def _text(control) -> str:
    try:
        return (control.window_text() or "").strip()
    except Exception:
        return ""


def _find(window, pattern: re.Pattern, control_type: Optional[str] = None):
    for control in _visible_controls(window, control_type):
        name = _text(control)
        if name and pattern.search(name):
            return control
    return None


def _click(control) -> bool:
    try:
        control.click_input()
        return True
    except Exception:
        try:
            control.invoke()
            return True
        except Exception:
            return False


def _activate(control) -> bool:
    """Tabs answer to select(), buttons to invoke(), rows to click_input()."""
    for method in ("select", "invoke", "click_input"):
        try:
            getattr(control, method)()
            return True
        except Exception:
            continue
    return False


def _by_auto_id(window, ids: tuple[str, ...], control_type: Optional[str] = None):
    wanted = {i.lower() for i in ids}
    for control in _visible_controls(window, control_type):
        try:
            if (control.element_info.automation_id or "").lower() in wanted:
                return control
        except Exception:
            continue
    return None


def _offline(window) -> bool:
    for control in _visible_controls(window, "Text"):
        name = _text(control)
        if not name or not OFFLINE_RE.search(name):
            continue
        try:
            auto_id = control.element_info.automation_id or ""
        except Exception:
            auto_id = ""
        if auto_id in ("ConnectivityStatusTextBlock", "") and len(name) < 24:
            return True
    return False


def _focus_search(window):
    """Calls tab exposes ContactSuggestionsBox > Edit; Messages tab a search Group."""
    box = _by_auto_id(window, ("ContactSuggestionsBox",))
    if box is not None:
        for edit in _visible_controls(box, "Edit"):
            _click(edit)
            time.sleep(0.2)
            try:
                edit.set_focus()
            except Exception:
                pass
            return edit
    search = _by_auto_id(window, SEARCH_IDS)
    if search is None:
        search = _find(window, SEARCH_RE, control_type="Edit") or _find(window, SEARCH_RE)
    if search is None:
        return None
    _click(search)
    time.sleep(0.2)
    try:
        search.set_focus()
    except Exception:
        pass
    return search


def _suggestion_rows(window) -> list:
    """Contact suggestions render in SuggestionsPopup under ContactSuggestionsBox."""
    box = _by_auto_id(window, ("ContactSuggestionsBox",))
    if box is None:
        return []
    try:
        return box.descendants(control_type="ListItem")
    except Exception:
        return []


def _call_button(window):
    button = _find(window, CALL_BUTTON_RE, control_type="Button")
    if button is not None:
        return button
    return _by_auto_id(window, ("ButtonCall",), "Button")


def _open_window() -> tuple[Optional[object], str]:
    window = _window(wait=3)
    if window is not None:
        return window, ""
    launch()
    window = _window(wait=15)
    if window is None:
        return None, (
            "Phone Link is not responding, Sir. Open it once manually and make sure your "
            "phone is connected."
        )
    return window, ""


# ---------------------------------------------------------------------------
# public actions
# ---------------------------------------------------------------------------
def call_contact(contact: str) -> str:
    contact = (contact or "").strip()
    if not contact:
        return "Who should I call, Sir?"
    window, error = _open_window()
    if window is None:
        return error
    try:
        if _offline(window):
            return (
                "Phone Link says your phone is offline, Sir. Reconnect it (Bluetooth) "
                "and ask me to call again."
            )

        # Phone Link's Calls section is a TabItem named "Calls (Ctrl+1)".
        calls_tab = _by_auto_id(window, (CALLS_TAB_ID,), "TabItem")
        if calls_tab is None:
            calls_tab = _find(window, re.compile(r"^calls\b", re.IGNORECASE), "TabItem")
        if calls_tab is not None:
            _activate(calls_tab)
            time.sleep(1.5)

        search = _focus_search(window)
        if search is None:
            return (
                "I opened Phone Link, Sir, but could not find its search box. "
                "Run the phone diagnostic so I can adapt to this version."
            )
        search.type_keys(contact, with_spaces=True, set_foreground=True)
        time.sleep(2.0)

        # Suggestion rows first (they live in SuggestionsPopup), then recent-call rows.
        needles = {contact.lower(), re.sub(r"\s+", "", contact.lower())}

        def matches(name: str) -> bool:
            name = name.lower()
            return bool(name) and (
                any(n in name for n in needles)
                or any(n in re.sub(r"\s+", "", name) for n in needles)
            )

        suggestions = [c for c in _suggestion_rows(window) if matches(_text(c))]
        if suggestions:
            # Prefer a mobile number when a contact has several.
            suggestions.sort(key=lambda c: 0 if "mobile" in _text(c).lower() else 1)
        candidate = suggestions[0] if suggestions else None
        if candidate is None:
            for ctype in ("ListItem", "Button"):
                for control in _visible_controls(window, ctype):
                    if matches(_text(control)):
                        candidate = control
                        break
                if candidate is not None:
                    break
        if candidate is not None:
            _click(candidate)
            time.sleep(1.5)
            if _find(window, MUTE_RE, "Button") or _find(window, END_BUTTON_RE, "Button"):
                return f"Calling {contact} through Phone Link, Sir."

        # The dial button: name "Call" or automation id "ButtonCall".
        call_button = _call_button(window)
        if call_button is None:
            return (
                f"I found {contact} in Phone Link, Sir, but the call button was not exposed. "
                "The window is open so you can tap call, or run the phone diagnostic."
            )
        if _activate(call_button):
            time.sleep(1.5)
            return f"Calling {contact} through Phone Link, Sir."
        return f"I could not press the call button for {contact}, Sir."
    except Exception as exc:
        log.warning("call_contact failed: %s", exc)
        return f"I could not place the call, Sir. {exc}"


def end_call() -> str:
    window, error = _open_window()
    if window is None:
        return error
    try:
        button = _find(window, END_BUTTON_RE, control_type="Button") or _find(window, END_BUTTON_RE)
        if button is not None and _click(button):
            return "Call ended, Sir."
        return "I could not find the end-call button, Sir."
    except Exception as exc:
        return f"I could not end the call, Sir. {exc}"


def toggle_mute() -> str:
    window, error = _open_window()
    if window is None:
        return error
    try:
        button = _find(window, MUTE_RE, control_type="Button") or _find(window, MUTE_RE)
        if button is None:
            return "There is no active call to mute, Sir."
        label = _text(button).lower()
        if _click(button):
            return "Microphone muted, Sir." if "unmute" not in label else "Microphone unmuted, Sir."
        return "I could not toggle the microphone, Sir."
    except Exception as exc:
        return f"I could not toggle mute, Sir. {exc}"


def mute_call() -> str:
    window, error = _open_window()
    if window is None:
        return error
    try:
        button = _find(window, re.compile(r"^mute( microphone)?$", re.IGNORECASE), control_type="Button")
        if button is not None and _click(button):
            return "Microphone muted, Sir."
        return toggle_mute()
    except Exception as exc:
        return f"I could not mute the call, Sir. {exc}"


def unmute_call() -> str:
    window, error = _open_window()
    if window is None:
        return error
    try:
        button = _find(window, re.compile(r"^unmute( microphone)?$", re.IGNORECASE), control_type="Button")
        if button is not None and _click(button):
            return "Microphone unmuted, Sir."
        return toggle_mute()
    except Exception as exc:
        return f"I could not unmute the call, Sir. {exc}"


def call_volume(level: int) -> str:
    # Call audio uses the default output device, so the normal volume control
    # is both correct and instant.
    from backend.skills import system_control

    return system_control.set_volume(level)


def phone_volume_up() -> str:
    from backend.skills import system_control

    return system_control.volume_up(15)


def phone_volume_down() -> str:
    from backend.skills import system_control

    return system_control.volume_down(15)


# ---------------------------------------------------------------------------
# diagnostics
# ---------------------------------------------------------------------------
def diagnose() -> str:
    """Dump the Phone Link control tree so selectors can be corrected."""
    window, error = _open_window()
    if window is None:
        return error
    target = Path(cfg.DATA_DIR) / "phone_link_tree.txt"
    lines: list[str] = []
    try:
        for control in window.descendants():
            try:
                if not control.is_visible():
                    continue
                lines.append(
                    f"{control.element_info.control_type:<14} | "
                    f"name={_text(control)!r} | auto_id={control.element_info.automation_id!r}"
                )
            except Exception:
                continue
        target.write_text("\n".join(lines), encoding="utf-8")
        return f"Phone Link layout captured to {target} ({len(lines)} controls)."
    except Exception as exc:
        return f"I could not inspect Phone Link, Sir. {exc}"


def status() -> dict:
    window = _window(wait=1.5)
    if window is None:
        return {"open": False}
    names = []
    try:
        for control in _visible_controls(window, "Button"):
            name = _text(control)
            if name:
                names.append(name)
    except Exception:
        pass
    in_call = any(END_BUTTON_RE.search(n) or MUTE_RE.search(n) for n in names)
    return {"open": True, "in_call": in_call, "buttons": names[:15]}


_STATUS_CACHE: dict = {"at": 0.0, "value": {"open": False}}


def status_cached(timeout: float = 3.0, ttl: float = 30.0) -> dict:
    """Never let a stalled UI Automation tree block the HUD or health checks."""
    now = time.time()
    if now - _STATUS_CACHE["at"] < ttl:
        return _STATUS_CACHE["value"]
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = status()
        except Exception as exc:
            box["value"] = {"open": False, "error": str(exc)}

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    value = box.get("value", {"open": False, "busy": True})
    _STATUS_CACHE.update(at=now, value=value)
    return value
