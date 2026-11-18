# 🚀 JARVIS Quick Start Guide

Get JARVIS up and running in 5 minutes!

## ⚡ Super Quick Start (TL;DR)

```bash
# 1. Setup environment
python setup.py

# 2. Configure API keys
# Edit .env file with your API keys

# 3. Install dependencies
python -m venv venv
venv\Scripts\activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 4. Launch JARVIS
python start.py

# 5. Open browser to http://localhost:3000
```

---

## 📋 Prerequisites

- **Python 3.9 or higher**
  - Check: `python --version`
  - Download: https://www.python.org/downloads/

- **Node.js 14+ and npm**
  - Check: `node --version` and `npm --version`
  - Download: https://nodejs.org/

- **Internet connection** (for API calls)

- **Microphone** (for voice commands)

---

## 🔑 Step 1: Get API Keys

Choose at least ONE AI provider:

### Option A: Claude (Recommended) ⭐
1. Go to https://console.anthropic.com
2. Sign up or log in
3. Create an API key
4. Copy the key (starts with `sk-ant-`)

### Option B: OpenAI
1. Go to https://platform.openai.com/api/keys
2. Sign up or log in
3. Create an API key
4. Copy the key (starts with `sk-`)

### Optional: Better Voice (ElevenLabs)
1. Go to https://www.elevenlabs.io
2. Sign up for free
3. Get your API key from the account settings
4. Optional: Train a custom voice or use the free British male voice

### Optional: Weather & News
- Weather: https://openweathermap.org/api (free tier available)
- News: https://newsapi.org (free tier available)

---

## 🛠️ Step 2: Setup Environment

### Windows
```bash
# Navigate to project directory
cd C:\Users\YOUR_USER\OneDrive\Desktop\JARVIS

# Run setup wizard (recommended)
python setup.py

# Or manually:
# Copy .env.example to .env
copy .env.example .env

# Edit .env and add your API keys
notepad .env
```

### macOS/Linux
```bash
# Navigate to project directory
cd ~/Desktop/JARVIS  # or wherever you cloned it

# Run setup wizard
python setup.py

# Or manually:
cp .env.example .env
nano .env  # or vim, or your favorite editor
```

### Edit .env File
Replace the placeholder values with your API keys:

```env
# Add your Claude API key (RECOMMENDED)
CLAUDE_API_KEY=sk-ant-your-actual-key-here

# OR add your OpenAI API key
OPENAI_API_KEY=sk-your-actual-key-here

# Optional: Add ElevenLabs for better voice
ELEVENLABS_API_KEY=sk_your-actual-key-here

# Optional: Weather and News
WEATHER_API_KEY=your-openweather-key
NEWS_API_KEY=your-newsapi-key

# Customize (optional)
USER_NAME=Mr. Stark
WAKE_WORD=hey jarvis
```

---

## 📦 Step 3: Install Dependencies

### Create Virtual Environment (Recommended)

#### Windows
```bash
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
```

#### macOS/Linux
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### Install Python Packages
```bash
pip install -r requirements.txt
```

This installs:
- FastAPI (backend framework)
- Uvicorn (server)
- OpenAI Whisper (speech recognition)
- ElevenLabs (text-to-speech)
- Claude/OpenAI APIs
- And many more...

**Note:** If you get errors with PyAudio, see [Troubleshooting](#troubleshooting)

### Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

---

## ▶️ Step 4: Start JARVIS

### One-Command Start (Recommended)
```bash
python start.py
```

This will:
1. ✅ Validate configuration
2. ✅ Start the FastAPI backend on `http://localhost:8000`
3. ✅ Start the React frontend on `http://localhost:3000`
4. ✅ Automatically open the HUD in your browser

### Manual Start (If you want separate terminals)

**Terminal 1 - Backend:**
```bash
cd backend
python -m uvicorn main:app --reload
# or: python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm start
```

---

## 🎙️ Step 5: Using JARVIS

### Voice Commands
1. **Click the microphone button** in the bottom-right of the HUD
2. **Say the wake word**: "Hey JARVIS" or just "JARVIS"
3. **Give a command**:
   - "What's the weather?"
   - "Open Chrome"
   - "Send an email to john@example.com"
   - "What time is it?"
   - "Set volume to 50"

### Example Commands

```
Weather & News:
  "What's the weather in New York?"
  "Tell me the latest news"
  "What's the date?"

System Control:
  "Open Chrome"
  "Close Firefox"
  "Shut down the computer"
  "Restart"
  "Lock the screen"

File Management:
  "Create a file called notes"
  "Read the readme file"
  "Delete desktop.txt"

Email:
  "Send an email to john@example.com"
  "Check my emails"

Fun:
  "Tell me a joke"
  "Play some music"
  "What's your name?"
  "Threat assessment"
```

### Keyboard Shortcuts
- `F11` - Toggle fullscreen mode
- `Ctrl+C` - Stop JARVIS (in terminal)
- `Space` - Voice toggle (when HUD is focused)

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'X'"
**Solution:** Make sure you installed dependencies:
```bash
pip install -r requirements.txt
```

### "Connection refused" on localhost:8000
**Solution:** Wait 5-10 seconds for backend to start. Check the terminal for errors.

### Microphone not working
**Solution:**
1. Check microphone permissions in your OS
2. Test microphone: `python -c "import speech_recognition; print('OK')"`
3. Install PyAudio properly:
   ```bash
   pip install --upgrade pyaudio
   ```

### "PyAudio not found"
**Windows:**
```bash
pip install pipwin
pipwin install pyaudio
```

**macOS:**
```bash
brew install portaudio
pip install pyaudio
```

**Linux:**
```bash
sudo apt-get install portaudio19-dev
pip install pyaudio
```

### .env file not loading
**Solution:**
1. Ensure `.env` is in the project root directory
2. Make sure it has the right format: `KEY=value`
3. Don't use quotes: `KEY=value` ✅ not `KEY="value"` ❌

### API Key errors
**Solution:**
1. Double-check your API keys in `.env` file
2. Ensure you copied the full key (including `sk-` prefix)
3. Make sure the API key is active (not revoked/expired)
4. For Claude: https://console.anthropic.com/account/keys
5. For OpenAI: https://platform.openai.com/api/keys

### Frontend won't start
**Solution:**
```bash
cd frontend
npm cache clean --force
npm install
npm start
```

### "Port 3000 already in use"
**Solution:**
```bash
# Kill the process on port 3000
# Windows:
netstat -ano | findstr :3000
taskkill /PID {PID} /F

# macOS/Linux:
lsof -ti:3000 | xargs kill -9
```

### Whisper takes forever to load
**Solution:** Whisper downloads a model on first run (~140MB). Be patient or:
```bash
# Pre-download the model
python -c "import whisper; whisper.load_model('base')"
```

---

## 🎯 Next Steps

1. **Customize JARVIS Personality**
   - Edit `config.py` and modify `JARVIS_SYSTEM_PROMPT`

2. **Change HUD Colors**
   - Edit `frontend/src/App.css` and replace `#00ffff` with your color

3. **Add Custom Skills**
   - Create new files in `backend/skills/`
   - Register in `backend/main.py`

4. **Home Assistant Integration**
   - Set `HOME_ASSISTANT_URL` and `HOME_ASSISTANT_TOKEN` in `.env`

5. **Deploy to Cloud**
   - See README.md for deployment options

---

## 📚 More Information

- Full documentation: See [README.md](README.md)
- Architecture details: See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)
- Contributing: See [CONTRIBUTING.md](CONTRIBUTING.md)

---

## ✨ You're All Set!

**Open http://localhost:3000 and enjoy your new AI assistant!**

---

## 🎓 Learning Resources

### Python
- FastAPI: https://fastapi.tiangolo.com/
- Uvicorn: https://www.uvicorn.org/

### Frontend
- React: https://react.dev/
- Framer Motion: https://www.framer.com/motion/

### AI
- Claude API: https://docs.anthropic.com
- OpenAI API: https://platform.openai.com/docs
- Whisper: https://github.com/openai/whisper

### Voice
- ElevenLabs: https://elevenlabs.io/docs
- pyttsx3: https://pyttsx3.readthedocs.io/

---

**"Thank you for installing JARVIS. It's been a pleasure."** 🤖✨
