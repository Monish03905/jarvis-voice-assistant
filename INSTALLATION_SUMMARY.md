# JARVIS Installation and Project Summary

A concise status sheet for the project. The authoritative setup and feature guide is [README.md](README.md).

## What this project is

JARVIS is a local-first, voice-controlled desktop assistant for Windows. It combines a FastAPI backend, a React HUD, a local Ollama brain, voice recognition with speaker verification, and direct Windows automation.

```text
wake word → speech-to-text → voiceprint check → intent → action → spoken reply
```

## Implemented components

| Component | Status | Notes |
| --- | --- | --- |
| FastAPI server + WebSocket HUD | Implemented | Serves the prebuilt React app and streams events |
| Local brain (Ollama) | Implemented | `qwen3.5:4b` default, `qwen3:0.6b` fast path |
| Cloud fallbacks | Implemented | Gemini, OpenAI, Claude over plain HTTP |
| Voice pipeline | Implemented, hardware validation pending | openWakeWord, faster-whisper, Resemblyzer, Edge-TTS/pyttsx3 |
| OS control | Implemented | Apps, volume, brightness, power, screenshots, window state |
| Files | Implemented | Search, open, move, rename, delete to Recycle Bin, organize |
| Browser automation | Implemented | YouTube, Google, WhatsApp Web, Instagram |
| Phone Link | Implemented | Calls, hang up, mute, call volume through UI Automation |
| Email | Implemented | Multiple SMTP/IMAP accounts, read, send, contacts sync |
| News, weather, knowledge | Implemented | Google News RSS, Open-Meteo, Wikipedia, DuckDuckGo |
| Finance | Implemented | Expenses, income, budgets, LLM advice |
| Tasks, events, agenda | Implemented | SQLite persistence, natural-language times, priorities |
| Multi-step planner | Implemented | Allow-listed steps, confirmation gates, persisted runs |
| Vision | Implemented | Windows OCR, Gemini screen/camera description |
| Hardware telemetry | Implemented | NVIDIA GPU, thermals, battery, disk, slowdown diagnosis |
| Home Assistant | Implemented | Lights, climate, scenes, status |
| Deep research | Implemented | Markdown reports with fenced untrusted sources |
| Safety controls | Implemented | Emergency stop, privacy mode, injection checks |
| HUD | Implemented | Modes, agenda, plans, waveform, vitals, mail, budget, news |

## Verified on the development machine

- 49 offline tests pass.
- The production React build compiles without errors.
- Text commands work through the HUD and `POST /api/command`.
- A 5-step diagnostic plan executed and persisted to SQLite.
- Mode switching, privacy blocking, emergency stop/resume, agenda creation, and GPU/thermal telemetry were exercised live.
- The HUD renders all mode buttons, agenda/upcoming items, plan history, waveform, and safety pills with no console errors.

## Not yet verified end to end

- Wake word, speech-to-text accuracy, and speaker verification with a real enrolled microphone.
- WhatsApp/Instagram message delivery after a QR login.
- Phone Link call placement and call controls on the target phone.
- Personal and college email logins (app passwords not yet supplied).
- Home Assistant control (no `HASS_URL`/`HASS_TOKEN` yet).

These require local accounts, hardware, or credentials; the code paths and HUD controls exist.

## Technology stack

| Layer | Technology |
| --- | --- |
| Server | FastAPI, Uvicorn, WebSocket |
| Frontend | React 18, Create React App |
| Brain | Ollama; Gemini/OpenAI/Claude optional |
| Voice | openWakeWord, faster-whisper, Resemblyzer, Edge-TTS |
| Desktop | pywinauto, pyautogui, pycaw, pygetwindow, psutil |
| Browser | Selenium with a dedicated Chrome profile |
| Data | SQLite (WAL), dotenv |
| Vision | winocr, OpenCV, Pillow |
| Hardware | nvidia-smi, WMI, psutil |

## Important paths

```text
backend/            server, agent, brain, voice, database, skills
frontend/src/       React HUD source
frontend/build/     prebuilt HUD served by FastAPI
tests/              offline test suite
tools/              email linker and key collector
data/jarvis.db      runtime database (git-ignored)
data/voiceprint.npy voiceprint (git-ignored)
logs/jarvis.log     runtime log (git-ignored)
```

## Setup in one screen

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
python setup.py
python start.py
```

No-microphone check:

```powershell
python start.py --no-voice
curl http://127.0.0.1:8000/api/status
```

## Next steps

1. Enrol your voice and validate wake word → reply.
2. Link personal and college email with app passwords.
3. Add a Gemini key if you want screen and camera descriptions.
4. Configure Home Assistant if you want smart-home control.
5. Sign in to Phone Link and run one test call.
6. Scan the WhatsApp QR once and send a test message.
