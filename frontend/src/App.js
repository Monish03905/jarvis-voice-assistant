import React, { useCallback, useEffect, useRef, useState } from 'react';
import './App.css';
import ArcReactor from './components/ArcReactor';
import Transcript from './components/Transcript';
import SystemStats from './components/SystemStats';
import NewsTicker from './components/NewsTicker';
import BudgetPanel from './components/BudgetPanel';
import MailPanel from './components/MailPanel';
import CommandBar from './components/CommandBar';
import VoiceEnroll from './components/VoiceEnroll';
import ModeBar from './components/ModeBar';
import AgendaPanel from './components/AgendaPanel';
import PlanPanel from './components/PlanPanel';
import Waveform from './components/Waveform';

const isDev = window.location.port === '3000';
const API = isDev ? 'http://localhost:8000' : '';
const WS_URL = isDev
  ? 'ws://localhost:8000/ws'
  : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;

const STATE_COPY = {
  IDLE: 'Standing by',
  LISTENING: 'Listening for "Hey Jarvis"',
  HEARD: 'Wake word detected',
  PROCESSING: 'Transcribing',
  VERIFYING: 'Checking your voiceprint',
  THINKING: 'Thinking',
  WORKING: 'Executing',
  SPEAKING: 'Speaking',
  OFFLINE: 'Offline',
  ERROR: 'Voice engine error',
};

function App() {
  const [connected, setConnected] = useState(false);
  const [voiceState, setVoiceState] = useState('IDLE');
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState([]);
  const [partial, setPartial] = useState('');
  const [stats, setStats] = useState({});
  const [news, setNews] = useState([]);
  const [money, setMoney] = useState({});
  const [status, setStatus] = useState(null);
  const [voice, setVoice] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [showEnroll, setShowEnroll] = useState(false);
  const [clock, setClock] = useState(new Date());
  const [fullscreen, setFullscreen] = useState(false);
  const [agenda, setAgenda] = useState({});
  const [vitals, setVitals] = useState({});
  const [plan, setPlan] = useState(null);
  const [mode, setMode] = useState('normal');
  const [modes, setModes] = useState([]);
  const [safety, setSafety] = useState({ halted: false, privacy: false });
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  const pushToast = useCallback((message) => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev.slice(-3), { id, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 6000);
  }, []);

  const addMessage = useCallback((speaker, message, timestamp) => {
    setMessages((prev) => {
      if (prev.length && prev[prev.length - 1].message === message &&
          prev[prev.length - 1].speaker === speaker) {
        return prev;
      }
      return [...prev.slice(-60), {
        id: `${Date.now()}-${Math.random()}`,
        speaker,
        message,
        time: timestamp || new Date().toISOString(),
      }];
    });
  }, []);

  const refresh = useCallback(async () => {
    const grab = async (path) => {
      try {
        const res = await fetch(`${API}${path}`);
        return res.ok ? await res.json() : null;
      } catch {
        return null;
      }
    };
    const [statusData, statsData, newsData, moneyData, history, agendaData, vitalsData, plansData] = await Promise.all([
      grab('/api/status'),
      grab('/system-stats'),
      grab('/api/news?category=world&limit=10'),
      grab('/api/money'),
      grab('/api/history?limit=30'),
      grab('/api/agenda'),
      grab('/api/vitals'),
      grab('/api/plans'),
    ]);
    if (statusData) {
      setStatus(statusData);
      if (statusData.mode) setMode(statusData.mode);
      if (statusData.modes) setModes(statusData.modes);
      if (statusData.safety) setSafety(statusData.safety);
    }
    if (statsData) setStats(statsData);
    if (newsData) setNews(newsData.items || []);
    if (moneyData) setMoney(moneyData);
    if (agendaData) setAgenda(agendaData);
    if (vitalsData) setVitals(vitalsData);
    if (plansData?.plans?.length) setPlan(plansData.plans[0]);
    if (history && Array.isArray(history.messages) && history.messages.length) {
      setMessages((prev) => (prev.length ? prev : history.messages.map((m, i) => ({
        id: `h-${i}`,
        speaker: m.role === 'user' ? 'user' : 'jarvis',
        message: m.content,
        time: m.created_at,
      }))));
    }
    const voiceData = await grab('/api/voice');
    if (voiceData) setVoice(voiceData);
  }, []);

  const runCommand = useCallback(async (text) => {
    const command = (text || '').trim();
    if (!command || busy) return '';
    setBusy(true);
    addMessage('user', command);
    try {
      const res = await fetch(`${API}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: command, source: 'ui' }),
      });
      const data = await res.json();
      if (data.reply) addMessage('jarvis', data.reply);
      return data.reply || '';
    } catch (err) {
      pushToast('Backend unreachable. Is JARVIS running?');
      return '';
    } finally {
      setBusy(false);
      setTimeout(refresh, 700);
    }
  }, [busy, addMessage, pushToast, refresh]);

  const postControl = useCallback(async (path, body = {}) => {
    try {
      const response = await fetch(`${API}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (data.message) pushToast(data.message);
      return data;
    } catch {
      pushToast('Backend unreachable.');
      return null;
    }
  }, [pushToast]);

  const changeMode = useCallback(async (next) => {
    const data = await postControl('/api/mode', { mode: next });
    if (data?.mode) setMode(data.mode);
  }, [postControl]);

  const togglePrivacy = useCallback(async (on) => {
    const data = await postControl('/api/privacy', { on });
    if (data) setSafety((prev) => ({ ...prev, privacy: Boolean(data.privacy) }));
  }, [postControl]);

  const emergencyStop = useCallback(async () => {
    const data = await postControl('/api/stop', {});
    if (data?.safety) setSafety(data.safety);
  }, [postControl]);

  const resumeAll = useCallback(async () => {
    const data = await postControl('/api/resume', {});
    if (data?.safety) setSafety(data.safety);
  }, [postControl]);

  // WebSocket
  useEffect(() => {
    let disposed = false;

    const connect = () => {
      if (disposed) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!disposed) reconnectRef.current = setTimeout(connect, 3000);
      };
      ws.onerror = () => setConnected(false);
      ws.onmessage = (event) => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          return;
        }
        switch (data.type) {
          case 'transcript':
            addMessage(data.speaker, data.message);
            setPartial('');
            break;
          case 'partial':
            setPartial(data.text || '');
            break;
          case 'agent':
          case 'voice':
            setVoiceState(data.state || 'IDLE');
            break;
          case 'news':
            setNews(data.items || []);
            break;
          case 'plan':
            setPlan(data.steps && data.steps.length ? data : null);
            if (data.status === 'failed' || data.status === 'stopped') {
              pushToast(`Plan ${data.status}.`);
            }
            break;
          case 'mode':
            if (data.mode) setMode(data.mode);
            break;
          case 'privacy':
            setSafety((prev) => ({ ...prev, privacy: Boolean(data.on) }));
            break;
          case 'halt':
            setSafety((prev) => ({ ...prev, halted: Boolean(data.active) }));
            break;
          case 'toast':
            pushToast(data.message);
            break;
          case 'action':
            if (data.ok === false && data.message) pushToast(data.message);
            break;
          default:
            break;
        }
      };
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(reconnectRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [addMessage, pushToast]);

  // Polling
  useEffect(() => {
    refresh();
    const tick = setInterval(() => {
      fetch(`${API}/system-stats`).then((r) => r.json()).then(setStats).catch(() => {});
    }, 4000);
    const slow = setInterval(refresh, 60000);
    const agendaTick = setInterval(() => {
      fetch(`${API}/api/agenda`).then((r) => r.json()).then(setAgenda).catch(() => {});
    }, 20000);
    const vitalsTick = setInterval(() => {
      fetch(`${API}/api/vitals`).then((r) => r.json()).then(setVitals).catch(() => {});
    }, 15000);
    return () => {
      clearInterval(tick);
      clearInterval(slow);
      clearInterval(agendaTick);
      clearInterval(vitalsTick);
    };
  }, [refresh]);

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  };

  const enrolled = Boolean(voice?.enrolled ?? status?.voice?.enrolled);
  const voiceRunning = Boolean(voice?.running ?? status?.voice?.running);
  const stateLabel = STATE_COPY[voiceState] || voiceState;

  return (
    <div className="app">
      <div className="backdrop" aria-hidden="true">
        <div className="grid" />
        <div className="glow glow-a" />
        <div className="glow glow-b" />
        <div className="scanlines" />
      </div>

      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">J</span>
          <div>
            <h1>J.A.R.V.I.S.</h1>
            <p>{status?.user ? `At your service, ${status.user}` : 'Just A Rather Very Intelligent System'}</p>
          </div>
        </div>

        <div className="topbar-meta">
          <div className={`pill ${connected ? 'ok' : 'bad'}`}>
            <span className="dot" /> {connected ? 'LINK' : 'NO LINK'}
          </div>
          <div className={`pill ${enrolled ? 'ok' : 'warn'}`} title="Speaker verification">
            <span className="dot" /> {enrolled ? 'VOICE LOCKED' : 'ENROLL VOICE'}
          </div>
          <div className={`pill ${voiceRunning ? 'ok' : 'warn'}`} title="Microphone loop">
            <span className="dot" /> MIC {voiceRunning ? 'LIVE' : 'OFF'}
          </div>
          <div className={`pill ${mode === 'normal' ? 'ok' : 'warn'}`} title="Interface mode">
            <span className="dot" /> {mode.toUpperCase()}
          </div>
          {safety.privacy && (
            <div className="pill bad" title="Privacy mode">
              <span className="dot" /> PRIVACY
            </div>
          )}
          {safety.halted && (
            <div className="pill bad" title="Emergency stop engaged">
              <span className="dot" /> HALTED
            </div>
          )}
          <div className="clock">
            <span className="time">{clock.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
            <span className="date">{clock.toLocaleDateString([], { weekday: 'short', day: '2-digit', month: 'short' })}</span>
          </div>
          <button
            className={`ghost-btn ${safety.halted ? 'warn' : 'danger'}`}
            onClick={safety.halted ? resumeAll : emergencyStop}
            title={safety.halted ? 'Resume operations' : 'Emergency stop'}
          >
            {safety.halted ? 'RESUME' : 'STOP'}
          </button>
          <button className="ghost-btn" onClick={toggleFullscreen} title="Toggle fullscreen">
            {fullscreen ? 'EXIT' : 'FULL'}
          </button>
        </div>
      </header>

      <main className="layout">
        <aside className="rail rail-left">
          <ModeBar
            modes={modes}
            mode={mode}
            safety={safety}
            onChange={changeMode}
            onPrivacy={togglePrivacy}
            onStop={emergencyStop}
            onResume={resumeAll}
          />
          <SystemStats stats={stats} health={status?.health} vitals={vitals} />

          <AgendaPanel agenda={agenda} api={API} onAdded={refresh} busy={busy} />

          <section className="panel contacts-panel">
            <header className="panel-head">
              <h2>Quick actions</h2>
              <span className="tag">one click</span>
            </header>
            <div className="quick-grid">
              {[
                ['Agenda', 'what is on my agenda'],
                ['Brief me', 'good morning'],
                ['Screen', 'what is on my screen'],
                ['Diagnose', 'why is my laptop slow'],
                ['Play lofi', 'play lofi beats on youtube'],
                ['News', 'world news'],
              ].map(([label, cmd]) => (
                <button key={cmd} onClick={() => runCommand(cmd)} disabled={busy}>{label}</button>
              ))}
            </div>
          </section>
        </aside>

        <section className="core">
          <ArcReactor state={voiceState} busy={busy} />
          <Waveform state={busy ? 'WORKING' : voiceState} />
          <div className={`state-line state-${voiceState.toLowerCase()}`}>
            <span className="state-dot" />
            {busy ? 'Working' : stateLabel}
          </div>
          {partial && <div className="partial">“{partial}”</div>}

          <CommandBar onSend={runCommand} busy={busy} />

          <div className="core-hints">
            <span>Say <b>“Hey Jarvis”</b> then speak</span>
            <span className="sep">·</span>
            <span>or type a command</span>
            {!enrolled && (
              <>
                <span className="sep">·</span>
                <button className="link-btn" onClick={() => setShowEnroll(true)}>
                  Enroll my voice
                </button>
              </>
            )}
          </div>
        </section>

        <aside className="rail rail-right">
          <PlanPanel plan={plan} />
          <Transcript messages={messages} />
          <MailPanel
            accounts={status?.health?.email?.accounts || []}
            api={API}
            onAsk={runCommand}
            onToast={pushToast}
          />
          <BudgetPanel money={money} onRefresh={refresh} onToast={pushToast} api={API} />
        </aside>
      </main>

      <NewsTicker items={news} onAsk={runCommand} />

      <div className="toasts">
        {toasts.map((toast) => (
          <div className="toast" key={toast.id}>{toast.message}</div>
        ))}
      </div>

      {showEnroll && (
        <VoiceEnroll
          api={API}
          onClose={() => setShowEnroll(false)}
          onDone={(result) => {
            setShowEnroll(false);
            if (result?.ok) {
              pushToast(`Voiceprint saved (${Math.round((result.score || 0) * 100)}% quality).`);
              refresh();
            } else {
              pushToast('Enrollment failed. Check your microphone and try again.');
            }
          }}
        />
      )}
    </div>
  );
}

export default App;
