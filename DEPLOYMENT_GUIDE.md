# 🚀 JARVIS Deployment Guide

## System Successfully Initialized! ✅

Your JARVIS AI Assistant system has been fully built and is ready to deploy.

---

## 📋 What You Have

A complete, production-ready AI assistant system with:

### Backend Components ✅
- **FastAPI Server** - RESTful API with WebSocket support
- **AI Brain** - Claude/OpenAI integration with personality
- **Voice Interface** - Speech recognition + text-to-speech
- **Skills Modules** - System control, search, email, vision
- **Error Handling** - Graceful failure modes and logging

### Frontend Components ✅
- **React Dashboard** - Futuristic Iron Man-style HUD
- **Animations** - Framer Motion transitions and effects
- **Real-time Updates** - WebSocket live data
- **Responsive Design** - Works on different screen sizes
- **Control Interface** - Voice and text input

### Configuration ✅
- **Environment System** - .env file for API keys
- **Setup Wizard** - Interactive initialization (setup.py)
- **Startup Script** - One-command launch (start.py)
- **Documentation** - Comprehensive guides and examples

---

## 🎯 Three Simple Steps to Launch

### Step 1: Configure API Keys (5 minutes)

**Create or edit the `.env` file:**

```bash
# Windows
notepad .env

# macOS/Linux
nano .env
vim .env
```

**Add your API keys:**

```env
# REQUIRED - Choose one AI provider

# Option A: Claude (Recommended)
CLAUDE_API_KEY=sk-ant-your-actual-key-here

# Option B: OpenAI
OPENAI_API_KEY=sk-your-actual-key-here

# OPTIONAL - But recommended for full features
ELEVENLABS_API_KEY=sk_your-actual-key-here
WEATHER_API_KEY=your-openweather-key
NEWS_API_KEY=your-newsapi-key

# OPTIONAL - Customize if desired
USER_NAME=Mr. Stark
WAKE_WORD=hey jarvis
```

**How to get API keys:**
- Claude: https://console.anthropic.com → API Keys
- OpenAI: https://platform.openai.com → API Keys
- ElevenLabs: https://elevenlabs.io → Account → API Key
- Weather: https://openweathermap.org → Sign Up → API Keys
- News: https://newsapi.org → Sign Up → Get Key

### Step 2: Install Dependencies (15 minutes)

```bash
# Navigate to project
cd c:\Users\YOUR_USER\OneDrive\Desktop\JARVIS

# Create Python virtual environment (recommended)
python -m venv venv

# Activate virtual environment
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS/Linux

# Upgrade pip
python -m pip install --upgrade pip

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..

# Verify everything
python -c "import fastapi; import anthropic; print('✅ All good!')"
```

### Step 3: Start JARVIS (1 minute)

```bash
# One command to launch everything
python start.py
```

This will automatically:
- ✅ Start the backend server on http://localhost:8000
- ✅ Start the frontend on http://localhost:3000
- ✅ Open the HUD in your default browser
- ✅ Begin listening for voice commands

---

## 🎙️ Using JARVIS

### Voice Commands

Once JARVIS is running, interact through the HUD:

1. **Click the microphone button** (bottom-right) or say the wake word
2. **Say "Hey JARVIS" or "JARVIS"** to activate listening
3. **Give a command:**

#### Examples by Category

**Information:**
```
"What's the weather?"
"Tell me the latest news"
"What time is it?"
"What's today's date?"
```

**System Control:**
```
"Open Chrome"
"Close Firefox"
"Lock the screen"
"Restart the computer"
"Set volume to 50"
"Increase brightness"
```

**File Management:**
```
"Create a file called notes"
"Delete readme.txt"
"Read the notes file"
"Move file to desktop"
```

**Email:**
```
"Send an email to john@example.com"
"Check my emails"
"Read the latest email"
```

**Fun:**
```
"Tell me a joke"
"What's your name?"
"Threat detection mode"
"Status report"
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `F11` | Toggle fullscreen mode |
| `Ctrl+C` | Stop JARVIS (in terminal) |
| `Space` | Toggle voice listening |

### Web Interface Features

- **System Stats**: Real-time CPU, RAM, disk, battery
- **Arc Reactor**: Animated centerpiece showing system status
- **Radar Scan**: Animated scanning visualization
- **Weather Widget**: Current weather conditions
- **News Widget**: Latest headlines
- **Conversation**: Live chat transcript
- **Status Indicator**: Connection status

---

## 📊 Monitoring JARVIS

### Backend Logs

Watch the backend terminal to see:
- API requests and responses
- Voice recognition results
- AI responses being generated
- Skill execution logs
- Error messages

### Frontend Console

Open browser developer tools (F12) to see:
- WebSocket connections
- API calls
- React component renders
- Console errors or warnings

### System Status Endpoint

Check system health via HTTP:
```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "systems": {
    "brain": true,
    "voice": true,
    "system_skills": true,
    ...
  }
}
```

---

## 🔧 Troubleshooting Guide

### Port Already in Use

If you get "Port 3000/8000 already in use" error:

```bash
# Find process on port
# Windows:
netstat -ano | findstr :3000

# macOS/Linux:
lsof -ti:3000

# Kill the process
# Windows:
taskkill /PID {PID} /F

# macOS/Linux:
kill -9 {PID}
```

### Microphone Not Working

```bash
# Test microphone access
python -c "import speech_recognition as sr; print(sr.Microphone().list_microphone_indexes())"

# Reinstall PyAudio
# Windows:
pip install pipwin
pipwin install pyaudio

# macOS:
brew install portaudio
pip install pyaudio

# Linux:
sudo apt-get install portaudio19-dev
pip install pyaudio
```

### API Key Errors

1. **Check .env file exists in project root**
   ```bash
   # Verify file exists
   # Windows: dir .env
   # Linux/Mac: ls -la .env
   ```

2. **Verify format (no quotes):**
   ```env
   CORRECT:    CLAUDE_API_KEY=sk-ant-xxxxx
   INCORRECT:  CLAUDE_API_KEY="sk-ant-xxxxx"
   ```

3. **Verify key is active** on provider's website

4. **Restart JARVIS** after editing .env

### Backend Won't Start

```bash
# Check Python version
python --version  # Should be 3.9+

# Verify dependencies installed
pip list | grep fastapi

# Try manual backend start
cd backend
python -m uvicorn main:app --reload

# Check for port conflicts
netstat -tuln | grep 8000
```

### Frontend Won't Load

```bash
# Clear npm cache
cd frontend
npm cache clean --force

# Reinstall dependencies
npm install

# Try starting again
npm start

# Check Node version
node --version  # Should be 14+
```

---

## 🎨 Customization

### Change JARVIS Personality

Edit `config.py`:

```python
JARVIS_SYSTEM_PROMPT = """You are JARVIS, a witty and sophisticated AI...
[Modify this to customize personality]
"""
```

### Customize HUD Colors

Edit `frontend/src/App.css`:

```css
/* Change from cyan to your color */
.neon-glow {
    color: #00ffff;  /* Change to #ff00ff, #00ff00, etc */
}
```

### Change Wake Word

Edit `.env`:

```env
WAKE_WORD=hey jarvis      # Default
WAKE_WORD=hey iron man    # Custom
WAKE_WORD=jarvis          # Just one word
```

### Add Custom Skills

1. Create new file: `backend/skills/custom_skill.py`
2. Define class with `async execute()` method
3. Register in `backend/main.py`
4. Update intent routing in brain

---

## 📈 Performance Tips

### Optimize for Speed

1. **Use smaller AI model:**
   ```env
   AI_MODEL=gpt-3.5-turbo  # Faster but less capable
   ```

2. **Reduce voice quality for speed:**
   ```env
   STT_ENGINE=speech_recognition  # Faster than whisper
   ```

3. **Use local TTS:**
   ```env
   TTS_ENGINE=pyttsx3  # Local, no API calls
   ```

### Monitor Resource Usage

```bash
# Check running processes
# Windows
tasklist | findstr python

# macOS/Linux
ps aux | grep python
```

### Optimize GPU Usage

If you have a GPU and want to use it:

```bash
# Install GPU-accelerated packages
pip install torch torchvision torchaudio
```

---

## 🔒 Security Best Practices

### ✅ Do This
- ✅ Keep .env file secure (in .gitignore)
- ✅ Use environment variables for secrets
- ✅ Regenerate API keys if accidentally exposed
- ✅ Run only on trusted networks initially
- ✅ Keep dependencies updated

### ❌ Don't Do This
- ❌ Commit .env to version control
- ❌ Share API keys publicly
- ❌ Run on untrusted networks
- ❌ Use weak/default credentials
- ❌ Disable security warnings

---

## 📱 Advanced Deployment

### Local Network Access

Make JARVIS accessible from other devices:

Edit `backend/main.py`:
```python
# Change from 0.0.0.0 to your machine IP
if __name__ == "__main__":
    uvicorn.run(app, host="192.168.1.100", port=8000)
```

### Docker Deployment

Create `Dockerfile`:
```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "start.py"]
```

### Cloud Deployment

For production deployment (AWS, Azure, Google Cloud):
1. Use managed databases instead of local storage
2. Enable HTTPS with SSL certificates
3. Use container orchestration (Kubernetes)
4. Set up monitoring and alerting
5. Configure auto-scaling

---

## 📞 Support & Resources

### Official Documentation
- FastAPI: https://fastapi.tiangolo.com/
- React: https://react.dev/
- OpenAI: https://platform.openai.com/docs/
- Anthropic: https://docs.anthropic.com/
- ElevenLabs: https://elevenlabs.io/docs/

### Community
- FastAPI GitHub: https://github.com/tiangolo/fastapi
- React GitHub: https://github.com/facebook/react
- Stack Overflow: Search "JARVIS" or specific errors

---

## ✨ Success Checklist

After launching JARVIS, verify:

- [ ] Backend running on http://localhost:8000
- [ ] Frontend loading on http://localhost:3000
- [ ] HUD displays with animations
- [ ] Microphone button responds
- [ ] Wake word triggers listening
- [ ] Voice commands are recognized
- [ ] JARVIS responds with voice
- [ ] System stats update in real-time
- [ ] Weather widget shows data
- [ ] News widget displays headlines

---

## 🎉 Congratulations!

Your JARVIS AI Assistant is now fully deployed and operational!

### What's Next?

1. **Explore**: Test various voice commands
2. **Customize**: Adjust personality and appearance
3. **Integrate**: Add home automation or other services
4. **Share**: Show your friends your new AI assistant
5. **Extend**: Create custom skills as needed

---

## 📝 Common Commands Reference

```bash
# Start JARVIS
python start.py

# Just backend
cd backend && python -m uvicorn main:app --reload

# Just frontend
cd frontend && npm start

# Run setup wizard
python setup.py

# Check health
curl http://localhost:8000/health

# Send test command
curl -X POST http://localhost:8000/command \
  -H "Content-Type: application/json" \
  -d '{"command": "What time is it?"}'

# Stop backend (Ctrl+C in terminal)
# Stop frontend (Ctrl+C in terminal)
```

---

## 📄 Documentation

- **README.md** - Full user guide
- **QUICK_START.md** - 5-minute setup
- **INSTALLATION_SUMMARY.md** - What was built
- **This file** - Deployment and usage guide

---

**Ready to use your JARVIS assistant?**

Run: `python start.py`

Then visit: `http://localhost:3000`

*"Thank you for using JARVIS. It's been a pleasure."* 🤖✨

---

**System Status**: ✅ Production Ready
**Version**: 1.0.0
**Last Updated**: May 2026
