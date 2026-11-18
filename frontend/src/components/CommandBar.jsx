import React, { useState } from 'react';

const SUGGESTIONS = [
  'Good morning, brief me',
  'Play something calm on YouTube',
  'Send a WhatsApp to …',
  'What is the weather today?',
  'Remind me to stretch in 20 minutes',
  'How much did I spend on food?',
];

function CommandBar({ onSend, busy }) {
  const [value, setValue] = useState('');
  const [placeholder] = useState(
    () => SUGGESTIONS[Math.floor(Math.random() * SUGGESTIONS.length)]
  );

  const submit = (event) => {
    event.preventDefault();
    const text = value.trim();
    if (!text) return;
    setValue('');
    onSend?.(text);
  };

  return (
    <form className={`command-bar ${busy ? 'is-busy' : ''}`} onSubmit={submit}>
      <span className="prompt-glyph">›</span>
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={`Try: “${placeholder}”`}
        aria-label="Command"
        autoComplete="off"
        spellCheck="false"
      />
      <button type="submit" disabled={busy || !value.trim()}>
        {busy ? <span className="spinner" /> : 'SEND'}
      </button>
    </form>
  );
}

export default CommandBar;
