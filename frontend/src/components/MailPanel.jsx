import React, { useState } from 'react';

function MailPanel({ accounts = [], api = '', onAsk, onToast }) {
  const [busy, setBusy] = useState(false);
  const ready = accounts.filter((a) => a.configured);
  const linked = accounts.length > 0;

  const call = async (path, body) => {
    setBusy(true);
    try {
      const res = await fetch(`${api}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {}),
      });
      const data = await res.json();
      onToast?.(data.message || 'Done.');
    } catch {
      onToast?.('Mail request failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel mail-panel">
      <header className="panel-head">
        <h2>Mail</h2>
        <span className="tag">
          {ready.length ? `${ready.length} ready` : linked ? 'setup needed' : 'not linked'}
        </span>
      </header>

      {linked ? (
        <ul className="mail-list">
          {accounts.map((acc) => (
            <li key={acc.label}>
              <i className={acc.configured ? 'on' : 'off'} />
              <div>
                <b>{acc.label}</b>
                <span>{acc.address || 'no address yet'}</span>
              </div>
              <em>{acc.configured ? 'ready' : 'setup'}</em>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mail-hint">
          No account linked. Run <code>python tools/link_email.py</code>.
        </p>
      )}

      <div className="mail-actions">
        <button disabled={busy || !ready.length} onClick={() => onAsk?.('read my emails')}>
          Check mail
        </button>
        <button disabled={busy} onClick={() => call('/api/email/test')}>
          Test
        </button>
        <button disabled={busy || !ready.length} onClick={() => call('/api/email/sync-contacts')}>
          Import contacts
        </button>
      </div>
    </section>
  );
}

export default MailPanel;
