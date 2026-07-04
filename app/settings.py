from __future__ import annotations

import os
from datetime import date


def get_current_date() -> date:
    """Return current date, with an optional override for reproducible reviews."""
    configured_date = os.getenv("APP_CURRENT_DATE")
    if configured_date:
        return date.fromisoformat(configured_date)

    return date.today()
