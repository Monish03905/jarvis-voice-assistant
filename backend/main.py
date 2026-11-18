"""FastAPI server: REST and WebSocket API for the JARVIS HUD."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config as cfg
import backend.db as db
from backend.agent import JarvisAgent
from backend.brain import brain
from backend.skills import browser, news, phone, updater
from backend.skills import email_skill, hardware, home, planner, research, security
from backend.skills import tasks as tasks_skill
from backend.skills import vision
from backend.voice import list_microphones

cfg.setup_logging()
log = logging.getLogger("jarvis.server")

_clients: List[WebSocket] = []
agent: Optional[JarvisAgent] = None


async def hud_emit(payload: Dict[str, Any]) -> None:
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _clients:
            _clients.remove(ws)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    for warning in cfg.validate_config():
        log.warning(warning)
    agent = JarvisAgent(hud_emit=hud_emit)
    await agent.start()
    log.info("JARVIS server ready on http://%s:%s", cfg.HOST, cfg.PORT)
    yield
    if agent:
        await agent.stop()


app = FastAPI(title="JARVIS", version=cfg.VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------
class CommandRequest(BaseModel):
    text: str = ""
    source: str = "ui"


class ExpenseRequest(BaseModel):
    amount: float
    category: str = "general"
    note: str = ""


class IncomeRequest(BaseModel):
    amount: float
    note: str = ""


class BudgetRequest(BaseModel):
    category: str
    amount: float


class ContactRequest(BaseModel):
    name: str
    platform: str = "any"
    handle: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None


class EmailTestRequest(BaseModel):
    account: Optional[str] = None


class ModeRequest(BaseModel):
    mode: str


class PrivacyRequest(BaseModel):
    on: bool = True


class ResearchRequest(BaseModel):
    topic: str
    depth: int = 3


class TaskRequest(BaseModel):
    title: str
    when: str = ""
    priority: int = 2


# ---------------------------------------------------------------------------
# websocket
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)
    await ws.send_json({"type": "connected", "version": cfg.VERSION,
                        "time": datetime.now().isoformat()})
    try:
        while True:
            message = await ws.receive_json()
            kind = message.get("type")
            if kind == "command" and agent:
                text = message.get("text") or message.get("command") or ""
                asyncio.create_task(agent.handle_command(text, source="ui"))
            elif kind == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        log.debug("websocket error: %s", exc)
    finally:
        if ws in _clients:
            _clients.remove(ws)


# ---------------------------------------------------------------------------
# chat / commands
# ---------------------------------------------------------------------------
@app.post("/api/command")
async def command(req: CommandRequest):
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(400, "Empty command")
    reply = await agent.handle_command(text, source=req.source or "ui")
    return {"reply": reply, "response": reply}


@app.post("/chat")
async def chat_compat(req: CommandRequest):
    return await command(req)


@app.get("/api/history")
async def history(limit: int = 30):
    return {"messages": db.recent_messages(limit)}


@app.post("/api/briefing")
async def briefing():
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    text = await agent.morning_briefing()
    return {"briefing": text}


# ---------------------------------------------------------------------------
# voice
# ---------------------------------------------------------------------------
@app.get("/api/voice")
async def voice_status():
    engine = agent.voice if agent else None
    return {
        "enrolled": bool(engine and engine.enrolled),
        "mode": engine.mode if engine else "none",
        "lock": cfg.VOICE_LOCK_ENABLED,
        "threshold": cfg.VOICE_MATCH_THRESHOLD,
        "running": bool(engine and engine.running),
        "microphones": list_microphones(),
    }


@app.post("/api/voice/enroll")
async def voice_enroll():
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    ok, score, mode = await asyncio.to_thread(agent.voice.enroll)
    return {"ok": ok, "score": score, "mode": mode}


@app.post("/api/voice/test")
async def voice_test():
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    ok, score = await asyncio.to_thread(agent.voice.test_voice)
    return {"ok": ok, "score": score}


@app.delete("/api/voice")
async def voice_forget():
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    agent.voice.forget_voiceprint()
    return {"ok": True}


# ---------------------------------------------------------------------------
# system / status
# ---------------------------------------------------------------------------
@app.get("/api/status")
async def status():
    return {
        "version": cfg.VERSION,
        "time": datetime.now().isoformat(),
        "brain": brain.status(),
        "voice": {
            "enrolled": bool(agent and agent.voice.enrolled),
            "running": bool(agent and agent.voice.running),
        },
        "user": cfg.USER_TITLE,
        "mode": agent.mode if agent else cfg.DEFAULT_MODE,
        "modes": [
            {"id": key, "label": value["label"], "hint": value["hint"]}
            for key, value in cfg.MODES.items()
        ],
        "safety": security.status(),
        "health": await asyncio.to_thread(updater.system_health),
        "stats": db.command_stats(),
    }


@app.get("/system-stats")
async def system_stats():
    battery = psutil.sensors_battery()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    network = psutil.net_io_counters()
    try:
        cpu = psutil.cpu_percent(interval=0.2)
    except Exception:
        cpu = 0.0
    return {
        "cpu": cpu,
        "ram": memory.percent,
        "battery": battery.percent if battery else None,
        "charging": battery.power_plugged if battery else None,
        "disk": disk.percent,
        "net_sent_mb": round(network.bytes_sent / (1024 * 1024), 2),
        "net_recv_mb": round(network.bytes_recv / (1024 * 1024), 2),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/vitals")
async def vitals():
    return await asyncio.to_thread(hardware.vitals)


# ---------------------------------------------------------------------------
# agenda / plans / modes / safety
# ---------------------------------------------------------------------------
@app.get("/api/agenda")
async def agenda(day: Optional[str] = None):
    return await asyncio.to_thread(tasks_skill.agenda_data, day)


@app.post("/api/tasks")
async def add_task(req: TaskRequest):
    message = await asyncio.to_thread(
        tasks_skill.add, req.title, req.when, req.priority
    )
    return {"message": message, "agenda": tasks_skill.agenda_data()}


@app.get("/api/plans")
async def plans(limit: int = 10):
    return {"plans": db.recent_plans(limit)}


@app.get("/api/mode")
async def get_mode():
    mode = agent.mode if agent else cfg.DEFAULT_MODE
    entry = cfg.MODES[mode]
    return {"mode": mode, "label": entry["label"], "hint": entry["hint"],
            "modes": [{"id": key, **value} for key, value in cfg.MODES.items()]}


@app.post("/api/mode")
async def set_mode(req: ModeRequest):
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    message = await agent._control("set_mode", {"mode": req.mode})
    if "do not have" in message:
        raise HTTPException(400, message)
    return {"message": message, "mode": agent.mode}


@app.post("/api/privacy")
async def set_privacy(req: PrivacyRequest):
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    message = await agent._control("privacy_on" if req.on else "privacy_off", {})
    return {"message": message, "privacy": security.privacy_enabled()}


@app.post("/api/stop")
async def emergency_stop():
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    message = await agent._control("emergency_stop", {})
    return {"message": message, "safety": security.status()}


@app.post("/api/resume")
async def resume():
    if agent is None:
        raise HTTPException(503, "JARVIS is still starting up")
    message = await agent._control("resume", {})
    return {"message": message, "safety": security.status()}


# ---------------------------------------------------------------------------
# vision / research / home
# ---------------------------------------------------------------------------
@app.get("/api/vision/screen")
async def vision_screen(question: str = ""):
    return {"message": await asyncio.to_thread(vision.analyze_screen, question)}


@app.get("/api/vision/text")
async def vision_text():
    return {"message": await asyncio.to_thread(vision.read_screen_text)}


@app.get("/api/vision/camera")
async def vision_camera(question: str = ""):
    return {"message": await asyncio.to_thread(vision.camera_look, question)}


@app.post("/api/research")
async def run_research(req: ResearchRequest):
    message = await asyncio.to_thread(research.deep_research, req.topic, req.depth)
    return {"message": message}


@app.get("/api/home")
async def home_status():
    return await asyncio.to_thread(home.summary_data)


# ---------------------------------------------------------------------------
# news
# ---------------------------------------------------------------------------
@app.get("/api/news")
async def get_news(category: str = "world", limit: int = 8):
    return {"items": news.headlines(category, limit)}


# ---------------------------------------------------------------------------
# money
# ---------------------------------------------------------------------------
@app.get("/api/money")
async def money():
    return db.money_summary()


@app.post("/api/money/expense")
async def money_expense(req: ExpenseRequest):
    from backend.skills import finance

    return {"message": finance.add_expense(req.amount, req.category, req.note)}


@app.post("/api/money/income")
async def money_income(req: IncomeRequest):
    from backend.skills import finance

    return {"message": finance.add_income(req.amount, req.note)}


@app.post("/api/money/budget")
async def money_budget(req: BudgetRequest):
    from backend.skills import finance

    return {"message": finance.set_budget(req.category, req.amount)}


# ---------------------------------------------------------------------------
# contacts
# ---------------------------------------------------------------------------
@app.get("/api/contacts")
async def contacts():
    return {"contacts": db.list_contacts()}


@app.post("/api/contacts")
async def save_contact(req: ContactRequest):
    if not req.name.strip():
        raise HTTPException(400, "Name is required")
    db.upsert_contact(req.name, req.platform, req.handle, req.phone, req.email, req.notes)
    return {"ok": True, "contact": db.find_contact(req.name, req.platform)}


# ---------------------------------------------------------------------------
# integrations
# ---------------------------------------------------------------------------
@app.get("/api/browser/status")
async def browser_status():
    return await asyncio.to_thread(browser.login_status)


@app.post("/api/browser/close")
async def browser_close():
    return {"message": browser.close_browser()}


@app.get("/api/phone/status")
async def phone_status():
    try:
        return await asyncio.to_thread(phone.status_cached)
    except Exception as exc:
        return {"open": False, "error": str(exc)}


@app.get("/api/email/accounts")
async def email_accounts():
    return email_skill.status()


@app.post("/api/email/test")
async def email_test(req: EmailTestRequest):
    return {"message": await asyncio.to_thread(email_skill.test_account, req.account)}


@app.post("/api/email/sync-contacts")
async def email_sync_contacts():
    return {"message": await asyncio.to_thread(email_skill.sync_contacts)}


@app.post("/api/phone/diagnose")
async def phone_diagnose():
    return {"message": await asyncio.to_thread(phone.diagnose)}


@app.get("/api/updates")
async def updates():
    return {"message": await asyncio.to_thread(updater.check_updates)}


@app.get("/")
async def root():
    index = cfg.FRONTEND_BUILD / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(_FALLBACK_HTML)


# ---------------------------------------------------------------------------
# static frontend
# ---------------------------------------------------------------------------
if cfg.FRONTEND_BUILD.exists():
    app.mount("/static", StaticFiles(directory=cfg.FRONTEND_BUILD / "static"), name="static")
    app.mount("/", StaticFiles(directory=cfg.FRONTEND_BUILD, html=True), name="app")


_FALLBACK_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>JARVIS</title>
<style>
 body{background:#05080d;color:#7df9ff;font-family:Consolas,monospace;display:grid;
 place-items:center;height:100vh;margin:0}
 .ring{width:220px;height:220px;border:2px solid #7df9ff;border-radius:50%;
 box-shadow:0 0 40px #00e5ff66 inset,0 0 30px #00e5ff44;animation:p 3s linear infinite}
 @keyframes p{to{transform:rotate(360deg)}}
 h1{letter-spacing:.4em;font-weight:300}
 p{color:#9ad}
</style></head>
<body><div style="text-align:center"><div class="ring"></div>
<h1>J.A.R.V.I.S.</h1><p>Backend online. Build the HUD with <code>npm run build</code>.</p></div></body></html>"""
