"""Windows control skills used by the agent router.

Every function returns a short sentence that can be spoken directly.
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

import psutil

import config as cfg

try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover
    gw = None

try:
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception as exc:
        return 1, str(exc)


def _start(target: str | list[str]) -> None:
    if isinstance(target, list):
        subprocess.Popen(target)
    elif target.startswith(("http://", "https://")):
        import webbrowser

        webbrowser.open(target)
    else:
        os.startfile(target)  # type: ignore[attr-defined]


APP_ALIASES = {
    "chrome": ["chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"],
    "google chrome": ["chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"],
    "edge": ["msedge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
    "brave": ["brave"],
    "firefox": ["firefox"],
    "notepad": ["notepad"],
    "calc": ["calc"],
    "calculator": ["calc"],
    "paint": ["mspaint"],
    "word": ["winword"],
    "excel": ["excel"],
    "powerpoint": ["powerpnt"],
    "outlook": ["outlook"],
    "vscode": ["code"],
    "vs code": ["code"],
    "visual studio code": ["code"],
    "pycharm": ["pycharm64"],
    "terminal": ["wt"],
    "cmd": ["cmd", "/c", "start", "cmd"],
    "powershell": ["powershell"],
    "explorer": ["explorer"],
    "file explorer": ["explorer"],
    "settings": ["ms-settings:"],
    "task manager": ["taskmgr"],
    "control panel": ["control"],
    "device manager": ["devmgmt.msc"],
    "camera": ["microsoft.windowscamera:"],
    "spotify": ["spotify:"],
    "discord": ["discord:"],
    "telegram": ["tg:"],
    "whatsapp": ["whatsapp:"],
    "phone link": [r"explorer.exe", r"shell:AppsFolder\Microsoft.YourPhone_8wekyb3d8bbwe!App"],
    "your phone": [r"explorer.exe", r"shell:AppsFolder\Microsoft.YourPhone_8wekyb3d8bbwe!App"],
    "steam": ["steam:"],
}


# ---------------------------------------------------------------------------
# voice / brightness (exact values)
# ---------------------------------------------------------------------------
def _volume_interface():
    try:
        from comtypes import CLSCTX_ALL
        from ctypes import POINTER, cast
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        speakers = AudioUtilities.GetSpeakers()
        # pycaw >= 2024 exposes EndpointVolume directly
        if hasattr(speakers, "EndpointVolume"):
            return speakers.EndpointVolume
        interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception:
        return None


def get_volume() -> str:
    vol = _volume_interface()
    if vol is None:
        return "I cannot read the volume on this machine, Sir."
    try:
        level = round(vol.GetMasterVolumeLevelScalar() * 100)
        muted = bool(vol.GetMute())
        return f"Volume is at {level} percent" + (" and muted" if muted else "") + ", Sir."
    except Exception as exc:
        return f"I could not read the volume, Sir. {exc}"


def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    vol = _volume_interface()
    if vol is None:
        return _media_steps("VOLUME_DOWN", 50) if level < 50 else _media_steps("VOLUME_UP", 50)
    try:
        if vol.GetMute():
            vol.SetMute(0, None)
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level} percent, Sir."
    except Exception as exc:
        return f"I could not set the volume, Sir. {exc}"


def volume_up(step: int = 10) -> str:
    vol = _volume_interface()
    if vol is None:
        return _media_steps("VOLUME_UP", 5)
    try:
        current = vol.GetMasterVolumeLevelScalar()
        vol.SetMasterVolumeLevelScalar(min(1.0, current + step / 100.0), None)
        return f"Volume up. Now at {round(min(1.0, current + step / 100.0) * 100)} percent."
    except Exception as exc:
        return f"I could not raise the volume, Sir. {exc}"


def volume_down(step: int = 10) -> str:
    vol = _volume_interface()
    if vol is None:
        return _media_steps("VOLUME_DOWN", 5)
    try:
        current = vol.GetMasterVolumeLevelScalar()
        vol.SetMasterVolumeLevelScalar(max(0.0, current - step / 100.0), None)
        return f"Volume down. Now at {round(max(0.0, current - step / 100.0) * 100)} percent."
    except Exception as exc:
        return f"I could not lower the volume, Sir. {exc}"


def mute_volume() -> str:
    vol = _volume_interface()
    if vol is None:
        return _media_steps("VOLUME_MUTE", 1)
    try:
        vol.SetMute(1, None)
        return "Muted, Sir."
    except Exception as exc:
        return f"I could not mute, Sir. {exc}"


def unmute_volume() -> str:
    vol = _volume_interface()
    if vol is None:
        return _media_steps("VOLUME_MUTE", 1)
    try:
        vol.SetMute(0, None)
        return "Sound restored, Sir."
    except Exception as exc:
        return f"I could not unmute, Sir. {exc}"


def set_brightness(level: int) -> str:
    level = max(0, min(100, int(level)))
    try:
        import screen_brightness_control as sbc

        sbc.set_brightness(level)
        return f"Brightness set to {level} percent, Sir."
    except Exception as exc:
        return f"I could not change the brightness, Sir. {exc}"


# ---------------------------------------------------------------------------
# apps and windows
# ---------------------------------------------------------------------------
def open_app(name: str) -> str:
    name = (name or "").strip().lower()
    if not name:
        return "Which application should I open, Sir?"
    try:
        candidates = APP_ALIASES.get(name)
        if candidates:
            _start(candidates)
            return f"Opening {name.title()}, Sir."
        # direct exe or URL
        if name.endswith(".exe") or os.path.exists(name):
            _start(name)
            return f"Opening {name}, Sir."
        # fall back to the shell's app resolver
        code, out = _run(["cmd", "/c", "start", "", name], timeout=10)
        if code == 0:
            return f"Opening {name}, Sir."
        return f"I could not find an app called {name}, Sir."
    except Exception as exc:
        return f"I could not open {name}, Sir. {exc}"


def close_app(name: str) -> str:
    name = (name or "").strip().lower()
    if not name:
        return "Which application should I close, Sir?"
    if name in {"chrome", "google chrome"}:
        name = "chrome"
    image = name if name.endswith(".exe") else f"{name}.exe"
    code, _ = _run(["taskkill", "/F", "/IM", image], timeout=10)
    if code == 0:
        return f"Closed {name}, Sir."
    killed = 0
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if name in pname and pname not in {"python.exe", "explorer.exe"}:
                proc.kill()
                killed += 1
        except Exception:
            continue
    if killed:
        return f"Closed {name}, Sir."
    if gw is not None:
        try:
            for win in gw.getWindowsWithTitle(name):
                win.close()
                killed += 1
        except Exception:
            pass
    return f"Closed {name}, Sir." if killed else f"{name.title()} is not running, Sir."


def switch_app(name: str) -> str:
    if not name:
        return "Which window should I switch to, Sir?"
    if gw is None:
        return "Window switching is unavailable, Sir."
    try:
        wins = [w for w in gw.getAllWindows() if name.lower() in (w.title or "").lower() and w.visible]
        if not wins:
            return f"I could not find a window for {name}, Sir."
        wins[0].activate()
        return f"Switching to {wins[0].title}, Sir."
    except Exception as exc:
        return f"I could not switch windows, Sir. {exc}"


def list_open_apps() -> str:
    try:
        if gw is not None:
            titles = [w.title for w in gw.getAllWindows() if w.title and w.visible]
            if titles:
                return "Open windows: " + "; ".join(titles[:12]) + "."
        names = sorted({p.info["name"] for p in psutil.process_iter(["name"]) if p.info.get("name")})
        return "Running processes include " + ", ".join(names[:15]) + "."
    except Exception as exc:
        return f"I could not list windows, Sir. {exc}"


def minimize_all() -> str:
    try:
        ctypes.windll.user32.keybd_event(0x5B, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x44, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x44, 0, 2, 0)
        ctypes.windll.user32.keybd_event(0x5B, 0, 2, 0)
        return "Minimised everything, Sir."
    except Exception as exc:
        return f"I could not minimise the windows, Sir. {exc}"


# ---------------------------------------------------------------------------
# power
# ---------------------------------------------------------------------------
def lock_screen() -> str:
    try:
        ctypes.windll.user32.LockWorkStation()
        return "Locking the workstation, Sir."
    except Exception as exc:
        return f"I could not lock the screen, Sir. {exc}"


def shutdown(timer: int = 10) -> str:
    if not cfg.ALLOW_POWER_ACTIONS:
        return "Power actions are disabled in my configuration, Sir."
    timer = max(0, int(timer))
    code, out = _run(["shutdown", "/s", "/t", str(timer)])
    if code == 0:
        return f"Shutting down in {timer} seconds, Sir."
    return f"I could not schedule the shutdown, Sir. {out}"


def restart(timer: int = 10) -> str:
    if not cfg.ALLOW_POWER_ACTIONS:
        return "Power actions are disabled in my configuration, Sir."
    timer = max(0, int(timer))
    code, out = _run(["shutdown", "/r", "/t", str(timer)])
    if code == 0:
        return f"Restarting in {timer} seconds, Sir."
    return f"I could not schedule the restart, Sir. {out}"


def cancel_shutdown() -> str:
    code, out = _run(["shutdown", "/a"])
    return "Power action cancelled, Sir." if code == 0 else f"There was nothing to cancel, Sir. {out}"


def sleep_mode() -> str:
    try:
        ctypes.windll.powrprof.SetSuspendState(False, True, False)
        return "Entering sleep, Sir."
    except Exception as exc:
        return f"I could not sleep the machine, Sir. {exc}"


def hibernate() -> str:
    try:
        ctypes.windll.powrprof.SetSuspendState(True, True, False)
        return "Hibernating, Sir."
    except Exception as exc:
        return f"I could not hibernate, Sir. {exc}"


def empty_recycle_bin() -> str:
    try:
        ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x1 | 0x2 | 0x4)
        return "Recycle bin emptied, Sir."
    except Exception as exc:
        return f"I could not empty the recycle bin, Sir. {exc}"


# ---------------------------------------------------------------------------
# system information
# ---------------------------------------------------------------------------
def get_battery_status() -> str:
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return "This machine has no battery, Sir."
        state = "charging" if battery.power_plugged else "on battery"
        return f"Battery at {round(battery.percent)} percent, {state}, Sir."
    except Exception as exc:
        return f"I could not read the battery, Sir. {exc}"


def get_cpu_ram_usage() -> str:
    try:
        cpu = psutil.cpu_percent(interval=0.6)
        mem = psutil.virtual_memory()
        return (
            f"Processor at {cpu:.0f} percent, memory at {mem.percent:.0f} percent "
            f"({mem.used / 1e9:.1f} of {mem.total / 1e9:.1f} gigabytes), Sir."
        )
    except Exception as exc:
        return f"I could not read the system load, Sir. {exc}"


def get_system_info() -> str:
    try:
        disk = psutil.disk_usage(str(Path.home().anchor))
        up = time.time() - psutil.boot_time()
        hours, minutes = int(up // 3600), int((up % 3600) // 60)
        return (
            f"{platform.system()} {platform.release()} on {platform.machine()}. "
            f"Disk {disk.percent:.0f} percent used. Uptime {hours} hours {minutes} minutes. "
            f"Hostname {platform.node()}."
        )
    except Exception as exc:
        return f"I could not gather system information, Sir. {exc}"


def get_ip_address() -> str:
    try:
        local = "unknown"
        for _, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family.name == "AF_INET" and not addr.address.startswith("127."):
                    local = addr.address
                    break
            if local != "unknown":
                break
        public = ""
        try:
            import requests

            public = requests.get("https://api.ipify.org", timeout=5).text.strip()
        except Exception:
            pass
        return f"Local address {local}" + (f", public address {public}" if public else "") + ", Sir."
    except Exception as exc:
        return f"I could not read the network address, Sir. {exc}"


def get_wifi_name() -> str:
    code, out = _run(["netsh", "wlan", "show", "interfaces"], timeout=10)
    match = re.search(r"^\s*SSID\s*:\s*(.+)$", out, flags=re.MULTILINE)
    if match:
        return f"Connected to {match.group(1).strip()}, Sir."
    return "I could not determine the Wi-Fi network, Sir."


def open_network_settings() -> str:
    try:
        os.startfile("ms-settings:network")  # type: ignore[attr-defined]
        return "Opening network settings, Sir."
    except Exception as exc:
        return f"I could not open network settings, Sir. {exc}"


def open_settings() -> str:
    return open_app("settings")


def task_manager() -> str:
    try:
        subprocess.Popen(["taskmgr"])
        return "Opening Task Manager, Sir."
    except Exception as exc:
        return f"I could not open Task Manager, Sir. {exc}"


def open_control_panel() -> str:
    try:
        subprocess.Popen(["control"])
        return "Opening Control Panel, Sir."
    except Exception as exc:
        return f"I could not open Control Panel, Sir. {exc}"


def open_device_manager() -> str:
    try:
        subprocess.Popen(["devmgmt.msc"])
        return "Opening Device Manager, Sir."
    except Exception as exc:
        return f"I could not open Device Manager, Sir. {exc}"


# ---------------------------------------------------------------------------
# keyboard, mouse, clipboard, screenshots
# ---------------------------------------------------------------------------
def type_text(text: str) -> str:
    if not text:
        return "There is nothing to type, Sir."
    try:
        # clipboard paste handles unicode correctly and is much faster
        if pyperclip is not None and pyautogui is not None:
            previous = ""
            try:
                previous = pyperclip.paste()
            except Exception:
                pass
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.15)
            if previous:
                try:
                    pyperclip.copy(previous)
                except Exception:
                    pass
            return "Typed, Sir."
        if pyautogui is not None:
            pyautogui.typewrite(text, interval=0.01)
            return "Typed, Sir."
        return "Keyboard control is unavailable, Sir."
    except Exception as exc:
        return f"I could not type that, Sir. {exc}"


def press_key(key: str) -> str:
    if pyautogui is None:
        return "Keyboard control is unavailable, Sir."
    try:
        pyautogui.press(key)
        return f"Pressed {key}, Sir."
    except Exception as exc:
        return f"I could not press that key, Sir. {exc}"


def hotkey(*keys: str) -> str:
    if pyautogui is None:
        return "Keyboard control is unavailable, Sir."
    flat: list[str] = []
    for key in keys:
        flat.extend(part.strip() for part in str(key).split("+") if part.strip())
    if not flat:
        return "Which shortcut, Sir?"
    try:
        pyautogui.hotkey(*flat)
        return f"Ran {'+'.join(flat)}, Sir."
    except Exception as exc:
        return f"I could not run that shortcut, Sir. {exc}"


def click(x: int, y: int) -> str:
    if pyautogui is None:
        return "Mouse control is unavailable, Sir."
    try:
        pyautogui.click(x=int(x), y=int(y))
        return f"Clicked at {x}, {y}, Sir."
    except Exception as exc:
        return f"I could not click there, Sir. {exc}"


def scroll(direction: str = "down", amount: int = 500) -> str:
    if pyautogui is None:
        return "Mouse control is unavailable, Sir."
    try:
        amount = abs(int(amount))
        pyautogui.scroll(amount if direction.lower().startswith("up") else -amount)
        return f"Scrolled {direction}, Sir."
    except Exception as exc:
        return f"I could not scroll, Sir. {exc}"


def screenshot() -> str:
    try:
        from PIL import ImageGrab

        target = Path.home() / "Pictures" / "JARVIS"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        ImageGrab.grab(all_screens=True).save(path)
        return f"Screenshot saved to {path}."
    except Exception as exc:
        return f"I could not take a screenshot, Sir. {exc}"


def copy_to_clipboard(text: str) -> str:
    try:
        pyperclip.copy(text or "")
        return "Copied to the clipboard, Sir."
    except Exception as exc:
        return f"I could not copy that, Sir. {exc}"


def get_clipboard() -> str:
    try:
        value = pyperclip.paste() or ""
        return f"The clipboard contains: {value[:400]}" if value else "The clipboard is empty, Sir."
    except Exception as exc:
        return f"I could not read the clipboard, Sir. {exc}"


# ---------------------------------------------------------------------------
# media keys
# ---------------------------------------------------------------------------
_MEDIA_KEYS = {
    "PLAY_PAUSE": 0xB3,
    "NEXT": 0xB0,
    "PREV": 0xB1,
    "STOP": 0xB2,
    "VOLUME_MUTE": 0xAD,
    "VOLUME_UP": 0xAF,
    "VOLUME_DOWN": 0xAE,
}


def _media_key(kind: str) -> None:
    vk = _MEDIA_KEYS[kind]
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def _media_steps(kind: str, count: int) -> str:
    for _ in range(max(1, count)):
        _media_key(kind)
        time.sleep(0.01)
    return "Done, Sir."


def play_pause_media() -> str:
    try:
        _media_key("PLAY_PAUSE")
        return "Toggled playback, Sir."
    except Exception as exc:
        return f"I could not control playback, Sir. {exc}"


def next_track() -> str:
    try:
        _media_key("NEXT")
        return "Next track, Sir."
    except Exception as exc:
        return f"I could not skip the track, Sir. {exc}"


def previous_track() -> str:
    try:
        _media_key("PREV")
        return f"Going back a track, Sir."
    except Exception as exc:
        return f"I could not go back, Sir. {exc}"


def stop_media() -> str:
    try:
        _media_key("STOP")
        return "Playback stopped, Sir."
    except Exception as exc:
        return f"I could not stop playback, Sir. {exc}"
