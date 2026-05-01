"""Shared filter widgets — keep the look consistent across pages."""
from __future__ import annotations

import streamlit as st

WINDOWS = ["L5", "L10", "L20", "Season"]
DEFAULT_WINDOW = "L10"

LAYERS = ["Traditional", "Advanced", "Offence", "Defence"]


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
