import React from 'react';

const STATIC_TICKS = Array.from({ length: 72 }, (_, i) => i * 5);

function ArcReactor({ state = 'IDLE', busy = false }) {
  const active = busy || ['SPEAKING', 'THINKING', 'WORKING', 'PROCESSING'].includes(state);
  const listening = state === 'LISTENING' || state === 'HEARD' || state === 'VERIFYING';

  return (
    <div className={`reactor ${active ? 'is-active' : ''} ${listening ? 'is-listening' : ''}`}>
      <svg viewBox="0 0 400 400" className="reactor-svg" role="img" aria-label="JARVIS core">
        <defs>
          <radialGradient id="coreGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#eaffff" stopOpacity="0.95" />
            <stop offset="35%" stopColor="#38f5ff" stopOpacity="0.85" />
            <stop offset="70%" stopColor="#0a7f9c" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#03161d" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#8ffcff" />
            <stop offset="55%" stopColor="#1bc8e8" />
            <stop offset="100%" stopColor="#0b4657" />
          </linearGradient>
        </defs>

        <circle cx="200" cy="200" r="190" className="halo" />
        <circle cx="200" cy="200" r="168" className="ring thin slow" />
        <circle cx="200" cy="200" r="148" className="ring dashed reverse" />

        <g className="ticks">
          {STATIC_TICKS.map((angle) => (
            <line
              key={angle}
              x1="200"
              y1="46"
              x2="200"
              y2={angle % 30 === 0 ? 58 : 52}
              transform={`rotate(${angle} 200 200)`}
              className={angle % 30 === 0 ? 'tick major' : 'tick'}
            />
          ))}
        </g>

        <circle cx="200" cy="200" r="126" className="ring segmented" />
        <circle cx="200" cy="200" r="108" className="ring dashed fast" />
        <path
          className="arc arc-top"
          d="M 200 78 A 122 122 0 0 1 306 140"
        />
        <path
          className="arc arc-bottom"
          d="M 200 322 A 122 122 0 0 1 94 260"
        />

        <circle cx="200" cy="200" r="96" fill="url(#coreGlow)" className="core-glow" />
        <circle cx="200" cy="200" r="62" className="core-ring" />
        <circle cx="200" cy="200" r="44" className="core-ring inner" />

        <g className="triangles">
          <polygon points="200,150 243,225 157,225" />
          <polygon points="200,250 157,175 243,175" />
        </g>

        <circle cx="200" cy="200" r="16" className="core-dot" />
      </svg>

      <div className="reactor-caption">
        <span className="caption-top">{active ? 'CORE ACTIVE' : listening ? 'SENSORS OPEN' : 'STANDBY'}</span>
        <span className="caption-sub">{state}</span>
      </div>
    </div>
  );
}

export default ArcReactor;
