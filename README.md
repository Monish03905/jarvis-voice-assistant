# JARVIS — Voice-First Desktop Assistant for Windows

A local-first, voice-controlled JARVIS for Windows: wake word, speaker verification,
a real reasoning brain (Ollama by default), full desktop control, browser automation
for YouTube / WhatsApp / Instagram, Microsoft Phone Link calls, email, news, budgets,
multi-step plans, screen vision, hardware diagnostics, smart-home control, and a
cinematic HUD with operating modes.

```text
"Hey Jarvis"  →  voiceprint check  →  intent  →  action  →  spoken answer
```

> **Status — work in progress.** The backend, skill modules and React HUD are
> implemented, and text commands through the HUD or `POST /api/command` are the
> verified path. The voice pipeline (wake word → STT → speaker check) is the area
> still under active verification on the development machine — expect rough edges
> there, and run the no-microphone check below first.

## What it can do

| Area | Examples |
| --- | --- |
| **Voice** | Wake word "Hey Jarvis", British TTS, **only your enrolled voice is obeyed** |
| **Power** | Shutdown / restart (with a timer), sleep, hibernate, lock, cancel shutdown |
| **Apps & media** | Open/close apps, exact volume, mute, brightness, screenshot, media keys |
| **Files** | Create, find, read, move, rename, delete (Recycle Bin), organize folders |
| **Browser** | "Play lo-fi on YouTube", Google/YouTube search, WhatsApp & Instagram messages |
| **Phone** | Place calls through Microsoft Phone Link, hang up, mute, call volume |
| **Comms** | Send/read email (SMTP/IMAP), WhatsApp Web, Instagram DMs |
| **Knowledge** | Weather (keyless), world/tech/science news, Wikipedia, DuckDuckGo, calculator |
| **Planning** | Multi-step plans ("prepare my laptop", "start my day", "full diagnostic") |
| **Agenda** | Tasks, calendar events, reminders, upcoming schedule, daily briefing |
| **Vision** | Read the screen (OCR), describe the screen or camera (Gemini if keyed) |
| **Hardware** | GPU load/temps (NVIDIA), thermals, battery, disk, slowdown diagnosis |
| **Smart home** | Home Assistant lights, climate, scenes, status summary |
| **Research** | Deep-research markdown reports saved to `data/reports` |
| **Modes** | Normal, Developer, Research, System, Vision, Security, Autonomous |
| **Money** | Expense/income ledger, category budgets, LLM budget advice |
| **Memory** | Notes, reminders, contacts, command history in SQLite |
| **Ops** | Health report, dependency update check, plugin drop-in directory |

## Requirements

- Windows 10/11, Python **3.10+** (3.11/3.12 tested), Chrome, a microphone
- [Ollama](https://ollama.com) with a tool-capable model:
  ```powershell
  ollama pull qwen3.5:4b
  ollama pull qwen3:0.6b
  ```
- Optional: Microsoft Phone Link (for calls), an SMTP/IMAP account (for email),
  WhatsApp Web / Instagram logins (first-time QR scan).

## Install

```powershell
git clone https://github.com/Monish03905/jarvis-voice-assistant.git JARVIS
cd JARVIS
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then edit names, city, optional keys
python setup.py             # checks, voice enrollment, WhatsApp login, contacts
python start.py             # server + HUD at http://127.0.0.1:8000
```

### Verify it runs (no microphone needed)

```powershell
python start.py --no-voice
# then, in a second terminal:
curl http://127.0.0.1:8000/api/status
```

The HUD should show **LINK** and the status JSON should report the brain, voice and
health blocks. Interactive API docs live at `http://127.0.0.1:8000/docs` — every HUD
action is a plain HTTP or WebSocket call, so any skill can be exercised from there or
from `curl` before wiring up voice.

The React HUD ships prebuilt. To rebuild after frontend changes:

```powershell
cd frontend
npm install
npm run build
```

## First five minutes

1. Run `python setup.py`, enrol your voice when prompted (12 seconds of speech).
2. Open the HUD. The top bar should show **LINK**, **VOICE LOCKED**, **MIC LIVE**.
3. Say: **"Hey Jarvis"** → wait for *"Yes?"* → **"What's the weather?"**
4. Try: *"Play lo-fi beats on YouTube"*, *"Open the downloads folder"*,
   *"How much did I spend this month?"*
5. Try: *"Prepare my laptop for development"*, *"Add a task to call the bank tomorrow"*,
   *"What is on my agenda?"*, *"Read my screen"*, *"Why is my laptop slow?"*
6. Add contacts in the setup wizard or with:
   *"Remember that Amma's phone is +91…"* (or edit `data/jarvis.db`).

## Voice pipeline

| Stage | Default | Fallback |
| --- | --- | --- |
| Wake word | openWakeWord `hey_jarvis` (ONNX) | Whisper listening windows |
| Speech-to-text | faster-whisper `base.en` int8 | — |
| Speaker check | Resemblyzer voiceprint | NumPy spectral fingerprint |
| Text-to-speech | Edge-TTS `en-GB-RyanNeural` | pyttsx3 |

The voiceprint is stored at `data/voiceprint.npy`. Delete it or use
`DELETE /api/voice` to forget it. While unenrolled, JARVIS still replies but warns
that the lock is open; once enrolled, unverified voices are refused.

Tuning lives in `.env`:

```ini
VOICE_LOCK_ENABLED=true
VOICE_MATCH_THRESHOLD=0.78
WAKE_THRESHOLD=0.55
MIC_DEVICE=13          # optional sounddevice index; see the HUD's mic list
TTS_ENGINE=edge
```

## Architecture

```text
start.py ──► FastAPI (backend/main.py) ──► WebSocket /ws ──► React HUD
                    │
                    ├── JarvisAgent (backend/agent.py)
                    │     ├── fast regex intents (instant)
                    │     ├── Brain.parse_intent → strict JSON tool call
                    │     └── safety: confirmation + speaker lock
                    ├── VoiceEngine (wake → STT → verify → TTS)
                    ├── SQLite (backend/db.py)
                    └── Skills (backend/skills/)
                          system_control · files · browser · phone
                          email_skill · news · finance · info · updater
                          tasks · planner · vision · hardware · home
                          research · security
```

- **Two-speed routing:** deterministic regex for common commands (~milliseconds),
  local LLM JSON routing for everything else.
- **Confirmation gate:** shutdown, restart, delete, recycle bin, sleep/hibernate
  require an explicit “yes” within 25 seconds.
- **Local-first:** Ollama by default; Gemini/OpenAI/Claude are used only if a real
  key is present in `.env`.

## Keys and accounts

Everything below is optional; JARVIS runs fully local without it.

| Feature | Setting |
| --- | --- |
| Cloud brain | `GEMINI_API_KEY` / `OPENAI_API_KEY` / `CLAUDE_API_KEY` |
| Email (any number of accounts) | `MAIL_<LABEL>_ADDRESS` + `MAIL_<LABEL>_PASSWORD` |
| Better TTS | `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `TTS_ENGINE=elevenlabs` |
| Location | `DEFAULT_CITY` (Open-Meteo is keyless) |

### Linking mail accounts

Use the local linker; it hides the password, tests IMAP + SMTP, and writes only
to the git-ignored `.env`:

```bash
python tools/link_email.py            # add/update one account
python tools/link_email.py --list     # show linked labels
python tools/link_email.py --test     # verify logins without sending mail
```

Add `personal`, `college`, `work` — any label. The label is spoken:

- *"Read my college email"*
- *"Send an email from personal to Ravi about lunch"*
- *"Which email accounts are linked?"*
- *"Sync my email contacts"* (imports inbox senders into `data/jarvis.db`)

Hosts are inferred from the domain (`smtp.gmail.com`, `smtp.office365.com`,
`smtp.mail.yahoo.com`, `smtp.mail.me.com`, `smtp.zoho.com`, otherwise
`smtp.<college-domain>`). If your college uses unusual servers, add the
`MAIL_<LABEL>_SMTP_HOST/PORT/SSL` and `MAIL_<LABEL>_IMAP_HOST/PORT` overrides.

**App passwords, not normal passwords**

| Provider | Where |
| --- | --- |
| Gmail / Google Workspace (college) | `myaccount.google.com/apppasswords` (2-Step Verification on) |
| Outlook / Microsoft 365 (college) | `account.microsoft.com/security` → App passwords, or ask IT |
| Yahoo | `account.yahoo.com` → Security → App passwords |
| iCloud | `appleid.apple.com` → App-specific passwords |

Gmail and Microsoft refuse plain passwords from third-party apps, so an app
password is required. The HUD shows each linked account as `Mail · <label>`
with `ready` or `incomplete` in the Vitals panel, and
`GET /api/email/accounts` returns the same state.

API keys are issued by each provider after you sign in; JARVIS cannot create
them. Run `python tools/collect_keys.py` (or `python setup.py`) and paste each
one at the hidden prompt; it is stored only in the git-ignored `.env`.

## Browser automation

- Dedicated Chrome profile: `%LOCALAPPDATA%\JARVIS\chrome-profile` (outside OneDrive).
- First WhatsApp use shows a QR code — scan it once.
- Instagram: log in once in the same profile.
- If the automation profile is already open in a normal Chrome window, close it first.

Phone Link has no public API. JARVIS drives its UI through Windows UI Automation:
it opens the app, searches for the contact, clicks Call, then exposes hang-up, mute,
and call volume. Run `POST /api/phone/diagnose` if a button cannot be found; it writes
the full control tree to `data/phone_link_tree.txt`.

## Plans and agenda

JARVIS can break a goal into a short, validated sequence of safe actions and execute
it step by step, streaming progress to the HUD's **Execution plan** panel and
persisting each run to SQLite.

```text
"Prepare my laptop for development"   → usage, VS Code, terminal, health
"Start my day"                        → agenda, weather, inbox, headlines
"Run a full diagnostic"               → health, CPU/RAM, GPU, thermals, slowdown
"Organize my downloads"               → sort files into folders
```

Known workflows use deterministic plans; anything else is planned by the local
model, filtered against an allow-list (power, deletion, and financial actions are
never buried inside a plan), capped at 8 steps, and paused for confirmation when a
step sends a message or email. Say **"stop"** to halt mid-plan.

Tasks and events live in the same database and feed the agenda panel:

```text
"Add a task to call the bank tomorrow at 5"      (urgent / low priorities understood)
"Remind me to stretch in 30 minutes"
"Add a meeting with Ravi on Friday at 3 pm"
"List my tasks"  ·  "Mark the bank task done"  ·  "What is next?"
"What is on my agenda?"  (falls back to the next upcoming item when today is clear)
```

## Modes, vision, hardware and research

Modes change JARVIS's tone and default behaviour. Switch by voice or from the HUD:

| Mode | Focus |
| --- | --- |
| Normal | Balanced assistant |
| Developer | Code, repos, diagnostics, precise answers |
| Research | Sources, summaries, reports |
| System | Hardware, processes, performance |
| Vision | Screen and camera analysis |
| Security | Terse, cautious, confirms more |
| Autonomous | Plans and executes without step-by-step chatter |

```text
"Enter developer mode"  ·  "Switch to research mode"
"Read my screen"        ·  "What is on my screen?"
"Look at the camera"    ·  "Check my GPU"  ·  "Show temperatures"
"Why is my laptop slow?"  (CPU, RAM, disk, GPU, top processes)
"Deep research quantum batteries"  (markdown report in data/reports/)
"Brief me on the James Webb telescope"
"Turn on the living room lights"  ·  "Set the study lamp to 30 percent"
"Set the thermostat to 24"  ·  "Activate movie scene"  (Home Assistant)
```

Screen OCR uses Windows' built-in engine (`winocr`); screen/camera description uses
Gemini when `GEMINI_API_KEY` is set. Home Assistant needs `HASS_URL` and
`HASS_TOKEN`. Deep research fetches public pages, fences the text as untrusted data,
and rejects prompt-injection patterns.

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| WS | `/ws` | transcripts, voice state, news, toasts |
| POST | `/api/command` | run a command, returns the spoken reply |
| GET | `/api/status` | brain, voice, health, stats, mode, safety |
| GET | `/system-stats` | CPU / RAM / battery / disk / network |
| GET | `/api/agenda` | today's events, tasks, reminders + upcoming |
| POST | `/api/tasks` | add a task (`{title, when}`) |
| GET | `/api/plans` | recent multi-step plan runs |
| GET/POST | `/api/mode` | read or set the operating mode |
| POST | `/api/privacy` | privacy mode (blocks mic, camera, screen) |
| POST | `/api/stop`, `/api/resume` | emergency stop / resume |
| GET | `/api/vitals` | GPU, thermals, battery, charging |
| GET | `/api/vision/screen`, `/api/vision/text`, `/api/vision/camera` | vision |
| POST | `/api/research` | deep-research report (`{topic, depth}`) |
| GET | `/api/home` | Home Assistant status summary |
| GET/POST | `/api/money`, `/api/money/expense`, `/api/money/budget` | ledger |
| GET/POST | `/api/contacts` | contact book |
| GET/POST/DELETE | `/api/voice` | status / enroll / forget |
| GET | `/api/news?category=technology` | headlines |
| POST | `/api/phone/diagnose` | Phone Link control tree |
| GET | `/api/email/accounts` | linked mail labels and readiness |
| POST | `/api/email/test` | verify IMAP/SMTP logins |
| POST | `/api/email/sync-contacts` | import inbox senders as contacts |
| GET | `/api/updates` | dependency update check |

Interactive docs: `http://127.0.0.1:8000/docs`.

## Configuration reference

See `.env.example` for every key. Common ones:

```ini
USER_NAME=Sir
DEFAULT_CITY=Vijayawada
BRAIN_PROVIDER=auto
OLLAMA_MODEL=qwen3.5:4b
TTS_VOICE=en-GB-RyanNeural
DEFAULT_MODE=normal         # normal | developer | research | system | vision | security | autonomous
PRIVACY_ON_START=false      # true boots with mic, camera and screen disabled
HASS_URL=                   # e.g. http://homeassistant.local:8123
HASS_TOKEN=                 # long-lived access token
ALLOW_POWER_ACTIONS=true   # false disables shutdown/restart/sleep
ALLOW_FILE_DELETE=true     # deletes go to the Recycle Bin
ALLOW_SHELL=false          # no arbitrary shell execution
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| HUD says **NO LINK** | Backend not running; run `python start.py` |
| “Ollama is not reachable” | `ollama serve`, then check `OLLAMA_MODEL` |
| No wake word | `WAKE_ENGINE=whisper` in `.env`, or check the mic index in the HUD |
| Voice rejected | Re-enrol in a quiet room; lower `VOICE_MATCH_THRESHOLD` slightly |
| WhatsApp QR every time | Profile folder deleted or Chrome already using that profile |
| Phone Link button missing | Run the diagnose endpoint and inspect `data/phone_link_tree.txt` |
| Email does nothing | Run `python tools/link_email.py`; Gmail/Outlook need an app password |
| PowerShell `pip` hangs | Use `python -m pip` or `uv pip install -r requirements.txt` |

Logs: `logs/jarvis.log`. Data: `data/jarvis.db`, `data/voiceprint.npy`.

## Safety

- The server binds to `127.0.0.1` only.
- Power actions and deletions require spoken/typed confirmation.
- File deletions go to the Recycle Bin via `send2trash`.
- Arbitrary shell commands are disabled unless `ALLOW_SHELL=true`.
- Voice commands are refused when the speaker does not match the enrolled print.
- Plans may only contain allow-listed steps; messages and emails inside a plan ask
  for confirmation first.
- **STOP ALL** / `POST /api/stop` halts plans and command execution immediately;
  **RESUME** restores normal operation.
- Privacy mode stops the microphone loop and refuses screen and camera access.
- Fetched web text is fenced as untrusted data and checked for prompt injection.

## License

Personal project. Use at your own risk; automation of third-party sites can break
when their UI changes.
