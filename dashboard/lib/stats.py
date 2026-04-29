"""Stat layer definitions — the four-layer split applied to teams + players.

Each layer maps to a list of (column_in_dataframe, display_label, formatter) tuples.
Pages call `team_layer_columns(layer)` and `player_layer_columns(layer)` to know
which columns to show.
"""
from __future__ import annotations

from typing import Callable

from .format import fmt_int, fmt_num, fmt_pct

# (df_col, label, formatter)
ColSpec = tuple[str, str, Callable]


# =========================================================================
# TEAM LAYERS
# =========================================================================

TEAM_LAYERS: dict[str, list[ColSpec]] = {
    "Traditional": [
        ("gp",      "GP",   fmt_int),
        ("w",       "W",    fmt_int),
        ("l",       "L",    fmt_int),
        ("pts",     "PTS",  fmt_num),
        ("reb",     "REB",  fmt_num),
        ("ast",     "AST",  fmt_num),
        ("stl",     "STL",  fmt_num),
        ("blk",     "BLK",  fmt_num),
        ("tov",     "TOV",  fmt_num),
        ("fg_pct",  "FG%",  fmt_pct),
        ("fg3_pct", "3P%",  fmt_pct),
        ("ft_pct",  "FT%",  fmt_pct),
    ],
    "Advanced": [
        ("gp",         "GP",   fmt_int),
        ("off_rating", "ORtg", fmt_num),
        ("def_rating", "DRtg", fmt_num),
        ("net_rating", "NetRtg", fmt_num),
        ("pace",       "Pace", fmt_num),
        ("efg_pct",    "eFG%", fmt_pct),
        ("ts_pct",     "TS%",  fmt_pct),
        ("tov_pct",    "TOV%", fmt_num),
        ("oreb_pct",   "OREB%", fmt_num),
        ("dreb_pct",   "DREB%", fmt_num),
        ("ast_pct",    "AST%", fmt_num),
    ],
    "Offence": [
        ("gp",         "GP",   fmt_int),
        ("pts",        "PTS",  fmt_num),
        ("off_rating", "ORtg", fmt_num),
        ("efg_pct",    "eFG%", fmt_pct),
        ("ts_pct",     "TS%",  fmt_pct),
        ("fga",        "FGA",  fmt_num),
        ("fg3a",       "3PA",  fmt_num),
        ("fg3_pct",    "3P%",  fmt_pct),
        ("ast",        "AST",  fmt_num),
        ("ast_pct",    "AST%", fmt_num),
        ("oreb",       "OREB", fmt_num),
        ("oreb_pct",   "OREB%", fmt_num),
        ("tov_pct",    "TOV%", fmt_num),
    ],
    "Defence": [
        ("gp",         "GP",   fmt_int),
        ("opp_pts",    "OPP PTS", fmt_num),
        ("def_rating", "DRtg", fmt_num),
        ("opp_efg_pct", "OPP eFG%", fmt_pct),
        ("opp_ts_pct",  "OPP TS%",  fmt_pct),
        ("opp_fg3_pct", "OPP 3P%",  fmt_pct),
        ("opp_fg3a",    "OPP 3PA",  fmt_num),
        ("dreb",        "DREB", fmt_num),
        ("dreb_pct",    "DREB%", fmt_num),
        ("stl",         "STL",  fmt_num),
        ("blk",         "BLK",  fmt_num),
        ("opp_tov_pct", "OPP TOV%", fmt_num),
    ],
}


# =========================================================================
# PLAYER LAYERS
# =========================================================================

PLAYER_LAYERS: dict[str, list[ColSpec]] = {
    "Traditional": [
        ("gp",      "GP",   fmt_int),
        ("starts",  "GS",   fmt_int),
        ("minutes", "MIN",  fmt_num),
        ("pts",     "PTS",  fmt_num),
        ("reb",     "REB",  fmt_num),
        ("ast",     "AST",  fmt_num),
        ("stl",     "STL",  fmt_num),
        ("blk",     "BLK",  fmt_num),
        ("tov",     "TOV",  fmt_num),
        ("fg_pct",  "FG%",  fmt_pct),
        ("fg3_pct", "3P%",  fmt_pct),
        ("ft_pct",  "FT%",  fmt_pct),
    ],
    "Advanced": [
        ("gp",         "GP",   fmt_int),
        ("minutes",    "MIN",  fmt_num),
        ("off_rating", "ORtg", fmt_num),
        ("def_rating", "DRtg", fmt_num),
        ("net_rating", "NetRtg", fmt_num),
        ("usg_pct",    "USG%", fmt_num),
        ("efg_pct",    "eFG%", fmt_pct),
        ("ts_pct",     "TS%",  fmt_pct),
        ("pie",        "PIE",  fmt_num),
    ],
    "Offence": [
        ("gp",      "GP",   fmt_int),
        ("minutes", "MIN",  fmt_num),
        ("pts",     "PTS",  fmt_num),
        ("usg_pct", "USG%", fmt_num),
        ("efg_pct", "eFG%", fmt_pct),
        ("ts_pct",  "TS%",  fmt_pct),
        ("fga",     "FGA",  fmt_num),
        ("fg3a",    "3PA",  fmt_num),
        ("fg3_pct", "3P%",  fmt_pct),
        ("ast",     "AST",  fmt_num),
    ],
    "Defence": [
        ("gp",      "GP",   fmt_int),
        ("minutes", "MIN",  fmt_num),
        ("def_rating", "DRtg", fmt_num),
        ("stl",     "STL",  fmt_num),
        ("blk",     "BLK",  fmt_num),
        ("reb",     "REB",  fmt_num),
        ("tov",     "TOV",  fmt_num),
    ],
}


def team_layer_columns(layer: str) -> list[ColSpec]:
    return TEAM_LAYERS.get(layer, TEAM_LAYERS["Traditional"])


def player_layer_columns(layer: str) -> list[ColSpec]:
    return PLAYER_LAYERS.get(layer, PLAYER_LAYERS["Traditional"])
