import React from 'react';

const ACTIVE = new Set(['LISTENING', 'HEARD', 'PROCESSING', 'VERIFYING', 'THINKING', 'SPEAKING', 'WORKING']);

function Waveform({ state = 'IDLE' }) {
  const active = ACTIVE.has(state);
  return (
    <div
      className={`waveform ${active ? 'active' : ''} wave-${state.toLowerCase()}`}
      aria-hidden="true"
    >
      {Array.from({ length: 36 }).map((_, index) => (
        <span key={index} style={{ animationDelay: `${(index % 9) * 0.07}s` }} />
      ))}
    </div>
  );
}

export default Waveform;
