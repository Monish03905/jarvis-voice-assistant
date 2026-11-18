import React from 'react';

function Ring({ value, label, unit = '%', tone = 'cyan', low = 101 }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const r = 30;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;
  return (
    <div className={`ring-gauge tone-${tone} ${pct >= low ? 'hot' : ''}`}>
      <svg viewBox="0 0 80 80">
        <circle className="track" cx="40" cy="40" r={r} />
        <circle
          className="value"
          cx="40"
          cy="40"
          r={r}
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="ring-label">
        <b>{value == null ? '--' : Math.round(pct)}</b>
        <span>{unit}</span>
      </div>
      <div className="ring-name">{label}</div>
    </div>
  );
}

function SystemStats({ stats = {}, health = {}, vitals = {} }) {
  const battery = stats.battery;
  const mailAccounts = health.email?.accounts || [];
  const gpu = (vitals.gpu || [])[0];
  const thermal = (vitals.temperatures || [])[0];
  const gpuLabel = gpu
    ? `${Math.round(gpu.util ?? 0)}%${gpu.temperature != null ? ` · ${Math.round(gpu.temperature)}°C` : ''}`
    : 'n/a';
  const healthRows = [
    ['Brain', health.brain || 'offline'],
    ['Chrome', health.chrome ? 'ready' : 'missing'],
    ['Phone Link', health.phone_link?.open ? 'open' : 'closed'],
    ['GPU', gpuLabel],
    ['Thermals', thermal ? `${Math.round(thermal.current)}°C` : 'n/a'],
    ...(mailAccounts.length
      ? mailAccounts.map((acc) => [`Mail · ${acc.label}`, acc.configured ? 'ready' : 'incomplete'])
      : [['Mail', 'not linked']]),
    ['Disk free', health.disk_free_gb != null ? `${Math.round(health.disk_free_gb)} GB` : '--'],
  ];

  return (
    <section className="panel stats-panel">
      <header className="panel-head">
        <h2>Vitals</h2>
        <span className="tag">live</span>
      </header>

      <div className="gauges">
        <Ring value={stats.cpu} label="CPU" />
        <Ring value={stats.ram} label="RAM" low={85} />
        <Ring value={battery} label="BATTERY" tone={battery != null && battery < 25 ? 'amber' : 'cyan'} />
        <Ring value={stats.disk} label="DISK" low={90} tone="amber" />
      </div>

      <div className="net-row">
        <span><i className="up" /> ↑ {stats.net_sent_mb ?? '--'} MB</span>
        <span><i className="down" /> ↓ {stats.net_recv_mb ?? '--'} MB</span>
        {stats.charging && <span className="charging">charging</span>}
      </div>

      <ul className="health-list">
        {healthRows.map(([label, value]) => (
          <li key={label}>
            <span>{label}</span>
            <b>{value}</b>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default SystemStats;
