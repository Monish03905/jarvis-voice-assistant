import React, { useEffect, useRef } from 'react';

function stamp(iso) {
  const date = iso ? new Date(iso) : new Date();
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function Transcript({ messages = [] }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages]);

  return (
    <section className="panel transcript-panel">
      <header className="panel-head">
        <h2>Comms log</h2>
        <span className="tag">{messages.length}</span>
      </header>

      <div className="transcript">
        {messages.length === 0 && (
          <div className="empty">
            <span className="empty-glyph">◍</span>
            <p>Say “Hey Jarvis” or type a command. I will keep the log here.</p>
          </div>
        )}
        {messages.map((m) => (
          <article key={m.id} className={`msg ${m.speaker === 'user' ? 'from-user' : 'from-jarvis'}`}>
            <div className="msg-meta">
              <span className="who">{m.speaker === 'user' ? 'YOU' : 'JARVIS'}</span>
              <span className="when">{stamp(m.time)}</span>
            </div>
            <p>{m.message}</p>
          </article>
        ))}
        <div ref={endRef} />
      </div>
    </section>
  );
}

export default Transcript;
