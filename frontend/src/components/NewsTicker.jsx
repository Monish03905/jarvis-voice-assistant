import React from 'react';

function NewsTicker({ items = [], onAsk }) {
  const list = items.slice(0, 12);
  const feed = list.length
    ? list
    : [{ title: 'Awaiting the next world feed…', source: 'JARVIS', link: '' }];

  const row = (keyPrefix) => (
    <div className="ticker-row" key={keyPrefix}>
      {feed.map((item, i) => (
        <button
          key={`${keyPrefix}-${i}`}
          className="ticker-item"
          onClick={() => onAsk?.(`tell me more about: ${item.title}`)}
          title={item.source}
        >
          <span className="ticker-src">{item.source}</span>
          <span className="ticker-title">{item.title}</span>
          <span className="ticker-sep">◆</span>
        </button>
      ))}
    </div>
  );

  return (
    <footer className="ticker">
      <div className="ticker-label">
        <span className="pulse" /> WORLD FEED
      </div>
      <div className="ticker-viewport">
        <div className="ticker-track">
          {row('a')}
          {row('b')}
        </div>
      </div>
    </footer>
  );
}

export default NewsTicker;
