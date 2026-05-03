"""Chart helpers for Team Stats and Player Stats.

Used by the Table | Chart toggle. The chart view shows a sortable bar chart
across teams or players for a single user-selected stat.
"""
from __future__ import annotations

from typing import Callable, Iterable

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def stat_picker(specs: list[tuple[str, str, Callable]],
                 default_col: str | None = None,
                 key: str = "stat_picker") -> str:
    """Render a dropdown for choosing which stat to chart.

    Returns the column name (not the label).
    """
    options = [(col, label) for col, label, _ in specs]
    labels_only = [label for _, label in options]

    default_idx = 0
    if default_col:
        for i, (col, _) in enumerate(options):
            if col == default_col:
                default_idx = i
                break

    chosen_label = st.selectbox(
        "Stat to chart",
        labels_only,
        index=default_idx,
        key=key,
    )
    # Reverse-lookup the column name
    for col, label in options:
        if label == chosen_label:
            return col
    return options[0][0]


def bar_chart(df: pd.DataFrame,
               value_col: str,
               label_col: str,
               value_label: str,
               lower_is_better: bool = False,
               sort_desc: bool = True,
               max_bars: int = 30,
               highlight_avg: float | None = None,
               format_str: str = ".1f") -> go.Figure:
    """Build a horizontal bar chart for one stat across multiple entities.

    Args:
        df: DataFrame containing the value_col and label_col
        value_col: column name with numeric values
        label_col: column name with display labels (e.g. team abbr or player name)
        value_label: human-readable name for the stat (axis title)
        lower_is_better: invert the colour ramp (red high, green low)
        sort_desc: order bars descending. Combined with lower_is_better it
                   shows worst-at-top so eye lands on the best at bottom.
        max_bars: cap to top N rows (after sort)
        highlight_avg: if provided, draws a vertical reference line
        format_str: format spec for the value display, e.g. ".1f", ".0f"

    Returns a Plotly figure ready for st.plotly_chart.
    """
    df = df[[value_col, label_col]].copy()
    df = df.dropna(subset=[value_col])
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", x=0.5, y=0.5, xref="paper", yref="paper",
                            showarrow=False, font=dict(color="#8B95A8"))
        fig.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)",
                            plot_bgcolor="rgba(0,0,0,0)")
        return fig

    # Sort: descending by default. For "lower is better" we still sort desc
    # so worst is on top, best is on bottom — eye scans down to the leader
    df = df.sort_values(value_col, ascending=not sort_desc).head(max_bars)

    # Color ramp by rank within the visible bars
    n = len(df)
    ranks = pd.Series(range(n), index=df.index)
    # Normalize 0..1, then to the diverging colors green→amber→red
    if n <= 1:
        norm = pd.Series([0.5] * n, index=df.index)
    else:
        norm = ranks / (n - 1)
    if lower_is_better:
        norm = 1 - norm

    def _color_at(t: float) -> str:
        # 0=green, 0.5=amber, 1=red
        if t < 0.5:
            # green → amber
            r = int(95 + (244 - 95) * (t * 2))
            g = int(190 + (167 - 190) * (t * 2))
            b = int(133 + (66 - 133) * (t * 2))
        else:
            # amber → red
            t2 = (t - 0.5) * 2
            r = int(244 + (227 - 244) * t2)
            g = int(167 + (112 - 167) * t2)
            b = int(66 + (112 - 66) * t2)
        return f"rgb({r},{g},{b})"

    colors = [_color_at(t) for t in norm]

    # Sort visually: best at TOP of the chart (meaning sorted ascending order
    # in the bar plot, since plotly draws bottom→top)
    df = df.sort_values(value_col, ascending=lower_is_better)
    # Re-color in the new order
    n2 = len(df)
    if n2 <= 1:
        norm2 = pd.Series([0.5] * n2, index=df.index)
    else:
        norm2 = pd.Series(range(n2), index=df.index) / (n2 - 1)
    if lower_is_better:
        norm2 = 1 - norm2
    else:
        norm2 = 1 - norm2  # last bar (top) should be best
    colors = [_color_at(t) for t in norm2]

    fmt = "{:" + format_str + "}"

    fig = go.Figure(go.Bar(
        x=df[value_col],
        y=df[label_col],
        orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[fmt.format(v) for v in df[value_col]],
        textposition="outside",
        textfont=dict(color="#E5E9F0", size=11),
        hovertemplate=f"<b>%{{y}}</b><br>{value_label}: %{{x:{format_str}}}<extra></extra>",
    ))

    if highlight_avg is not None and pd.notna(highlight_avg):
        fig.add_vline(
            x=highlight_avg,
            line=dict(color="#F4A742", width=1, dash="dash"),
            annotation_text=f"Avg {fmt.format(highlight_avg)}",
            annotation_position="top",
            annotation_font=dict(color="#F4A742", size=10),
        )

    height = max(280, 24 * n + 80)
    fig.update_layout(
        height=min(height, 900),
        margin=dict(l=10, r=40, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            title=value_label,
            color="#8B95A8",
            gridcolor="#25304a",
            zerolinecolor="#25304a",
        ),
        yaxis=dict(
            color="#E5E9F0",
            tickfont=dict(size=11),
        ),
        showlegend=False,
        hoverlabel=dict(bgcolor="#172033", bordercolor="#25304a",
                         font=dict(color="#E5E9F0")),
    )
    return fig


def column_multiselect(specs: list[tuple[str, str, Callable]],
                        key: str = "col_select") -> list[str]:
    """Render a multi-select for choosing which stat columns to display.

    Returns a list of column names to keep (in spec order). Default = all.
    """
    label_to_col = {label: col for col, label, _ in specs}
    all_labels = list(label_to_col.keys())
    chosen = st.multiselect(
        "Columns to show",
        all_labels,
        default=all_labels,
        key=key,
        help="Uncheck columns to hide them. Identity columns (Team / Player) always visible.",
    )
    return [label_to_col[lbl] for lbl in chosen]
