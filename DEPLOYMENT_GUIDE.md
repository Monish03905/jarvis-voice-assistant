# JARVIS Deployment and Operations Guide

JARVIS is a single-user, local-first desktop application. It is designed to run on the same Windows machine it controls, bound to `127.0.0.1`. This guide covers running it reliably, keeping data safe, and understanding its security boundary.

For installation, see [QUICK_START.md](QUICK_START.md) or [README.md](README.md).

## Deployment model

```text
Windows desktop
  ├─ Ollama                     127.0.0.1:11434
  ├─ JARVIS (FastAPI + HUD)     127.0.0.1:8000
  ├─ SQLite                     data/jarvis.db
  ├─ Chrome automation profile  %LOCALAPPDATA%\JARVIS\chrome-profile
  └─ Optional: Phone Link, Home Assistant, mail accounts
```

- One process serves both the API and the prebuilt React HUD.
- The server has no authentication because it only listens on loopback. Do not bind it to `0.0.0.0` without adding an authenticated reverse proxy.
- No cloud service is required. Cloud model keys are optional fallbacks.

## Start and stop

```powershell
python start.py                 # default port 8000, opens the HUD
python start.py --port 8080
python start.py --no-browser
python start.py --no-voice
```

Stop with `Ctrl+C`. If the port is occupied, JARVIS exits with a clear message rather than starting a second instance.

## Run at sign-in with Task Scheduler

1. Open **Task Scheduler** → **Create Task**.
2. General: run only when the user is logged on.
3. Triggers: **At log on**.
4. Actions: start a program.
   - Program: `C:\path\to\JARVIS\.venv\Scripts\pythonw.exe`
   - Arguments: `C:\path\to\JARVIS\start.py --no-browser`
   - Start in: `C:\path\to\JARVIS`
5. Disable "Stop the task if it runs longer than" under Settings.

`pythonw.exe` avoids a console window. Logs still go to `logs/jarvis.log`.

## Run as a Windows service with NSSM (optional)

```powershell
nssm install JARVIS "C:\path\to\JARVIS\.venv\Scripts\python.exe" "C:\path\to\JARVIS\start.py" "--no-browser"
nssm set JARVIS AppDirectory "C:\path\to\JARVIS"
nssm set JARVIS AppStdout "C:\path\to\JARVIS\logs\service.out.log"
nssm set JARVIS AppStderr "C:\path\to\JARVIS\logs\service.err.log"
nssm start JARVIS
```

A service runs without an interactive desktop, so window control, Phone Link UI Automation, and browser automation may be limited. Prefer Task Scheduler for full desktop control.

## Health checks

```powershell
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/system-stats
curl http://127.0.0.1:8000/api/vitals
```

A healthy response includes `brain.online: true`, a voice block, health flags, and the current mode. The HUD's top bar shows **LINK** when the WebSocket is connected.

## Data and backups

| Path | Contents | Back up |
| --- | --- | --- |
| `data/jarvis.db` | conversations, tasks, events, plans, contacts, budgets, memories | Yes |
| `data/voiceprint.npy` | your speaker embedding | Yes, if you want to avoid re-enrolment |
| `data/reports/` | generated research reports | Optional |
| `data/screenshots/` | screen captures used by vision | No |
| `.env` | credentials and preferences | Yes, securely |
| `logs/` | runtime logs | No |

SQLite runs in WAL mode. To take a consistent backup while JARVIS is running, use:

```powershell
sqlite3 data\jarvis.db ".backup 'data\jarvis-backup.db'"
```

Or stop JARVIS and copy the database file. Never commit `.env`, `data/`, or `logs/` to Git.

## Updating

```powershell
git pull
.venv\Scripts\activate
python -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..
python start.py
```

The HUD build is committed, so `npm` is only needed when frontend sources change. Check `/api/updates` or say *"check for updates"* for dependency status.

## Security boundary

- The API trusts any local process that can reach `127.0.0.1:8000`; do not expose the port.
- Destructive actions require a confirmation with a 25-second TTL.
- Plans are restricted to an allow-list and confirm before sending messages or email.
- Emergency stop halts plans and command execution; privacy mode disables microphone, screen, and camera.
- Keep `ALLOW_SHELL=false` unless you specifically need arbitrary shell commands.
- Use app passwords for email and a long-lived Home Assistant token scoped to the entities you need.
- Review `logs/jarvis.log` if a command behaves unexpectedly.

## If you need remote access

Do not port-forward the app. Put an authenticated reverse proxy in front of it and terminate TLS there, for example Caddy:

```caddyfile
jarvis.example.com {
    reverse_proxy 127.0.0.1:8000
    basic_auth {
        admin $2a$14$replace_with_a_real_hash
    }
}
```

Even then, voice, Phone Link, and desktop automation only make sense on the machine itself. Remote access is best limited to the read-only status and agenda endpoints.
