"""Screen understanding and camera vision.

Uses Gemini when a key is configured; otherwise falls back to Windows OCR
and OpenCV so core reading still works fully offline.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from PIL import Image, ImageGrab

import config as cfg
from backend.skills import security

log = logging.getLogger(__name__)

SHOT_DIR = cfg.DATA_DIR / "screenshots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

try:
    import winocr
except Exception:  # pragma: no cover
    winocr = None

try:
    import pygetwindow as gw
except Exception:  # pragma: no cover
    gw = None


def _gemini_available() -> bool:
    key = cfg.GEMINI_API_KEY or ""
    return len(key) > 30 and not key.lower().startswith(("your", "sk-"))


def _gemini_describe(prompt: str, image: Image.Image) -> str:
    buffer = io.BytesIO()
    copy = image.copy()
    copy.thumbnail((1400, 1400))
    copy.convert("RGB").save(buffer, format="JPEG", quality=82)
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": prompt},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
                    }
                },
            ],
        }],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500},
    }
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{cfg.GEMINI_MODEL}:generateContent?key={cfg.GEMINI_API_KEY}",
            json=payload, timeout=45,
        )
        response.raise_for_status()
        parts = response.json()["candidates"][0]["content"].get("parts", [])
        return "".join(part.get("text", "") for part in parts).strip()
    except Exception as exc:
        log.warning("gemini vision failed: %s", exc)
        return ""


def _ocr(image: Image.Image) -> str:
    if winocr is None:
        return ""

    async def run() -> str:
        result = await winocr.recognize_pil(image, "en-US")
        return "\n".join(line.text for line in result.lines)

    try:
        return asyncio.run(run()).strip()
    except Exception as exc:
        log.debug("ocr failed: %s", exc)
        return ""


def _front_window() -> str:
    if gw is None:
        return ""
    try:
        window = gw.getActiveWindow()
        return (window.title or "").strip() if window else ""
    except Exception:
        return ""


def _save(image: Image.Image, prefix: str) -> Path:
    path = SHOT_DIR / f"{prefix}-{datetime.now():%Y%m%d-%H%M%S}.jpg"
    try:
        image.convert("RGB").save(path, quality=88)
    except Exception:
        image.save(path)
    return path


def analyze_screen(question: str = "") -> str:
    if security.privacy_enabled():
        return "Privacy mode is on, Sir. I will not look at the screen until you switch it off."
    try:
        image = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        return f"I could not capture the screen, Sir. {exc}"
    path = _save(image, "screen")
    prompt = question or "Describe what is on this screen in two sentences, then note anything that looks like an error."
    if _gemini_available():
        answer = _gemini_describe(prompt, image)
        if answer:
            return answer
    text = _ocr(image)
    window = _front_window()
    bits = []
    if window:
        bits.append(f"The active window is {window}.")
    if text:
        condensed = re.sub(r"\s+", " ", text)[:900]
        bits.append(f"Visible text includes: {condensed}")
    bits.append(f"Screenshot saved at {path}.")
    return " ".join(bits) or f"I captured the screen at {path}, but could not read it."


def read_screen_text() -> str:
    if security.privacy_enabled():
        return "Privacy mode is on, Sir. I am not reading the screen."
    try:
        image = ImageGrab.grab(all_screens=True)
    except Exception as exc:
        return f"I could not capture the screen, Sir. {exc}"
    text = _ocr(image)
    if not text:
        return "I could not find readable text on the screen, Sir."
    condensed = re.sub(r"[ \t]+", " ", text)
    condensed = re.sub(r"\n{2,}", "\n", condensed)
    return condensed[:1600]


def camera_look(question: str = "") -> str:
    if security.privacy_enabled():
        return "Privacy mode is on, Sir. The camera stays off until you disable it."
    if cv2 is None:
        return "OpenCV is not installed, so I cannot use the camera, Sir."
    capture = None
    try:
        for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
            candidate = cv2.VideoCapture(0, backend)
            if candidate.isOpened():
                capture = candidate
                break
            candidate.release()
        if capture is None:
            return "I cannot reach a camera on this machine, Sir."
        ok, frame = capture.read()
    except Exception as exc:
        return f"The camera failed, Sir. {exc}"
    finally:
        if capture is not None:
            capture.release()
    if not ok or frame is None:
        return "The camera opened but returned no image, Sir."

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame)
    path = _save(image, "camera")

    faces = 0
    try:
        cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        faces = len(cascade.detectMultiScale(gray, 1.2, 5))
    except Exception:
        pass

    prompt = question or "Describe the person or scene in this camera photo briefly."
    if _gemini_available():
        answer = _gemini_describe(prompt, image)
        if answer:
            return f"{answer} Photo saved at {path}."
    if faces:
        return f"I can see {faces} face{'s' if faces != 1 else ''}. Photo saved at {path}."
    return (
        "I captured a camera frame but no face was detected at this angle. "
        f"Photo saved at {path}."
    )
