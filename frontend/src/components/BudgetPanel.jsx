import React, { useState } from 'react';

const money = (value) =>
  Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 });

function BudgetPanel({ money: summary = {}, onRefresh, onToast, api = '' }) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState('food');
  const [saving, setSaving] = useState(false);

  const spent = summary.spent || 0;
  const income = summary.income || 0;
  const balance = summary.balance || 0;
  const categories = summary.by_category || [];
  const budgets = summary.budgets || [];
  const top = categories.slice(0, 3);

  const saveExpense = async (event) => {
    event.preventDefault();
    const value = parseFloat(amount);
    if (!value || value <= 0) {
      onToast?.('Enter an amount greater than zero.');
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`${api}/api/money/expense`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: value, category, note: '' }),
      });
      const data = await res.json();
      onToast?.(data.message || 'Expense recorded.');
      setAmount('');
      setOpen(false);
      onRefresh?.();
    } catch {
      onToast?.('Could not record that expense.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="panel money-panel">
      <header className="panel-head">
        <h2>Ledger</h2>
        <span className="tag">{summary.month || 'this month'}</span>
      </header>

      <div className="money-grid">
        <div>
          <span className="k">In</span>
          <b className="v pos">{money(income)}</b>
        </div>
        <div>
          <span className="k">Out</span>
          <b className="v neg">{money(spent)}</b>
        </div>
        <div>
          <span className="k">Net</span>
          <b className={`v ${balance >= 0 ? 'pos' : 'neg'}`}>{money(balance)}</b>
        </div>
      </div>

      {top.length > 0 && (
        <div className="cat-list">
          {top.map((cat) => {
            const share = spent ? Math.round((cat.total / spent) * 100) : 0;
            return (
              <div className="cat" key={cat.category}>
                <span>{cat.category}</span>
                <div className="cat-bar"><i style={{ width: `${share}%` }} /></div>
                <b>{money(cat.total)}</b>
              </div>
            );
          })}
        </div>
      )}

      {budgets.length > 0 && (
        <div className="budget-list">
          {budgets.slice(0, 3).map((budget) => {
            const used = categories.find((c) => c.category === budget.category)?.total || 0;
            const pct = budget.amount ? Math.min(100, Math.round((used / budget.amount) * 100)) : 0;
            return (
              <div className="budget" key={budget.id || budget.category}>
                <div className="budget-head">
                  <span>{budget.category} cap</span>
                  <b>{pct}%</b>
                </div>
                <div className="budget-bar">
                  <i className={pct > 90 ? 'over' : ''} style={{ width: `${pct}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {open ? (
        <form className="expense-form" onSubmit={saveExpense}>
          <input
            type="number"
            min="1"
            step="0.01"
            placeholder="Amount"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            autoFocus
          />
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            {['food', 'transport', 'bills', 'shopping', 'health', 'fun', 'general'].map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          <button type="submit" disabled={saving}>{saving ? '…' : 'Log'}</button>
          <button type="button" className="muted" onClick={() => setOpen(false)}>✕</button>
        </form>
      ) : (
        <button className="wide-btn" onClick={() => setOpen(true)}>+ Log an expense</button>
      )}
    </section>
  );
}

export default BudgetPanel;
