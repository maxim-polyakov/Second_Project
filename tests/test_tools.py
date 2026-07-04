from __future__ import annotations

import json

import httpx
import pytest

from app import tools
from app.tools import CurrencyConversionError, convert_currency, get_obligations


@pytest.fixture()
def fixture_path(tmp_path):
    path = tmp_path / "obligations.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "title": "Netflix",
                    "amount": 15.49,
                    "currency": "USD",
                    "category": "entertainment",
                    "next_payment_date": "2026-07-10",
                    "status": "active",
                },
                {
                    "id": "2",
                    "title": "Old VPN",
                    "amount": 9.99,
                    "currency": "EUR",
                    "category": "security",
                    "next_payment_date": "2026-07-07",
                    "status": "cancelled",
                },
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_get_obligations_returns_all_items(fixture_path):
    obligations = get_obligations(path=fixture_path)

    assert len(obligations) == 2
    assert obligations[0]["title"] == "Netflix"


def test_get_obligations_filters_by_status_and_category(fixture_path):
    obligations = get_obligations(
        status="ACTIVE",
        category="ENTERTAINMENT",
        path=fixture_path,
    )

    assert len(obligations) == 1
    assert obligations[0]["id"] == "1"


def test_convert_currency_returns_same_currency_without_api_call(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("HTTP API should not be called for same-currency conversion")

    monkeypatch.setattr(tools.httpx, "get", fail_if_called)

    assert convert_currency(100, "rub", "RUB") == 100.0


def test_convert_currency_uses_frankfurter_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"rates": {"RUB": 894.5}}

    def fake_get(url, params=None, timeout=10.0):
        assert url == tools.FRANKFURTER_URL
        assert params == {"amount": 10.0, "from": "USD", "to": "RUB"}
        assert timeout == 10.0
        return FakeResponse()

    monkeypatch.setattr(tools.httpx, "get", fake_get)

    assert convert_currency(10, "usd", "rub") == 894.5


def test_convert_currency_raises_clear_error_on_api_failure(monkeypatch):
    def fake_get(url, params=None, timeout=10.0):
        raise httpx.ConnectError("network is down")

    monkeypatch.setattr(tools.httpx, "get", fake_get)

    with pytest.raises(CurrencyConversionError, match="Could not fetch exchange rate"):
        convert_currency(10, "GBP", "CHF")


def test_convert_currency_uses_rub_fallback_when_api_does_not_support_pair(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=10.0):
        calls.append(url)
        if url == tools.FRANKFURTER_URL:
            raise httpx.HTTPStatusError(
                "not found",
                request=httpx.Request("GET", url),
                response=httpx.Response(404),
            )

        class FakeFallbackResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"rates": {"RUB": 91.5}}

        return FakeFallbackResponse()

    monkeypatch.setattr(tools.httpx, "get", fake_get)

    assert convert_currency(2, "USD", "RUB") == 183.0
    assert calls == [
        tools.FRANKFURTER_URL,
        tools.SECONDARY_RATES_URL.format(base_currency="USD"),
    ]
