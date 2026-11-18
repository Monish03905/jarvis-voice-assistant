import React from 'react';

function ModeBar({ modes = [], mode = 'normal', safety = {}, onChange, onPrivacy, onStop, onResume }) {
  const halted = Boolean(safety.halted);
  const privacy = Boolean(safety.privacy);

  return (
    <section className={`panel mode-panel ${halted ? 'halted' : ''}`}>
      <header className="panel-head">
        <h2>Interface</h2>
        <span className="tag">{mode}</span>
      </header>

      <div className="mode-grid">
        {modes.map((item) => (
          <button
            key={item.id}
            type="button"
            title={item.hint}
            className={item.id === mode ? 'active' : ''}
            onClick={() => onChange(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="safety-row">
        <button
          type="button"
          className={`safety ${privacy ? 'on' : ''}`}
          onClick={() => onPrivacy(!privacy)}
          title="Privacy mode stops the microphone and camera"
        >
          {privacy ? 'PRIVACY ON' : 'PRIVACY OFF'}
        </button>
        {halted ? (
          <button type="button" className="danger" onClick={onResume}>RESUME</button>
        ) : (
          <button type="button" className="danger" onClick={onStop}>STOP ALL</button>
        )}
      </div>
    </section>
  );
}

export default ModeBar;
