"""Personal finance: ledger, budgets, and grounded advice."""

from __future__ import annotations

import re
from datetime import date

import backend.db as db
from backend.brain import brain

MONEY = r"([0-9]+(?:\.[0-9]+)?\s*[kK]?)"


def _amount(text: str) -> float:
    text = (text or "").replace(",", "").lower()
    match = re.search(MONEY, text)
    if not match:
        return 0.0
    raw = match.group(1).strip()
    if raw.endswith("k"):
        return float(raw[:-1]) * 1000
    return float(raw)


def add_expense(amount: float | str, category: str = "general", note: str = "") -> str:
    try:
        value = float(amount) if not isinstance(amount, str) else _amount(amount)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0:
        return "How much did you spend, Sir?"
    db.add_transaction("expense", value, category or "general", note or "")
    summary = db.money_summary()
    return (
        f"Noted {value:.0f} on {category or 'general'}, Sir. "
        f"You have spent {summary['spent']:.0f} this month."
    )


def add_income(amount: float | str, note: str = "") -> str:
    try:
        value = float(amount) if not isinstance(amount, str) else _amount(amount)
    except (TypeError, ValueError):
        value = 0.0
    if value <= 0:
        return "How much came in, Sir?"
    db.add_transaction("income", value, "income", note or "")
    summary = db.money_summary()
    return f"Income of {value:.0f} recorded, Sir. Balance this month is {summary['balance']:.0f}."


def set_budget(category: str, amount: float | str) -> str:
    try:
        value = float(amount) if not isinstance(amount, str) else _amount(amount)
    except (TypeError, ValueError):
        value = 0.0
    if not category or value <= 0:
        return "Tell me the category and the monthly limit, Sir."
    db.set_budget(category, value)
    return f"Monthly budget for {category} set to {value:.0f}, Sir."


def budget_status() -> str:
    summary = db.money_summary()
    if not summary["income"] and not summary["spent"]:
        return (
            "I have no transactions recorded this month, Sir. "
            "Tell me an expense or income and I will start the ledger."
        )
    parts = [
        f"This month you received {summary['income']:.0f}",
        f"spent {summary['spent']:.0f}",
        f"leaving {summary['balance']:.0f}",
    ]
    if summary["by_category"]:
        top = ", ".join(f"{row['category']} {row['total']:.0f}" for row in summary["by_category"][:4])
        parts.append(f"Top categories: {top}")
    if summary["budgets"]:
        lines = []
        spent_map = {row["category"]: row["total"] for row in summary["by_category"]}
        for budget in summary["budgets"]:
            used = spent_map.get(budget["category"], 0)
            lines.append(f"{budget['category']} {used:.0f} of {budget['amount']:.0f}")
        parts.append("Budgets: " + ", ".join(lines))
    return ". ".join(parts) + ", Sir."


def _rule_based_advice(income: float, spent: float, goal: str) -> str:
    remaining = income - spent
    if income <= 0:
        return (
            "I need your monthly income to build a budget, Sir. "
            "Tell me the figure, for example: give me a budget for fifty thousand."
        )
    needs, wants, savings = income * 0.5, income * 0.3, income * 0.2
    return (
        f"On an income of {income:.0f}, a sensible split is {needs:.0f} for essentials, "
        f"{wants:.0f} for discretionary spending and {savings:.0f} into savings. "
        f"You have {remaining:.0f} left this month. "
        + (f"For {goal}, I would protect the savings tranche first, Sir." if goal else "")
    )


def budget_advice(question: str = "") -> str:
    summary = db.money_summary()
    income = summary["income"]
    spent = summary["spent"]

    # If the user names an income figure in the question, use it as the basis.
    named = _amount(question) if question else 0
    if named >= 1000 and ("budget" in question.lower() or "income" in question.lower()
                          or "salary" in question.lower()):
        income = named

    data = (
        f"Month {summary['month']}. Income {income:.0f}. Spent {spent:.0f}. "
        f"Balance {income - spent:.0f}. "
        + "Categories: "
        + ", ".join(f"{r['category']} {r['total']:.0f}" for r in summary["by_category"])
        + ". Budgets: "
        + ", ".join(f"{b['category']} {b['amount']:.0f}" for b in summary["budgets"])
    )
    prompt = (
        "Act as a practical financial adviser. Use only the ledger data below. "
        "Give a short, concrete budget plan with numbers, and one warning if spending is risky. "
        "Do not invent expenses.\n\n"
        f"Ledger: {data}\n\nQuestion: {question or 'Give me a budget for this month.'}"
    )
    answer = brain.chat(prompt, max_tokens=260)
    if answer:
        return answer
    return _rule_based_advice(income, spent, question)


def recent_transactions(limit: int = 10) -> str:
    summary = db.money_summary()
    if not summary["recent"]:
        return "The ledger is empty, Sir."
    rows = summary["recent"][:limit]
    return "Recent entries: " + "; ".join(
        f"{row['occurred_on']} {row['kind']} {row['amount']:.0f} {row['category']}"
        for row in rows
    ) + "."
