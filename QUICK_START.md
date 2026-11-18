# JARVIS Quick Start

A short path from clone to a running HUD. For the full feature guide, see [README.md](README.md).

## 1. Prerequisites

- Windows 10/11
- Python 3.10+ (3.11 recommended)
- Chrome
- A microphone for voice control
- [Ollama](https://ollama.com) with:

```powershell
ollama pull qwen3.5:4b
ollama pull qwen3:0.6b
```

## 2. Clone and install

```powershell
git clone https://github.com/Monish03905/jarvis-voice-assistant.git JARVIS
cd JARVIS

python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Configure

```powershell
copy .env.example .env
```

Edit `.env` for at least:

```ini
USER_NAME=Sir
DEFAULT_CITY=Vijayawada
BRAIN_PROVIDER=auto
OLLAMA_MODEL=qwen3.5:4b
```

Everything else is optional. Keep `.env` private; it is git-ignored.

## 4. First-run wizard

```powershell
python setup.py
```

The wizard checks dependencies, offers model setup, enrols your voice (12 seconds of speech), can link email accounts and API keys, and warms up the WhatsApp/Instagram browser profile.

## 5. Start

```powershell
python start.py
```

The HUD opens at `http://127.0.0.1:8000`. The production HUD is prebuilt in `frontend/build`.

Launcher flags:

```powershell
python start.py --port 8080
python start.py --no-browser
python start.py --no-voice
```

## 6. Verify without a microphone

```powershell
python start.py --no-voice
```

In a second terminal:

```powershell
curl http://127.0.0.1:8000/api/status
```

Open `http://127.0.0.1:8000/docs` to exercise every skill over HTTP, and use the HUD's command bar for text commands.

## 7. Try these commands

```text
"What is on my agenda?"
"Run a full diagnostic"
"Prepare my laptop for development"
"Open downloads folder"
"Read my screen"
"World news"
"How much did I spend this month?"
"Add a task to call the bank tomorrow at 5"
```

Voice: say **"Hey Jarvis"**, wait for *"Yes?"*, then speak.

## 8. Optional integrations

| Feature | Setup |
| --- | --- |
| Personal/college email | `python tools/link_email.py` (use app passwords) |
| Cloud model fallback | `python tools/collect_keys.py` (Gemini/OpenAI/Claude) |
| Screen/camera description | `GEMINI_API_KEY` |
| Home Assistant | `HASS_URL` + `HASS_TOKEN` |
| Phone calls | Sign in to Microsoft Phone Link |
| WhatsApp / Instagram | Scan the QR code once in the automation profile |

## 9. Rebuild the HUD (optional)

```powershell
cd frontend
npm install
npm run build
```

## 10. Run the tests

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| HUD shows **NO LINK** | Backend is not running |
| Ollama unreachable | Run `ollama serve`; check `OLLAMA_MODEL` |
| No wake word | Try `WAKE_ENGINE=whisper`; check the mic index |
| Voice rejected | Re-enrol in a quiet room; adjust `VOICE_MATCH_THRESHOLD` |
| Email fails | Use an app password, not your normal password |
| Port in use | `python start.py --port 8080` |

See [README.md](README.md) for architecture, every endpoint, and the full command cookbook.
