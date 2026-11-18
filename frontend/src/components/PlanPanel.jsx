import React from 'react';

const ICONS = {
  pending: '○',
  running: '◌',
  done: '✓',
  failed: '✕',
  skipped: '—',
};

function PlanPanel({ plan }) {
  if (!plan || !plan.steps || plan.steps.length === 0) return null;
  const running = plan.status === 'running' || plan.status === 'step';
  const completed = plan.steps.filter((step) => step.status === 'done').length;

  return (
    <section className={`panel plan-panel ${running ? 'running' : ''}`}>
      <header className="panel-head">
        <h2>Execution plan</h2>
        <span className="tag">{plan.status}</span>
      </header>
      <p className="plan-goal">{plan.goal}</p>
      <ol className="plan-steps">
        {plan.steps.map((step, index) => (
          <li key={`${step.action}-${index}`} className={`plan-step ${step.status || 'pending'}`}>
            <span className="plan-icon">{ICONS[step.status] || '○'}</span>
            <span className="plan-action">{step.action.replace(/_/g, ' ')}</span>
            {step.result && <span className="plan-result">{step.result}</span>}
          </li>
        ))}
      </ol>
      <div className="plan-foot">
        <span>{completed}/{plan.steps.length} complete</span>
        {running && <span className="plan-pulse">executing</span>}
      </div>
    </section>
  );
}

export default PlanPanel;
