# JARVIS — Voice-First Desktop Assistant for Windows

**Just A Rather Very Intelligent System** — a local-first, voice-controlled AI assistant for Windows that actually operates your computer.

JARVIS listens for **"Hey Jarvis"**, verifies that the speaker is you, reasons with a local LLM, and then acts: opening apps, moving files, sending messages, placing calls, running multi-step plans, reading the screen, diagnosing hardware, and reporting back out loud inside a cinematic HUD.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6?logo=windows&logoColor=white)
![Local-first](https://img.shields.io/badge/Brain-Local%20Ollama-6B5B95)

```text
"Hey Jarvis"  →  voiceprint check  →  intent  →  action  →  spoken answer
```

> **Status — work in progress.** The backend, skill modules, and React HUD are implemented, and text commands through the HUD or `POST /api/command` are the verified path. The voice pipeline (wake word → STT → speaker check) is implemented but still being validated on the development machine — expect rough edges there, and run the no-microphone check below first.

## Contents

- [Why this project](#why-this-project)
- [What it can do](#what-it-can-do)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Verify it runs without a microphone](#verify-it-runs-without-a-microphone)
- [First five minutes](#first-five-minutes)
- [Command cookbook](#command-cookbook)
- [Voice pipeline](#voice-pipeline)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Operating modes](#operating-modes)
- [Plans and agenda](#plans-and-agenda)
- [Vision, hardware, research, smart home](#vision-hardware-research-smart-home)
- [Keys and accounts](#keys-and-accounts)
- [Email accounts](#email-accounts)
- [API surface](#api-surface)
- [Testing](#testing)
- [Safety and privacy](#safety-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Credits](#credits)

## Why this project

- **It does real work.** Not a chat wrapper — JARVIS drives Windows through window management, UI Automation, Selenium, `pycaw`, `psutil`, and Windows OCR.
- **It knows who is talking.** A Resemblyzer voiceprint is required before voice commands are obeyed; unverified voices are refused.
- **It runs offline.** The default brain is Ollama on your machine. Cloud models are optional fallbacks, never a requirement.
- **It plans.** Known workflows become deterministic step lists; open-ended goals are planned by the local model and validated against a safe action allow-list.
- **It has a safety model.** Emergency stop, privacy mode, confirmation gates, an allow-listed planner, and prompt-injection fencing around untrusted web content.
- **It looks the part.** The React HUD shows reactor state, waveform, vitals, GPU/thermals, agenda, execution plans, transcript, mail, budget, and world news.

## What it can do

| Area | Capability | Try saying |
| --- | --- | --- |
| **Voice** | Wake word, British TTS, owner-only voiceprint | *"Hey Jarvis"* → *"What's the weather?"* |
| **Power** | Shutdown, restart, sleep, hibernate, lock, cancel | *"Shut down in 5 minutes"* |
| **Apps & media** | Open/close apps, volume, mute, brightness, screenshots | *"Open VS Code"*, *"Set volume to 30"* |
| **Files** | Create, find, read, move, rename, delete to Recycle Bin, organize | *"Open the downloads folder"*, *"Find my resume PDF"* |
| **Browser** | YouTube playback, Google/YouTube search | *"Play lo-fi beats on YouTube"* |
| **Messaging** | WhatsApp Web and Instagram DMs through a dedicated Chrome profile | *"Send message to Ravi on WhatsApp saying I am late"* |
| **Phone** | Calls through Microsoft Phone Link, hang up, mute, call volume | *"Call Amma"*, *"Mute the call"* |
| **Email** | Multiple SMTP/IMAP accounts, read, send, contacts sync | *"Read my college email"*, *"Send an email from personal to Ravi about lunch"* |
| **Knowledge** | Keyless weather, world/tech/science news, Wikipedia, DuckDuckGo, math | *"World news"*, *"What is 12 percent of 4800?"* |
| **Planning** | Multi-step plans with progress in the HUD | *"Prepare my laptop for development"* |
| **Agenda** | Tasks, events, reminders, priorities, upcoming schedule | *"Add a task to call the bank tomorrow at 5"* |
| **Vision** | Windows OCR screen reading, screen/camera description with Gemini | *"Read my screen"*, *"Look at the camera"* |
| **Hardware** | GPU load/temps (NVIDIA), thermals, battery, disk, slowdown diagnosis | *"Why is my laptop slow?"*, *"Check my GPU"* |
| **Smart home** | Home Assistant lights, climate, scenes, status | *"Turn on the living room lights"* |
| **Research** | Deep-research markdown reports saved to `data/reports` | *"Deep research solid-state batteries"* |
| **Money** | Expense/income ledger, budgets, LLM budget advice | *"How much did I spend this month?"* |
| **Memory** | Notes, reminders, contacts, command history in SQLite | *"Remember that my locker code is 4412"* |
| **Ops** | Health report, dependency update check, plugin drop-in folder | *"Run a full diagnostic"* |

## Requirements

- **Windows 10/11**
- **Python 3.10+** (3.11/3.12 tested; 3.11 recommended)
- **Chrome** installed
- A **microphone** for voice control
- [Ollama](https://ollama.com) with two models:

```powershell
ollama pull qwen3.5:4b
ollama pull qwen3:0.6b
```

Optional:

- Microsoft Phone Link, signed in, for phone calls
- SMTP/IMAP app passwords for email
- WhatsApp Web / Instagram logins (one-time QR scan)
- `GEMINI_API_KEY` for screen and camera descriptions
- `HASS_URL` + `HASS_TOKEN` for Home Assistant
- Node.js 18+ only if you want to rebuild the HUD from source

## Quick start

```powershell
git clone https://github.com/Monish03905/jarvis-voice-assistant.git JARVIS
cd JARVIS

python -m venv .venv
.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

copy .env.example .env      # then edit names, city, optional keys
python setup.py             # checks, voice enrolment, WhatsApp login, contacts
python start.py             # server + HUD at http://127.0.0.1:8000
```

The production HUD is already built in `frontend/build`, so no Node build is needed for normal use.

Useful launcher flags:

```powershell
python start.py --port 8080     # different port
python start.py --no-browser    # headless start
python start.py --no-voice      # type-only session
```

To rebuild the HUD after frontend changes:

```powershell
cd frontend
npm install
npm run build
```

## Verify it runs without a microphone

Start a type-only session first. This exercises the server, brain, database, skills, and HUD without touching the voice stack:

```powershell
python start.py --no-voice
```

Then, in a second terminal:

```powershell
curl http://127.0.0.1:8000/api/status
```

The HUD should show **LINK**, **MIC OFF**, and your mode pill. The status JSON should report `brain`, `voice`, `health`, `mode`, and `safety` blocks.

Interactive API docs live at `http://127.0.0.1:8000/docs` — every HUD action is a plain HTTP or WebSocket call, so any skill can be exercised from there or from `curl` before wiring up voice.

## First five minutes

1. Run `python setup.py`, enrol your voice when prompted (12 seconds of speech).
2. Open the HUD. The top bar should show **LINK**, **VOICE LOCKED**, **MIC LIVE**.
3. Say: **"Hey Jarvis"** → wait for *"Yes?"* → **"What's the weather?"**
4. Try: *"Play lo-fi beats on YouTube"*, *"Open the downloads folder"*, *"How much did I spend this month?"*
5. Try: *"Prepare my laptop for development"*, *"Add a task to call the bank tomorrow"*, *"What is on my agenda?"*, *"Read my screen"*, *"Why is my laptop slow?"*
6. Add contacts in the setup wizard or with: *"Remember that Amma's phone is +91…"* (or edit `data/jarvis.db`).

## Command cookbook

**Everyday**

```text
"What is on my agenda?"
"Brief me"                          → weather, agenda, inbox, headlines
"What is the weather in Mumbai?"
"World news"
"How much did I spend this month?"
"Remind me to stretch in 30 minutes"
```

**Workstation**

```text
"Prepare my laptop for development"
"Open downloads folder"
"Search my files for thesis"
"Organize my downloads"
"Run a full diagnostic"
"Why is my laptop slow?"
"Check my GPU and temperatures"
```

**Communication**

```text
"Send message to Ravi on WhatsApp saying I am running late"
"Send an Instagram DM to Priya saying check your mail"
"Read my personal email"
"Send an email from college to professor about the project review"
"Call Amma"
"Mute the call" / "Increase call volume"
```

**Research and screen**

```text
"Deep research local-first AI assistants"
"Brief me on the James Webb telescope"
"Read my screen"
"What is on my screen?"
"Look at the camera"
```

**Modes and safety**

```text
"Enter developer mode" / "Switch to research mode"
"Privacy mode on" / "Privacy mode off"
"Emergency stop" / "Resume"
```

## Voice pipeline

| Stage | Default | Fallback |
| --- | --- | --- |
| Wake word | openWakeWord `hey_jarvis` (ONNX) | Whisper listening windows |
| Speech-to-text | faster-whisper `base.en` int8 | — |
| Speaker check | Resemblyzer voiceprint | NumPy spectral fingerprint |
| Text-to-speech | Edge-TTS `en-GB-RyanNeural` | pyttsx3 |

The voiceprint is stored at `data/voiceprint.npy`. Delete it or use `DELETE /api/voice` to forget it. While unenrolled, JARVIS still replies but warns that the lock is open; once enrolled, unverified voices are refused.

Tuning lives in `.env`:

```ini
VOICE_LOCK_ENABLED=true
VOICE_MATCH_THRESHOLD=0.78
WAKE_THRESHOLD=0.55
MIC_DEVICE=13          # optional sounddevice index; see the HUD's mic list
TTS_ENGINE=edge
TTS_VOICE=en-GB-RyanNeural
```

## Architecture

```text
start.py
  └─► FastAPI (backend/main.py) ──► WebSocket /ws ──► React HUD (frontend/build)
            │
            ├─► JarvisAgent (backend/agent.py)
            │     ├─ fast regex intents            (milliseconds)
            │     ├─ Brain.parse_intent            (strict JSON tool call)
            │     ├─ Planner                       (validated multi-step plans)
            │     └─ safety gate                   (confirmation, halt, privacy)
            ├─► VoiceEngine                        (wake → STT → verify → TTS)
            ├─► SQLite                             (data/jarvis.db, WAL)
            └─► Skills (backend/skills/)
                  system_control · files · browser · phone · email_skill
                  news · finance · info · updater · tasks · planner
                  vision · hardware · home · research · security
```

- **Two-speed routing:** deterministic regex for common commands (~milliseconds), local LLM JSON routing for everything else.
- **Local-first brain:** `BRAIN_PROVIDER=auto` tries Ollama first and only uses Gemini/OpenAI/Claude if a real key is configured.
- **Event-driven HUD:** transcripts, partial speech, voice state, plans, modes, privacy, halt flags, news, and toasts stream over WebSocket.
- **Persistent state:** conversations, commands, tasks, events, reminders, plans, contacts, budgets, and memories live in one SQLite database.
- **Confirmation gate:** shutdown, restart, delete, recycle bin, sleep, and hibernate require an explicit "yes" within 25 seconds.

## Project layout

```text
JARVIS/
├─ backend/
│  ├─ main.py              FastAPI app, REST + WebSocket, static HUD
│  ├─ agent.py             intent routing, dispatch, confirmations, plans
│  ├─ brain.py             Ollama / Gemini / OpenAI / Claude clients
│  ├─ voice.py             wake word, STT, voiceprint, TTS
│  ├─ db.py                SQLite schema and queries
│  └─ skills/              OS, files, browser, phone, email, news,
│                          finance, tasks, planner, vision, hardware,
│                          home, research, security, updater
├─ frontend/
│  ├─ src/                 React HUD components
│  └─ build/               prebuilt production HUD (served by FastAPI)
├─ tests/                  offline unit and routing tests
├─ tools/                  link_email.py, collect_keys.py
├─ assets/                 UI sounds
├─ config.py               environment-backed configuration
├─ setup.py                first-run wizard
├─ start.py                launcher
├─ requirements.txt
└─ .env.example
```

Runtime files such as `.env`, `data/`, `logs/`, `archive/`, `status.json`, and virtual environments are git-ignored.

## Operating modes

Modes change JARVIS's tone and default behaviour. Switch by voice or from the HUD.

| Mode | Focus |
| --- | --- |
| **Normal** | Balanced assistant |
| **Developer** | Code, repositories, diagnostics, precise answers |
| **Research** | Sources, summaries, reports |
| **System** | Hardware, processes, performance |
| **Vision** | Screen and camera analysis |
| **Security** | Terse, cautious, confirms more |
| **Autonomous** | Plans and executes without step-by-step chatter |

Set the startup mode with `DEFAULT_MODE=normal` in `.env`.

## Plans and agenda

JARVIS can break a goal into a short, validated sequence of safe actions and execute it step by step, streaming progress to the HUD's **Execution plan** panel and persisting every run to SQLite.

```text
"Prepare my laptop for development"   → usage, VS Code, terminal, health
"Start my day"                        → agenda, weather, inbox, headlines
"Run a full diagnostic"               → health, CPU/RAM, GPU, thermals, slowdown
"Organize my downloads"               → sort files into folders
"Close everything"                    → close common apps
```

Known workflows use deterministic plans. Anything else is planned by the local model, filtered against an allow-list (power, deletion, and financial actions are never buried inside a plan), capped at 8 steps, and paused for confirmation when a step sends a message or email. Say **"stop"** or press **STOP ALL** to halt immediately.

Tasks and events live in the same database and feed the agenda panel:

```text
"Add a task to call the bank tomorrow at 5"      (urgent / low priorities understood)
"Remind me to stretch in 30 minutes"
"Add a meeting with Ravi on Friday at 3 pm"
"List my tasks"  ·  "Mark the bank task done"  ·  "What is next?"
"What is on my agenda?"  (falls back to the next upcoming item when today is clear)
```

## Vision, hardware, research, smart home

- **Screen text** uses Windows' built-in OCR (`winocr`); no cloud key required.
- **Screen/camera description** uses Gemini when `GEMINI_API_KEY` is set; without it, JARVIS falls back to OCR and face counting.
- **Hardware** reads NVIDIA telemetry through `nvidia-smi`, thermals through `psutil` and WMI, and produces a slowdown diagnosis with top processes and memory hogs.
- **Research** searches DuckDuckGo, fetches public pages, fences the text as untrusted data, rejects prompt-injection patterns, and writes a markdown report to `data/reports/`.
- **Home Assistant** talks to the REST API with a long-lived token; it never stores your token anywhere except `.env`.

```ini
GEMINI_API_KEY=
HASS_URL=http://homeassistant.local:8123
HASS_TOKEN=
```

## Keys and accounts

Everything below is optional; JARVIS runs fully local without it.

| Feature | Setting |
| --- | --- |
| Cloud brain | `GEMINI_API_KEY` / `OPENAI_API_KEY` / `CLAUDE_API_KEY` |
| Email (any number of accounts) | `MAIL_<LABEL>_ADDRESS` + `MAIL_<LABEL>_PASSWORD` |
| Better TTS | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TTS_ENGINE=elevenlabs` |
| Location | `DEFAULT_CITY` (Open-Meteo is keyless) |
| Smart home | `HASS_URL`, `HASS_TOKEN` |
| Interface | `DEFAULT_MODE`, `PRIVACY_ON_START` |
| Permissions | `ALLOW_POWER_ACTIONS`, `ALLOW_FILE_DELETE`, `ALLOW_SHELL` |

API keys are issued by each provider after you sign in; JARVIS cannot create them. Run `python tools/collect_keys.py` (or `python setup.py`) and paste each key at the hidden prompt; it is stored only in the git-ignored `.env`.

## Email accounts

Use the local linker; it hides the password, tests IMAP + SMTP, and writes only to the git-ignored `.env`:

```bash
python tools/link_email.py            # add or update one account
python tools/link_email.py --list     # show linked labels
python tools/link_email.py --test     # verify logins without sending mail
```

Add any labels you like: `personal`, `college`, `work`. The label is spoken:

- *"Read my college email"*
- *"Send an email from personal to Ravi about lunch"*
- *"Which email accounts are linked?"*
- *"Sync my email contacts"* (imports inbox senders into `data/jarvis.db`)

Hosts are inferred from the domain (`smtp.gmail.com`, `smtp.office365.com`, `smtp.mail.yahoo.com`, `smtp.mail.me.com`, `smtp.zoho.com`, otherwise `smtp.<domain>`). Override with `MAIL_<LABEL>_SMTP_HOST/PORT/SSL` and `MAIL_<LABEL>_IMAP_HOST/PORT` if needed.

**Use app passwords, not your normal password.** Gmail and Microsoft reject plain passwords from third-party apps.

| Provider | Where to create an app password |
| --- | --- |
| Gmail / Google Workspace | `myaccount.google.com/apppasswords` (2-Step Verification on) |
| Outlook / Microsoft 365 | `account.microsoft.com/security` → App passwords, or ask IT |
| Yahoo | `account.yahoo.com` → Security → App passwords |
| iCloud | `appleid.apple.com` → App-specific passwords |

The HUD shows each linked account as `Mail · <label>` with `ready` or `incomplete` in the Vitals panel, and `GET /api/email/accounts` returns the same state.

## Browser automation and phone

- Dedicated Chrome profile: `%LOCALAPPDATA%\JARVIS\chrome-profile` (outside OneDrive).
- First WhatsApp use shows a QR code — scan it once.
- Instagram: log in once in the same profile.
- If the automation profile is already open in a normal Chrome window, close it first.

Phone Link has no public API. JARVIS drives its UI through Windows UI Automation: it opens the app, searches for the contact, clicks Call, then exposes hang-up, mute, and call volume. Run `POST /api/phone/diagnose` if a button cannot be found; it writes the full control tree to `data/phone_link_tree.txt`.

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| WS | `/ws` | transcripts, voice state, plans, modes, privacy, halt, news, toasts |
| POST | `/api/command` | run a command, return the spoken reply |
| POST | `/chat` | plain chat without a tool action |
| GET | `/api/history` | recent conversation messages |
| POST | `/api/briefing` | morning briefing |
| GET | `/api/status` | brain, voice, health, mode, safety |
| GET | `/system-stats` | CPU / RAM / battery / disk / network |
| GET | `/api/vitals` | GPU, thermals, battery, charging |
| GET | `/api/agenda` | today's events, tasks, reminders, upcoming items |
| POST | `/api/tasks` | add a task (`{title, when, priority}`) |
| GET | `/api/plans` | recent plan runs |
| GET/POST | `/api/mode` | read or set the operating mode |
| POST | `/api/privacy` | privacy mode on/off |
| POST | `/api/stop`, `/api/resume` | emergency stop / resume |
| GET | `/api/vision/screen`, `/api/vision/text`, `/api/vision/camera` | vision |
| POST | `/api/research` | deep-research report (`{topic, depth}`) |
| GET | `/api/home` | Home Assistant summary |
| GET | `/api/news?category=technology` | headlines |
| GET | `/api/voice` | voice status |
| POST | `/api/voice/enroll`, `/api/voice/test` | enrol or verify a voiceprint |
| DELETE | `/api/voice` | forget the voiceprint |
| GET/POST | `/api/money`, `/api/money/expense`, `/api/money/income`, `/api/money/budget` | ledger |
| GET/POST | `/api/contacts` | contact book |
| GET | `/api/browser/status` | automation Chrome profile |
| POST | `/api/browser/close` | close the automation browser |
| GET | `/api/phone/status` | Phone Link state |
| GET | `/api/email/accounts` | linked mail labels and readiness |
| POST | `/api/email/test` | verify IMAP/SMTP logins |
| POST | `/api/email/sync-contacts` | import inbox senders as contacts |
| POST | `/api/phone/diagnose` | dump the Phone Link control tree |
| GET | `/api/updates` | dependency update check |

Interactive docs: `http://127.0.0.1:8000/docs`.

## Testing

The offline suite covers routing, email accounts, task/time parsing, plan validation, and safety switches. It does not require a microphone, network, or a model.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Current result: **49 tests passing**.

Frontend checks:

```powershell
cd frontend
npm run build
```

The build completes without errors. The HUD was verified in Chrome with all modes, agenda, plan history, waveform, and safety pills rendering without console errors.

Manual verification checklist:

1. `python start.py --no-voice` and open the HUD.
2. Confirm **LINK**, **MIC OFF**, and the **NORMAL** pill.
3. Switch modes from the Mode panel.
4. Add a task and confirm it appears under Agenda or Upcoming.
5. Run *"Run a full diagnostic"* and watch the Execution plan panel.
6. Toggle privacy and confirm screen reading is refused.
7. Press **STOP ALL**, then **RESUME**.

The voice pipeline needs a real microphone and voice enrolment, so it is verified manually with the checklist in [Voice pipeline](#voice-pipeline) rather than in the automated suite.

## Safety and privacy

JARVIS is an assistant, not an administrator.

- The server binds to `127.0.0.1` only.
- Power actions, file deletion, and other destructive actions require an explicit confirmation.
- File deletion goes to the Recycle Bin via `send2trash`.
- Arbitrary shell execution is disabled unless `ALLOW_SHELL=true`.
- Voice commands are refused when the speaker does not match the enrolled voiceprint.
- Plans may only contain allow-listed steps; messages and emails inside a plan confirm first.
- **STOP ALL** / `POST /api/stop` halts plans and command execution immediately; **RESUME** restores normal operation.
- Privacy mode stops the microphone loop and refuses screen and camera access.
- Fetched web text is fenced as untrusted data and checked for prompt-injection patterns.
- `.env`, `data/`, `logs/`, `archive/`, `status.json`, virtual environments, and browser profiles are never committed.

Known limitations: UI Automation and web automation can break when Windows apps or third-party sites change their layout; call and message features require the relevant account to be signed in; Windows-only features are unavailable on other platforms.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| HUD says **NO LINK** | Backend is not running; run `python start.py` |
| "Ollama is not reachable" | Run `ollama serve`, then check `OLLAMA_MODEL` |
| No wake word | Try `WAKE_ENGINE=whisper`, or check the microphone index in the HUD |
| Voice rejected | Re-enrol in a quiet room; lower `VOICE_MATCH_THRESHOLD` slightly |
| WhatsApp QR every time | Profile folder deleted or Chrome already using that profile |
| Phone Link button missing | Run the diagnose endpoint and inspect `data/phone_link_tree.txt` |
| Email does nothing | Run `python tools/link_email.py`; Gmail/Outlook need an app password |
| Screen reading fails | Install the Windows OCR language pack; check `winocr` |
| Home Assistant unreachable | Verify `HASS_URL`, `HASS_TOKEN`, and the local network |
| Port 8000 already in use | `python start.py --port 8080` |
| PowerShell `pip` hangs | Use `python -m pip` or `uv pip install -r requirements.txt` |

Logs: `logs/jarvis.log`. Data: `data/jarvis.db`, `data/voiceprint.npy`, `data/reports/`.

Additional docs: [QUICK_START.md](QUICK_START.md) for a short setup path, [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) for operations and deployment notes.

## Credits

- Name and spirit are a fan tribute to Tony Stark's JARVIS. This project is not affiliated with Marvel.
- Inspired by the open-source [open-jarvis/OpenJarvis](https://github.com/open-jarvis/OpenJarvis) concept; this repository is a heavily rewritten, working Windows implementation.
- Built with FastAPI, React, Ollama, faster-whisper, openWakeWord, Resemblyzer, Edge-TTS, Selenium, pywinauto, and psutil.

This repository is published for portfolio review. No open-source license is granted for reuse unless one is added.
