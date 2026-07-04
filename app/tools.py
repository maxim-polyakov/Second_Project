from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


DEFAULT_OBLIGATIONS_PATH = Path("data/obligations.json")
FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"
FALLBACK_RATES_TO_RUB = {
    "USD": 90.0,
    "EUR": 98.0,
}


class CurrencyConversionError(RuntimeError):
    """Raised when the exchange-rate API cannot provide a conversion."""


def _resolve_obligations_path(path: str | Path | None = None) -> Path:
    configured_path = path or os.getenv("OBLIGATIONS_PATH") or DEFAULT_OBLIGATIONS_PATH
    return Path(configured_path)


def get_obligations(
    status: str | None = None,
    category: str | None = None,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return obligations from the local fixture, optionally filtered by status/category."""
    obligations_path = _resolve_obligations_path(path)

    if not obligations_path.exists():
        raise FileNotFoundError(f"Obligations fixture was not found: {obligations_path}")

    with obligations_path.open("r", encoding="utf-8") as file:
        obligations: list[dict[str, Any]] = json.load(file)

    if status:
        normalized_status = status.lower()
        obligations = [
            item for item in obligations if item.get("status", "").lower() == normalized_status
        ]

    if category:
        normalized_category = category.lower()
        obligations = [
            item
            for item in obligations
            if item.get("category", "").lower() == normalized_category
        ]

    return obligations


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    timeout: float = 10.0,
) -> float:
    """Convert money through frankfurter.app and return only the converted amount."""
    normalized_from = from_currency.upper()
    normalized_to = to_currency.upper()

    if normalized_from == normalized_to:
        return round(float(amount), 2)

    try:
        response = httpx.get(
            FRANKFURTER_URL,
            params={
                "amount": float(amount),
                "from": normalized_from,
                "to": normalized_to,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        fallback = _fallback_convert(amount, normalized_from, normalized_to)
        if fallback is not None:
            return fallback

        raise CurrencyConversionError(
            f"Could not fetch exchange rate {normalized_from}->{normalized_to}: {exc}"
        ) from exc

    converted = payload.get("rates", {}).get(normalized_to)
    if converted is None:
        raise CurrencyConversionError(
            f"Exchange rate {normalized_from}->{normalized_to} is absent in API response."
        )

    return round(float(converted), 2)


def _fallback_convert(amount: float, from_currency: str, to_currency: str) -> float | None:
    """Use explicit fallback rates only for RUB, which frankfurter may not provide."""
    if to_currency == "RUB" and from_currency in FALLBACK_RATES_TO_RUB:
        return round(float(amount) * FALLBACK_RATES_TO_RUB[from_currency], 2)

    if from_currency == "RUB" and to_currency in FALLBACK_RATES_TO_RUB:
        return round(float(amount) / FALLBACK_RATES_TO_RUB[to_currency], 2)

    return None
