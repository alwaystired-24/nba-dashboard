"""Display formatters used across all pages."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("US/Eastern")
HKT = ZoneInfo("Asia/Hong_Kong")


def hkt_today() -> str:
    """Today's date string in Hong Kong time."""
    return datetime.now(HKT).date().isoformat()


def hkt_now_label() -> str:
    return datetime.now(HKT).strftime("%a %d %b %Y, %H:%M HKT")


def et_to_hkt_date(et_date_str: str) -> str:
    """Convert an ET date string ('2026-04-29') to the HKT date the games map to.

    NBA tip-offs are typically 7–10 PM ET, which is 7–10 AM HKT NEXT day.
    So games on ET date X mostly show as HKT date X+1.
    """
    d = date.fromisoformat(et_date_str)
    # Approx: assume 8pm ET = 8am HKT next day
    return (d + timedelta(days=1)).isoformat()


def hkt_to_et_date(hkt_date_str: str) -> str:
    """When user picks 'today' in HKT, find the matching ET date for the schedule."""
    d = date.fromisoformat(hkt_date_str)
    return (d - timedelta(days=1)).isoformat()


def fmt_pct(x, decimals: int = 1) -> str:
    """0.487 -> '48.7%'. Handles None/NaN."""
    if x is None or pd.isna(x):
        return "—"
    return f"{x*100:.{decimals}f}%"


def fmt_num(x, decimals: int = 1) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{x:.{decimals}f}"


def fmt_int(x) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{int(x)}"


def fmt_record(w: int, l: int) -> str:
    return f"{w}-{l}"


def status_badge(status: str) -> str:
    return {
        "Final":     "🏁 Final",
        "Live":      "🔴 Live",
        "Scheduled": "🕒 Scheduled",
        "PPD":       "⏸ Postponed",
    }.get(status, status or "—")


def matchup_label(home_abbr: str, away_abbr: str) -> str:
    return f"{away_abbr} @ {home_abbr}"
