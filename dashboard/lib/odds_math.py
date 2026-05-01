"""Odds math — implied probability, vig, no-vig fair lines.

All input prices are DECIMAL odds (Pinnacle / European format).
American odds conversion at the bottom if you need it for display.
"""
from __future__ import annotations

import math
from typing import Optional


# =========================================================================
# IMPLIED PROBABILITY
# =========================================================================

def implied_prob(decimal_price: Optional[float]) -> Optional[float]:
    """Decimal odds → raw implied probability (includes vig). 1.91 → 0.524.

    Returns None if input is None / 0 / negative.
    """
    if decimal_price is None or decimal_price <= 1.0:
        return None
    return 1.0 / decimal_price


# =========================================================================
# VIG (BOOK MARGIN)
# =========================================================================

def two_way_vig(price_a: Optional[float], price_b: Optional[float]) -> Optional[float]:
    """Vig on a 2-way market (moneyline, spread sides, totals over/under).

    vig = (1/price_a + 1/price_b) - 1.0
    Returns vig as a decimal (0.045 = 4.5% vig). None if inputs missing.
    """
    pa = implied_prob(price_a)
    pb = implied_prob(price_b)
    if pa is None or pb is None:
        return None
    return (pa + pb) - 1.0


# =========================================================================
# NO-VIG FAIR PROBABILITIES — the "true" probability after stripping margin
# =========================================================================

def no_vig_probs(price_a: Optional[float],
                   price_b: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """Return fair (no-vig) probabilities for a 2-way market.

    Method: proportional adjustment. Each side's fair prob = its raw implied
    prob divided by the sum of both. This is the standard approach unless you
    have a reason to believe the vig is asymmetrically applied.
    """
    pa = implied_prob(price_a)
    pb = implied_prob(price_b)
    if pa is None or pb is None:
        return None, None
    total = pa + pb
    if total == 0:
        return None, None
    return pa / total, pb / total


def no_vig_decimal_prices(price_a: Optional[float],
                            price_b: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """Same as no_vig_probs but returns decimal odds instead of probabilities.

    1 / fair_prob = fair decimal price.
    """
    fa, fb = no_vig_probs(price_a, price_b)
    if fa is None or fb is None:
        return None, None
    if fa == 0 or fb == 0:
        return None, None
    return 1.0 / fa, 1.0 / fb


# =========================================================================
# AMERICAN ODDS CONVERSION (for display)
# =========================================================================

def decimal_to_american(decimal_price: Optional[float]) -> Optional[int]:
    """1.91 → -110, 2.50 → +150."""
    if decimal_price is None or decimal_price <= 1.0:
        return None
    if decimal_price >= 2.0:
        return int(round((decimal_price - 1) * 100))
    return int(round(-100 / (decimal_price - 1)))


def american_to_decimal(american: Optional[int]) -> Optional[float]:
    if american is None:
        return None
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


# =========================================================================
# CONVENIENCE — produce a full "fair line" report from a 2-way market
# =========================================================================

def fair_line_report(price_a: Optional[float], price_b: Optional[float]) -> dict:
    """Compact summary for one 2-way market.

    Returns dict with implied_prob_a/b, fair_prob_a/b, fair_decimal_a/b, vig_pct.
    All keys present; values may be None if input incomplete.
    """
    pa = implied_prob(price_a)
    pb = implied_prob(price_b)
    fa, fb = no_vig_probs(price_a, price_b)
    fda, fdb = no_vig_decimal_prices(price_a, price_b)
    vig = two_way_vig(price_a, price_b)
    return {
        "implied_prob_a": pa,
        "implied_prob_b": pb,
        "fair_prob_a": fa,
        "fair_prob_b": fb,
        "fair_decimal_a": fda,
        "fair_decimal_b": fdb,
        "vig_pct": vig * 100 if vig is not None else None,
    }
