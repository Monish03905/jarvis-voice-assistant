import React, { useEffect, useState } from 'react';

function VoiceEnroll({ api = '', onClose, onDone }) {
  const [phase, setPhase] = useState('ready');
  const [seconds, setSeconds] = useState(12);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (phase !== 'recording') return undefined;
    const timer = setInterval(() => {
      setSeconds((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [phase]);

  const begin = async () => {
    setPhase('recording');
    setSeconds(12);
    try {
      const res = await fetch(`${api}/api/voice/enroll`, { method: 'POST' });
      const data = await res.json();
      setResult(data);
      setPhase('done');
    } catch {
      setResult({ ok: false, error: 'Backend unreachable' });
      setPhase('done');
    }
  };

  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-label="Voice enrollment">
      <div className="modal">
        <header className="modal-head">
          <h2>Voiceprint enrollment</h2>
          <button className="muted" onClick={onClose} aria-label="Close">✕</button>
        </header>

        {phase === 'ready' && (
          <>
            <p className="modal-copy">
              I will listen for twelve seconds. Read this aloud at a normal pace, using
              the microphone you normally speak into.
            </p>
            <blockquote className="script">
              “The quick brown fox jumps over the lazy dog. JARVIS, open the workshop
              shutters, dim the lights, and tell me the weather for tomorrow morning.”
            </blockquote>
            <button className="primary-btn" onClick={begin}>Begin enrollment</button>
          </>
        )}

        {phase === 'recording' && (
          <div className="recording">
            <div className="rec-dot" />
            <div className="count">{seconds}</div>
            <p>Recording — keep speaking naturally.</p>
          </div>
        )}

        {phase === 'done' && (
          <div className="modal-result">
            {result?.ok ? (
              <>
                <h3 className="ok">Voiceprint stored</h3>
                <p>
                  Quality score {(result.score ?? 0).toFixed(2)} · engine {result.mode || 'default'}.
                  From now on I will only act on your verified voice.
                </p>
              </>
            ) : (
              <>
                <h3 className="bad">Enrollment failed</h3>
                <p>{result?.error || 'No usable speech was captured. Check the mic and try again.'}</p>
              </>
            )}
            <button className="primary-btn" onClick={() => onDone?.(result)}>Done</button>
          </div>
        )}
      </div>
    </div>
  );
}

export default VoiceEnroll;
