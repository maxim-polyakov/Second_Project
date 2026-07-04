from __future__ import annotations

import json

import pytest

from app import analytics


@pytest.fixture()
def obligations_path(tmp_path, monkeypatch):
    path = tmp_path / "obligations.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "title": "Service A",
                    "amount": 10.0,
                    "currency": "USD",
                    "category": "tools",
                    "next_payment_date": "2026-07-05",
                    "status": "active",
                },
                {
                    "id": "2",
                    "title": "Service B",
                    "amount": 1000.0,
                    "currency": "RUB",
                    "category": "education",
                    "next_payment_date": "2026-07-06",
                    "status": "active",
                },
                {
                    "id": "3",
                    "title": "Service C",
                    "amount": 20.0,
                    "currency": "EUR",
                    "category": "education",
                    "next_payment_date": "2026-08-20",
                    "status": "active",
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OBLIGATIONS_PATH", str(path))
    monkeypatch.setenv("APP_CURRENT_DATE", "2026-07-04")
    return path


def test_calculate_spending_next_days_uses_deterministic_conversion(
    obligations_path,
    monkeypatch,
):
    monkeypatch.setattr(analytics, "convert_currency", lambda amount, *_: amount * 90)

    result = analytics.calculate_spending_next_days(days=7)

    assert result["total"] == 1900.0
    assert [item["title"] for item in result["items"]] == ["Service A", "Service B"]


def test_find_most_expensive_category_uses_category_subtotals(
    obligations_path,
    monkeypatch,
):
    def fake_convert(amount, from_currency, to_currency):
        rates = {"USD": 90, "EUR": 100}
        return amount * rates[from_currency]

    monkeypatch.setattr(analytics, "convert_currency", fake_convert)

    result = analytics.find_most_expensive_category()

    assert result["top_category"]["category"] == "education"
    assert result["top_category"]["total"] == 3000.0


def test_list_payments_next_days_filters_by_configured_date(obligations_path):
    result = analytics.list_payments_next_days(days=7)

    assert [payment["title"] for payment in result["payments"]] == [
        "Service A",
        "Service B",
    ]
