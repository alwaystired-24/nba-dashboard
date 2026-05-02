"""Diverging color mapper for stat tables.

Color scheme: rank 1 (best) = green, rank 15 = neutral, rank 30 = red.
Both extremes pop. Used by Team Stats and Player Stats pages.
"""
from __future__ import annotations

import pandas as pd


# RGB values, dark-theme friendly, all WCAG-AA contrast safe
COLOR_BEST = (62, 168, 102)       # solid green
COLOR_NEUTRAL = (45, 56, 78)      # neutral navy (table bg-ish)
COLOR_WORST = (200, 70, 70)       # solid red
TEXT_DARK = "#0E1525"             # for use over light backgrounds (best/worst peaks)
TEXT_LIGHT = "#E5E9F0"            # for use over neutral backgrounds


def _interpolate(c1: tuple[int, int, int], c2: tuple[int, int, int],
                  t: float) -> tuple[int, int, int]:
    """t=0 returns c1, t=1 returns c2."""
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def rank_to_color(rank: float, n_total: int = 30) -> str:
    """Convert a rank (1=best) into an rgba CSS string.

    1   -> bright green
    15  -> neutral (~45% of original alpha to soften)
    30  -> bright red

    Returns CSS like "rgba(62, 168, 102, 0.65)".
    """
    if pd.isna(rank) or n_total < 2:
        return ""

    # Position within range, 0 = best, 1 = worst
    pos = (rank - 1) / (n_total - 1)
    pos = max(0.0, min(1.0, pos))

    if pos <= 0.5:
        # Best half: green -> neutral
        t = pos * 2  # 0 (best) -> 1 (mid)
        rgb = _interpolate(COLOR_BEST, COLOR_NEUTRAL, t)
    else:
        # Worst half: neutral -> red
        t = (pos - 0.5) * 2  # 0 (mid) -> 1 (worst)
        rgb = _interpolate(COLOR_NEUTRAL, COLOR_WORST, t)

    # Alpha: more pronounced at extremes, softer at middle
    alpha = 0.30 + abs(pos - 0.5) * 1.4  # 0.30 (mid) -> ~1.0 (extremes)
    alpha = min(0.95, alpha)

    return f"rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha:.2f})"


def text_for_rank(rank: float, n_total: int = 30) -> str:
    """Returns text color CSS — light text everywhere except deep extremes
    where the green/red is so intense that we need dark text for contrast."""
    if pd.isna(rank):
        return ""
    pos = (rank - 1) / (n_total - 1)
    pos = max(0.0, min(1.0, pos))
    # Within ~25% of either extreme, use dark text on the bright bg
    if pos < 0.20 or pos > 0.80:
        return TEXT_DARK
    return TEXT_LIGHT


def style_dataframe_by_ranks(df: pd.DataFrame, rank_columns: dict[str, str],
                              n_total: int = 30,
                              league_avg_row_name: str | None = "League avg",
                              league_avg_col: str = "team",
                              ) -> "pd.io.formats.style.Styler":
    """Color each value cell by its sibling rank column.

    Args:
        df: DataFrame to style. May contain rank columns alongside value columns.
        rank_columns: mapping of {value_column_name: rank_column_name}.
                      e.g., {"pts": "pts_rank", "off_rating": "off_rating_rank"}
        n_total: total population size (e.g., 30 for teams, total player count
                 for players).
        league_avg_row_name: if df[league_avg_col] equals this, the row gets
                             a distinct neutral background instead of rank colors.
        league_avg_col: which column to check for the league avg row name.

    Returns a Styler. Just pass to st.dataframe.
    """
    def color_row(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        # Detect League avg row — give it a distinct amber accent across ALL cells
        is_league_avg = (
            league_avg_row_name is not None
            and league_avg_col in row.index
            and str(row[league_avg_col]) == league_avg_row_name
        )
        if is_league_avg:
            return [
                "background-color: rgba(244,167,66,0.12); color: #F4A742; "
                "font-weight: 600; border-top: 1px solid rgba(244,167,66,0.4);"
            ] * len(row)

        for value_col, rank_col in rank_columns.items():
            if value_col not in row.index or rank_col not in row.index:
                continue
            rank = row[rank_col]
            if pd.isna(rank):
                continue
            bg = rank_to_color(rank, n_total)
            txt = text_for_rank(rank, n_total)
            if bg:
                col_idx = row.index.get_loc(value_col)
                styles[col_idx] = f"background-color: {bg}; color: {txt}; font-weight: 600;"
        return styles

    return df.style.apply(color_row, axis=1)


def percentile_to_color(pct: float) -> str:
    """For Player Stats — input is percentile (100=best), maps inverse to rank_to_color."""
    if pd.isna(pct):
        return ""
    # pct 100 -> rank 1, pct 0 -> rank "100" (any large), use 100 as denom for symmetry
    rank = 100 - pct  # so 100 pct -> rank 0 -> nearly best
    return rank_to_color(rank + 1, n_total=100)


def text_for_percentile(pct: float) -> str:
    if pd.isna(pct):
        return ""
    rank = 100 - pct + 1
    return text_for_rank(rank, n_total=100)


def style_dataframe_by_percentiles(df: pd.DataFrame,
                                     pct_columns: dict[str, str]
                                     ) -> "pd.io.formats.style.Styler":
    """Same as style_dataframe_by_ranks but inputs are percentiles (100=best)."""
    def color_row(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        for value_col, pct_col in pct_columns.items():
            if value_col not in row.index or pct_col not in row.index:
                continue
            pct = row[pct_col]
            if pd.isna(pct):
                continue
            bg = percentile_to_color(pct)
            txt = text_for_percentile(pct)
            if bg:
                col_idx = row.index.get_loc(value_col)
                styles[col_idx] = f"background-color: {bg}; color: {txt}; font-weight: 600;"
        return styles

    return df.style.apply(color_row, axis=1)


# =========================================================================
# METRIC CARD HTML HELPERS
# =========================================================================

def _bg_for_rank(rank: int | float | None, n_total: int = 30,
                  is_neutral_metric: bool = False) -> tuple[str, str, str]:
    """Return (bg_rgba, border_rgba, delta_color) for a rank.

    Bands (4-tier):
        1 to ~20% of n  -> bright green
        ~20% to ~45%    -> soft green
        ~45% to ~55%    -> neutral
        ~55% to ~80%    -> soft red
        ~80% to n       -> bright red
    is_neutral_metric=True forces the neutral color (used for Pace which doesn't
    have a "good" or "bad" direction).
    """
    if rank is None or n_total < 2:
        return ("#172033", "#25304a", "#8B95A8")
    try:
        rank = float(rank)
    except (TypeError, ValueError):
        return ("#172033", "#25304a", "#8B95A8")

    if is_neutral_metric:
        return ("#172033", "#25304a", "#8B95A8")

    # Position 0 (best) to 1 (worst)
    pos = (rank - 1) / (n_total - 1)
    pos = max(0.0, min(1.0, pos))

    if pos <= 0.20:
        return ("rgba(62,168,102,0.30)", "rgba(62,168,102,0.55)", "#5FBE85")
    if pos <= 0.45:
        return ("rgba(62,168,102,0.18)", "rgba(62,168,102,0.40)", "#5FBE85")
    if pos <= 0.55:
        return ("#172033", "#25304a", "#8B95A8")
    if pos <= 0.80:
        return ("rgba(200,70,70,0.18)", "rgba(200,70,70,0.40)", "#E37070")
    return ("rgba(200,70,70,0.30)", "rgba(200,70,70,0.55)", "#E37070")


def metric_card_html(label: str, value: str, delta: str | None,
                       rank: int | None, n_total: int = 30,
                       is_neutral_metric: bool = False) -> str:
    """Generate HTML for a single metric card.

    Args:
        label: e.g. "ORtg"
        value: pre-formatted value as str, e.g. "119.8" or "55.1"
        delta: pre-formatted delta str including sign, e.g. "+4.2" or "+1.4pp", or None
        rank: 1..n_total, or None to disable color
        n_total: usually 30 (teams)
        is_neutral_metric: True for Pace etc. which have no "good" direction
    """
    bg, border, delta_color = _bg_for_rank(rank, n_total, is_neutral_metric)
    delta_html = ""
    if delta is not None and rank is not None:
        rank_str = f" · #{int(rank)}"
        delta_html = (
            f'<div style="font-size:10px;color:{delta_color};font-weight:500;'
            f'margin-top:2px;">{delta}{rank_str}</div>'
        )
    elif rank is not None:
        delta_html = (
            f'<div style="font-size:10px;color:{delta_color};font-weight:500;'
            f'margin-top:2px;">#{int(rank)}</div>'
        )
    return (
        f'<div style="background:{bg};border:1px solid {border};'
        f'border-radius:8px;padding:9px 10px;">'
        f'<div style="font-size:10px;color:#8B95A8;margin-bottom:2px;">{label}</div>'
        f'<div style="font-size:18px;color:#E5E9F0;font-weight:500;line-height:1.1;">{value}</div>'
        f'{delta_html}'
        f'</div>'
    )


def metric_cards_grid_html(cards_html: list[str], cols: int = 4) -> str:
    """Wrap a list of card HTML strings into a grid."""
    cards_str = "".join(cards_html)
    return (
        f'<div style="display:grid;grid-template-columns:repeat({cols},1fr);'
        f'gap:8px;margin-bottom:1rem;">{cards_str}</div>'
    )
