"""Thin wrapper around nba_api endpoints with retry + rate limiting.

We stay sequential (no threads) to keep request rate predictable. The NBA
stats endpoint is not officially documented and gets cranky under load —
~1 request per 0.6s is a good starting point.
"""
from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Callable

logger = logging.getLogger(__name__)

# --- Rate limiting --------------------------------------------------------
MIN_INTERVAL_SECONDS = 0.6
_last_call_at: float = 0.0


def _throttle() -> None:
    global _last_call_at
    elapsed = time.time() - _last_call_at
    if elapsed < MIN_INTERVAL_SECONDS:
        time.sleep(MIN_INTERVAL_SECONDS - elapsed)
    _last_call_at = time.time()


def call_with_retry(fn: Callable[..., Any], *args, max_retries: int = 4,
                    base_delay: float = 2.0, **kwargs) -> Any:
    """Run an nba_api endpoint with exponential backoff on failure."""
    last_err: Exception | None = None
    for attempt in range(max_retries):
        _throttle()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # nba_api raises various stdlib exceptions
            last_err = exc
            wait = base_delay * (2 ** attempt)
            logger.warning("nba_api call failed (attempt %d/%d): %s — sleeping %.1fs",
                           attempt + 1, max_retries, exc, wait)
            time.sleep(wait)
    assert last_err is not None
    raise last_err


# --- Season utilities -----------------------------------------------------

def current_season(today: date | None = None) -> str:
    """Return the NBA season string for `today` in the form '2025-26'.

    NBA seasons start in October. Anything Oct–Dec belongs to (year)-(year+1);
    Jan–Sep belongs to (year-1)-(year).
    """
    today = today or date.today()
    if today.month >= 10:
        start = today.year
    else:
        start = today.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


SEASON_TYPES = ("Regular Season", "PlayIn", "Playoffs")
