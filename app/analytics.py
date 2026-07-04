from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.settings import get_current_date
from app.tools import convert_currency, get_obligations


def calculate_spending_next_days(days: int = 30, target_currency: str = "RUB") -> dict[str, Any]:
    current_date = get_current_date()
    period_end = current_date + timedelta(days=days)
    obligations = [
        item
        for item in get_obligations(status="active")
        if current_date <= date.fromisoformat(item["next_payment_date"]) <= period_end
    ]

    total = 0.0
    items = []
    for item in obligations:
        converted = _convert_item_amount(item, target_currency)
        total += converted
        items.append(
            {
                "title": item["title"],
                "date": item["next_payment_date"],
                "amount": item["amount"],
                "currency": item["currency"],
                "converted_amount": converted,
                "target_currency": target_currency,
            }
        )

    return {
        "period": {
            "from": current_date.isoformat(),
            "to": period_end.isoformat(),
            "days": days,
        },
        "target_currency": target_currency,
        "total": round(total, 2),
        "items": items,
    }


def find_most_expensive_category(target_currency: str = "RUB") -> dict[str, Any]:
    grouped: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for item in get_obligations(status="active"):
        grouped[item["category"]][item["currency"]] += float(item["amount"])

    categories = []
    for category, currency_totals in grouped.items():
        converted_parts = []
        category_total = 0.0
        for currency, amount in currency_totals.items():
            converted = (
                round(amount, 2)
                if currency.upper() == target_currency.upper()
                else convert_currency(amount, currency, target_currency)
            )
            category_total += converted
            converted_parts.append(
                {
                    "amount": round(amount, 2),
                    "currency": currency,
                    "converted_amount": converted,
                    "target_currency": target_currency,
                }
            )

        categories.append(
            {
                "category": category,
                "total": round(category_total, 2),
                "target_currency": target_currency,
                "parts": converted_parts,
            }
        )

    categories.sort(key=lambda item: item["total"], reverse=True)
    return {
        "target_currency": target_currency,
        "top_category": categories[0] if categories else None,
        "categories": categories,
    }


def list_payments_next_days(days: int = 7) -> dict[str, Any]:
    current_date = get_current_date()
    period_end = current_date + timedelta(days=days)
    payments = [
        item
        for item in get_obligations(status="active")
        if current_date <= date.fromisoformat(item["next_payment_date"]) <= period_end
    ]
    payments.sort(key=lambda item: item["next_payment_date"])

    return {
        "period": {
            "from": current_date.isoformat(),
            "to": period_end.isoformat(),
            "days": days,
        },
        "payments": payments,
    }


def _convert_item_amount(item: dict[str, Any], target_currency: str) -> float:
    currency = item["currency"]
    amount = float(item["amount"])
    if currency.upper() == target_currency.upper():
        return round(amount, 2)

    return convert_currency(amount, currency, target_currency)
