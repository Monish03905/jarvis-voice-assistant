import React, { useState } from 'react';

function AgendaPanel({ agenda = {}, api = '', onAdded, busy = false }) {
  const [title, setTitle] = useState('');
  const [when, setWhen] = useState('');
  const [saving, setSaving] = useState(false);

  const events = agenda.events || [];
  const tasks = agenda.tasks || [];
  const reminders = agenda.reminders || [];
  const upcomingTasks = agenda.upcoming_tasks || [];
  const upcomingEvents = agenda.upcoming_events || [];

  const submit = async (event) => {
    event.preventDefault();
    if (!title.trim() || saving) return;
    setSaving(true);
    try {
      const response = await fetch(`${api}/api/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: title.trim(), when: when.trim() }),
      });
      if (response.ok) {
        setTitle('');
        setWhen('');
        onAdded?.();
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="panel agenda-panel">
      <header className="panel-head">
        <h2>Agenda</h2>
        <span className="tag">{agenda.day ? 'today' : '--'}</span>
      </header>

      <ul className="agenda-list">
        {events.length === 0 && tasks.length === 0 && reminders.length === 0 && (
          <li className="agenda-empty">Nothing scheduled today. Add a task below.</li>
        )}
        {events.map((event) => (
          <li key={`e-${event.id}`} className="agenda-event">
            <span className="agenda-time">{event.time}</span>
            <span className="agenda-title">{event.title}</span>
            {event.location && <span className="agenda-where">{event.location}</span>}
          </li>
        ))}
        {tasks.map((task) => (
          <li key={`t-${task.id}`} className={`agenda-task ${task.priority === 1 ? 'high' : ''}`}>
            <span className="agenda-box" />
            <span className="agenda-title">{task.title}</span>
            {task.due_at && <span className="agenda-where">{task.due_at.slice(11, 16)}</span>}
          </li>
        ))}
        {reminders.map((reminder) => (
          <li key={`r-${reminder.id}`} className="agenda-task">
            <span className="agenda-box bell" />
            <span className="agenda-title">{reminder.text}</span>
          </li>
        ))}
      </ul>

      {(upcomingEvents.length > 0 || upcomingTasks.length > 0) && (
        <div className="agenda-upcoming">
          <div className="agenda-sub">Upcoming</div>
          <ul className="agenda-list">
            {upcomingEvents.map((event) => (
              <li key={`ue-${event.id}`} className="agenda-event dim">
                <span className="agenda-time">{event.human_due}</span>
                <span className="agenda-title">{event.title}</span>
              </li>
            ))}
            {upcomingTasks.map((task) => (
              <li key={`ut-${task.id}`} className={`agenda-task dim ${task.priority === 1 ? 'high' : ''}`}>
                <span className="agenda-box" />
                <span className="agenda-title">{task.title}</span>
                <span className="agenda-where">{task.human_due}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <form className="agenda-form" onSubmit={submit}>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="New task or reminder"
          aria-label="New task"
        />
        <input
          value={when}
          onChange={(event) => setWhen(event.target.value)}
          placeholder="when (optional)"
          aria-label="When"
          className="when"
        />
        <button type="submit" disabled={!title.trim() || saving || busy}>+</button>
      </form>
    </section>
  );
}

export default AgendaPanel;
