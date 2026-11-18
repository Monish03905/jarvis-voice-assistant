"""Chrome automation for YouTube, WhatsApp and Instagram.

Uses one persistent Chrome profile (``data/chrome-profile``) so the user only
has to log in once. Selenium drives the browser; if anything is missing we
fall back to simply opening the URL in the default browser.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, quote_plus

import config as cfg

log = logging.getLogger(__name__)

_LOCK = threading.RLock()
_DRIVER = None


# ---------------------------------------------------------------------------
# driver lifecycle
# ---------------------------------------------------------------------------
def _build_options():
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    if Path(cfg.CHROME_PATH).exists():
        opts.binary_location = cfg.CHROME_PATH
    opts.add_argument(f"--user-data-dir={cfg.CHROME_PROFILE_DIR}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--autoplay-policy=no-user-gesture-required")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--ignore-certificate-errors")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_experimental_option("detach", True)
    if cfg.BROWSER_HEADLESS:
        opts.add_argument("--headless=new")
    return opts


def driver():
    """Return a live Chrome driver, creating it if needed."""
    global _DRIVER
    with _LOCK:
        if _DRIVER is not None:
            try:
                _ = _DRIVER.current_url
                return _DRIVER
            except Exception:
                try:
                    _DRIVER.quit()
                except Exception:
                    pass
                _DRIVER = None
        try:
            from selenium import webdriver

            log.info("Launching Chrome with profile %s", cfg.CHROME_PROFILE_DIR)
            _DRIVER = webdriver.Chrome(options=_build_options())
            try:
                _DRIVER.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
                )
            except Exception:
                pass
            return _DRIVER
        except Exception as exc:
            log.error("Chrome launch failed: %s", exc)
            raise RuntimeError(
                "I could not start Chrome. Check that Chrome is installed and close any "
                "Chrome window using the JARVIS profile."
            ) from exc


def close_browser() -> str:
    global _DRIVER
    with _LOCK:
        if _DRIVER is not None:
            try:
                _DRIVER.quit()
            except Exception:
                pass
            _DRIVER = None
    return "Closed the automated browser, Sir."


def _wait(css: str, timeout: float = 20):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    return WebDriverWait(driver(), timeout).until(
        lambda d: d.find_element(By.CSS_SELECTOR, css)
    )


def _try_first(selectors: list[str], timeout: float = 15):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    last = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        for selector in selectors:
            try:
                elements = driver().find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed():
                        return element
            except Exception as exc:
                last = exc
        time.sleep(0.4)
    if last:
        log.debug("selector miss: %s", last)
    return None


def _click_element(element) -> None:
    try:
        element.click()
    except Exception:
        driver().execute_script("arguments[0].click();", element)


def _open_input():
    from selenium.webdriver.common.by import By

    return driver().find_element(By.TAG_NAME, "body")


# ---------------------------------------------------------------------------
# generic navigation
# ---------------------------------------------------------------------------
def open_url(url: str, reuse: bool = True) -> bool:
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        d = driver()
        if reuse:
            d.get(url)
        else:
            d.switch_to.new_window("tab")
            d.get(url)
        return True
    except Exception as exc:
        log.error("open_url failed: %s", exc)
        try:
            import webbrowser

            webbrowser.open(url)
            return True
        except Exception:
            return False


def open_website(url: str) -> str:
    if not url:
        return "Which website should I open, Sir?"
    shortcuts = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "github": "https://github.com",
        "gmail": "https://mail.google.com",
        "netflix": "https://www.netflix.com",
        "whatsapp": "https://web.whatsapp.com",
        "whatsapp web": "https://web.whatsapp.com",
        "instagram": "https://www.instagram.com",
        "spotify": "https://open.spotify.com",
    }
    target = shortcuts.get(url.strip().lower(), url.strip())
    if not target.startswith(("http://", "https://")):
        target = "https://" + target
    if open_url(target):
        return f"Opening {url}, Sir."
    return f"I could not open {url}, Sir."


def search_google(query: str) -> str:
    if not query:
        return "What should I search for, Sir?"
    if open_url("https://www.google.com/search?q=" + quote_plus(query)):
        return f"Searching Google for {query}, Sir."
    return "I could not reach Google, Sir."


def search_youtube(query: str) -> str:
    if not query:
        return "What should I play, Sir?"
    if open_url("https://www.youtube.com/results?search_query=" + quote_plus(query)):
        return f"Here are YouTube results for {query}, Sir."
    return "I could not reach YouTube, Sir."


# ---------------------------------------------------------------------------
# YouTube playback
# ---------------------------------------------------------------------------
def play_youtube(query: str) -> str:
    """Search YouTube in Chrome and start the first result."""
    query = (query or "").strip()
    if not query:
        return "What would you like me to play, Sir?"
    try:
        open_url("https://www.youtube.com/results?search_query=" + quote_plus(query))
        # consent / cookie dialogs
        for selector in [
            "button[aria-label*='Accept']",
            "button[aria-label*='accept']",
            "tp-yt-paper-button[id='button']",
        ]:
            from selenium.webdriver.common.by import By

            try:
                for button in driver().find_elements(By.CSS_SELECTOR, selector):
                    if button.is_displayed():
                        _click_element(button)
                        break
            except Exception:
                pass

        link = _try_first([
            "ytd-video-renderer a#video-title",
            "ytd-video-renderer a#thumbnail",
            "a#video-title",
            "ytd-rich-item-renderer a#thumbnail",
        ], timeout=18)
        if link is None:
            return f"I found the results for {query}, but could not pick a video, Sir."
        from selenium.webdriver.common.keys import Keys

        _click_element(link)
        time.sleep(2.5)
        # Some browsers still show a "play" overlay; press k once.
        try:
            body = _open_input()
            body.send_keys("k")
        except Exception:
            pass
        time.sleep(1.5)
        try:
            paused = driver().execute_script(
                "const v=document.querySelector('video'); return v ? v.paused : null;"
            )
        except Exception:
            paused = None
        state = "playing" if paused is False else "opening"
        return f"{state.capitalize()} {query} on YouTube, Sir."
    except Exception as exc:
        log.warning("play_youtube failed: %s", exc)
        try:
            import webbrowser

            webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(query))
        except Exception:
            return f"I could not play that on YouTube, Sir. {exc}"
        return f"I opened YouTube for {query}, Sir, but could not press play automatically."


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------
WHATSAPP_MESSAGE_BOX = [
    "footer div[contenteditable='true']",
    "div[contenteditable='true'][data-tab='10']",
    "div[aria-label*='Type a message']",
]


def _whatsapp_state() -> str:
    """Return 'chat', 'qr' or 'unknown'."""
    from selenium.webdriver.common.by import By

    try:
        d = driver()
        if d.find_elements(By.CSS_SELECTOR, "canvas[aria-label*='Scan'], canvas[aria-label*='scan']"):
            return "qr"
        if d.find_elements(By.CSS_SELECTOR, "#pane-side, div[aria-label*='Chat list']"):
            return "chat"
        if d.find_elements(By.CSS_SELECTOR, WHATSAPP_MESSAGE_BOX[0]):
            return "chat"
    except Exception:
        pass
    return "unknown"


def _whatsapp_send_via_number(phone: str, message: str) -> bool:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if not digits:
        return False
    url = f"https://web.whatsapp.com/send?phone={digits}&text={quote(message)}"
    open_url(url)
    box = _try_first(WHATSAPP_MESSAGE_BOX, timeout=25)
    if box is None:
        return False
    from selenium.webdriver.common.keys import Keys

    _click_element(box)
    time.sleep(0.4)
    box.send_keys(Keys.ENTER)
    time.sleep(1.0)
    return True


def _whatsapp_send_via_name(contact: str, message: str) -> bool:
    from selenium.webdriver.common.keys import Keys

    search = _try_first([
        "div[aria-label='Search input textbox']",
        "#side div[contenteditable='true']",
        "div[contenteditable='true'][data-tab='3']",
        "header div[contenteditable='true']",
    ], timeout=15)
    if search is None:
        return False
    _click_element(search)
    time.sleep(0.3)
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(Keys.BACKSPACE)
    search.send_keys(contact)
    time.sleep(1.6)
    # pick the first visible chat row
    row = _try_first([
        "#pane-side div[role='listitem']",
        "#pane-side div[role='row']",
        "div[aria-label*='Chat list'] div[role='listitem']",
    ], timeout=8)
    if row is not None:
        _click_element(row)
    else:
        search.send_keys(Keys.ENTER)
    box = _try_first(WHATSAPP_MESSAGE_BOX, timeout=15)
    if box is None:
        return False
    _click_element(box)
    time.sleep(0.3)
    if not message:
        return True
    for line in message.split("\n"):
        box.send_keys(line)
        box.send_keys(Keys.SHIFT, Keys.ENTER)
    box.send_keys(Keys.ENTER)
    time.sleep(1.0)
    return True


def send_whatsapp(contact: str, message: str, phone: str | None = None) -> str:
    contact = (contact or "").strip()
    message = (message or "").strip()
    if not contact:
        return "Who should I message on WhatsApp, Sir?"
    if not message:
        return "What should the message say, Sir?"
    try:
        open_url("https://web.whatsapp.com")
        time.sleep(3)
        state = _whatsapp_state()
        if state == "qr":
            return (
                "WhatsApp Web needs a one-time login, Sir. A QR code is open in Chrome; "
                "scan it with your phone, then ask me again."
            )
        if phone and _whatsapp_send_via_number(phone, message):
            return f"Message sent to {contact} on WhatsApp, Sir."
        if _whatsapp_send_via_name(contact, message):
            return f"Message sent to {contact} on WhatsApp, Sir."
        return (
            f"I could not find {contact} on WhatsApp, Sir. "
            "Check the exact chat name, or add their number with 'save contact'."
        )
    except Exception as exc:
        log.warning("send_whatsapp failed: %s", exc)
        return f"WhatsApp automation failed, Sir. {exc}"


def open_whatsapp(contact: str = "") -> str:
    try:
        if contact:
            open_url("https://web.whatsapp.com")
            time.sleep(2.5)
            if _whatsapp_state() == "qr":
                return "WhatsApp Web is showing a QR code, Sir. Scan it once to log in."
            _whatsapp_send_via_name(contact, "")
            return f"Opened the chat with {contact} on WhatsApp, Sir."
        open_url("https://web.whatsapp.com")
        return "Opening WhatsApp Web, Sir."
    except Exception as exc:
        return f"I could not open WhatsApp, Sir. {exc}"


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------
def send_instagram(contact: str, message: str) -> str:
    contact = (contact or "").strip().lstrip("@")
    message = (message or "").strip()
    if not contact:
        return "Who should I message on Instagram, Sir?"
    if not message:
        return "What should the message say, Sir?"
    from selenium.webdriver.common.keys import Keys

    try:
        open_url(f"https://www.instagram.com/{quote(contact)}/")
        time.sleep(3.5)
        d = driver()
        if "accounts/login" in (d.current_url or ""):
            return (
                "Instagram needs a one-time login, Sir. Log in in the Chrome window, "
                "then ask me again."
            )
        from selenium.webdriver.common.by import By

        # Prefer a button whose visible text is Message
        message_button = None
        for element in d.find_elements(By.XPATH, "//div[@role='button' or self::button]"):
            try:
                if element.is_displayed() and (element.text or "").strip().lower() in {"message", "send message"}:
                    message_button = element
                    break
            except Exception:
                continue
        if message_button is None:
            return (
                f"I opened {contact}'s Instagram profile, Sir, but could not find the Message button. "
                "Instagram may require a login or changed its layout."
            )
        _click_element(message_button)
        time.sleep(2.5)
        box = _try_first([
            "div[contenteditable='true'][role='textbox']",
            "textarea[placeholder*='Message']",
            "div[aria-label*='Message']",
        ], timeout=12)
        if box is None:
            return "I could not find Instagram's message box, Sir."
        _click_element(box)
        time.sleep(0.3)
        for line in message.split("\n"):
            box.send_keys(line)
            box.send_keys(Keys.SHIFT, Keys.ENTER)
        box.send_keys(Keys.ENTER)
        time.sleep(1.0)
        return f"Message sent to {contact} on Instagram, Sir."
    except Exception as exc:
        log.warning("send_instagram failed: %s", exc)
        return f"Instagram automation failed, Sir. {exc}"


# ---------------------------------------------------------------------------
# login / diagnostics
# ---------------------------------------------------------------------------
def login_status() -> dict:
    """Quick, non-blocking-ish check used by the HUD."""
    status = {"chrome": False, "whatsapp": "unknown", "instagram": "unknown"}
    try:
        open_url("https://web.whatsapp.com")
        time.sleep(3)
        status["chrome"] = True
        status["whatsapp"] = _whatsapp_state()
    except Exception as exc:
        status["error"] = str(exc)
    return status


def warm() -> None:
    """Launch Chrome and the driver in the background."""
    def run():
        try:
            driver()
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()
