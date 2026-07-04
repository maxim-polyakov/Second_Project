from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.settings import get_current_date
from app.tools import get_obligations


DEMO_RATES_TO_RUB = {
    "RUB": 1.0,
    "USD": 90.0,
    "EUR": 98.0,
}


def ask_demo_agent(question: str, today: date | None = None) -> dict[str, Any]:
    """Deterministic demo agent used when the paid LLM API is unavailable."""
    current_date = today or get_current_date()
    normalized_question = question.lower()
    obligations = get_obligations(status="active")
    trace: list[dict[str, Any]] = [
        {
            "type": "llm",
            "content": (
                "Thought: Включен DEMO_MODE, поэтому отвечаю локально по фикстуре "
                "и демонстрационным курсам без вызова LLM."
            ),
        },
        {
            "type": "action",
            "tool": "get_obligations",
            "input": json.dumps({"status": "active"}, ensure_ascii=False),
        },
        {
            "type": "observation",
            "content": json.dumps(obligations, ensure_ascii=False, indent=2),
        },
    ]

    if "30" in normalized_question or "ближайш" in normalized_question:
        return _answer_next_30_days(obligations, current_date, trace)

    if "категор" in normalized_question or "дороже" in normalized_question:
        return _answer_top_category(obligations, trace)

    if "недел" in normalized_question:
        return _answer_this_week(obligations, current_date, trace)

    return {
        "answer": (
            "DEMO_MODE умеет отвечать на три проверочных сценария: расходы за "
            "ближайшие 30 дней, самая дорогая категория и платежи на этой неделе. "
            "Для произвольных вопросов нужен активный баланс DeepSeek."
        ),
        "trace": trace,
    }


def _answer_next_30_days(
    obligations: list[dict[str, Any]],
    current_date: date,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    period_end = current_date + timedelta(days=30)
    upcoming = [
        item
        for item in obligations
        if current_date <= date.fromisoformat(item["next_payment_date"]) <= period_end
    ]
    total = sum(_to_rub(item["amount"], item["currency"]) for item in upcoming)

    trace.append(
        {
            "type": "llm",
            "content": (
                f"Thought: Фильтрую активные платежи с {current_date.isoformat()} "
                f"по {period_end.isoformat()} и перевожу суммы в RUB."
            ),
        }
    )

    titles = ", ".join(item["title"] for item in upcoming)
    return {
        "answer": (
            f"В ближайшие 30 дней ожидается {len(upcoming)} активных платежей "
            f"на сумму примерно {total:.2f} RUB. Учтены: {titles}."
        ),
        "trace": trace,
    }


def _answer_top_category(
    obligations: list[dict[str, Any]],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    totals: defaultdict[str, float] = defaultdict(float)
    for item in obligations:
        totals[item["category"]] += _to_rub(item["amount"], item["currency"])

    top_category, top_total = max(totals.items(), key=lambda item: item[1])
    trace.append(
        {
            "type": "llm",
            "content": (
                "Thought: Группирую активные обязательства по category, "
                "конвертирую в RUB и выбираю максимум."
            ),
        }
    )

    breakdown = ", ".join(
        f"{category}: {amount:.2f} RUB" for category, amount in sorted(totals.items())
    )
    return {
        "answer": (
            f"Самая затратная категория: {top_category}, примерно {top_total:.2f} RUB. "
            f"Разбивка по категориям: {breakdown}."
        ),
        "trace": trace,
    }


def _answer_this_week(
    obligations: list[dict[str, Any]],
    current_date: date,
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    week_end = current_date + timedelta(days=7)
    payments = [
        item
        for item in obligations
        if current_date <= date.fromisoformat(item["next_payment_date"]) <= week_end
    ]
    trace.append(
        {
            "type": "llm",
            "content": (
                f"Thought: Проверяю платежи с {current_date.isoformat()} "
                f"по {week_end.isoformat()}."
            ),
        }
    )

    if not payments:
        return {
            "answer": "В ближайшие 7 дней активных платежей нет.",
            "trace": trace,
        }

    details = "; ".join(
        f"{item['title']} - {item['next_payment_date']} ({item['amount']} {item['currency']})"
        for item in payments
    )
    return {
        "answer": f"Да, в ближайшие 7 дней есть платежи: {details}.",
        "trace": trace,
    }


def _to_rub(amount: float, currency: str) -> float:
    rate = DEMO_RATES_TO_RUB.get(currency.upper())
    if rate is None:
        raise ValueError(f"Demo rate for {currency} is not configured.")
    return round(float(amount) * rate, 2)
