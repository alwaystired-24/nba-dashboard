"""Team logo URLs and color helpers.

ESPN serves logos at predictable URLs by NBA abbreviation. We cache the
nba_api team_id -> ESPN abbr mapping locally to avoid a runtime lookup.
"""
from __future__ import annotations


# nba_api team_id -> ESPN abbreviation (used in CDN URL paths)
NBA_TEAM_TO_ESPN_ABBR = {
    1610612737: "atl",   # Atlanta Hawks
    1610612738: "bos",   # Boston Celtics
    1610612739: "cle",   # Cleveland Cavaliers
    1610612740: "no",    # New Orleans Pelicans
    1610612741: "chi",   # Chicago Bulls
    1610612742: "dal",   # Dallas Mavericks
    1610612743: "den",   # Denver Nuggets
    1610612744: "gs",    # Golden State Warriors
    1610612745: "hou",   # Houston Rockets
    1610612746: "lac",   # Los Angeles Clippers
    1610612747: "lal",   # Los Angeles Lakers
    1610612748: "mia",   # Miami Heat
    1610612749: "mil",   # Milwaukee Bucks
    1610612750: "min",   # Minnesota Timberwolves
    1610612751: "bkn",   # Brooklyn Nets
    1610612752: "ny",    # New York Knicks
    1610612753: "orl",   # Orlando Magic
    1610612754: "ind",   # Indiana Pacers
    1610612755: "phi",   # Philadelphia 76ers
    1610612756: "phx",   # Phoenix Suns
    1610612757: "por",   # Portland Trail Blazers
    1610612758: "sac",   # Sacramento Kings
    1610612759: "sa",    # San Antonio Spurs
    1610612760: "okc",   # Oklahoma City Thunder
    1610612761: "tor",   # Toronto Raptors
    1610612762: "utah",  # Utah Jazz
    1610612763: "mem",   # Memphis Grizzlies
    1610612764: "wsh",   # Washington Wizards
    1610612765: "det",   # Detroit Pistons
    1610612766: "cha",   # Charlotte Hornets
}


def team_logo_url(team_id: int, size: int = 500) -> str:
    """Return ESPN CDN URL for a team logo. size in {500, 250, 110, 28}."""
    abbr = NBA_TEAM_TO_ESPN_ABBR.get(team_id)
    if not abbr:
        return ""
    return f"https://a.espncdn.com/i/teamlogos/nba/{size}/{abbr}.png"
