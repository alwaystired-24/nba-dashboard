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
                              n_total: int = 30) -> "pd.io.formats.style.Styler":
    """Color each value cell by its sibling rank column.

    Args:
        df: DataFrame to style. May contain rank columns alongside value columns.
        rank_columns: mapping of {value_column_name: rank_column_name}.
                      e.g., {"pts": "pts_rank", "off_rating": "off_rating_rank"}
        n_total: total population size (e.g., 30 for teams, total player count
                 for players).

    Returns a Styler. Just pass to st.dataframe.
    """
    def color_row(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
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
