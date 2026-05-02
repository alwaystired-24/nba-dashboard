"""Shared filter widgets — keep the look consistent across pages."""
from __future__ import annotations

import streamlit as st

WINDOWS = ["L5", "L10", "L20", "Season"]
DEFAULT_WINDOW = "L10"

LAYERS = ["Traditional", "Advanced", "Offence", "Defence"]

SEASON_FILTER_LABELS = {
    "reg": "Regular Season",
    "playoffs": "Playoffs",
    "both": "Both",
}
SEASON_FILTER_DEFAULT = "reg"  # Reg season is what matters most for trend analysis


def window_picker(key: str = "form_window", default: str = DEFAULT_WINDOW) -> str:
    """Render the form-window radio. Returns the selected window."""
    return st.radio(
        "Form window",
        options=WINDOWS,
        index=WINDOWS.index(default),
        horizontal=True,
        key=key,
    )


def layer_picker(key: str = "stat_layer", default: str = "Traditional") -> str:
    return st.radio(
        "Stat layer",
        options=LAYERS,
        index=LAYERS.index(default),
        horizontal=True,
        key=key,
    )


def season_filter_picker(key: str = "global_season_filter") -> str:
    """Render the season-type filter. Persists across pages via st.session_state.

    Returns the internal value: 'reg' | 'playoffs' | 'both'.
    """
    # Initialize session state if first visit
    if key not in st.session_state:
        st.session_state[key] = SEASON_FILTER_DEFAULT

    labels = list(SEASON_FILTER_LABELS.values())
    keys_list = list(SEASON_FILTER_LABELS.keys())
    current_label = SEASON_FILTER_LABELS[st.session_state[key]]
    chosen = st.radio(
        "Season filter",
        options=labels,
        index=labels.index(current_label),
        horizontal=True,
        key=f"{key}_radio",
        help="Filter all stats by season type. Affects every page.",
    )
    # Map back to internal value and persist
    chosen_internal = keys_list[labels.index(chosen)]
    st.session_state[key] = chosen_internal
    return chosen_internal
