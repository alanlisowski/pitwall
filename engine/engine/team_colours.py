"""Official F1 constructor colours (2024 season).

One source of truth — import ``team_colour()`` wherever a hex colour is needed.
"""
from __future__ import annotations

# Keyed by the team name strings FastF1 returns in session.laps["Team"].
TEAM_COLOURS: dict[str, str] = {
    "Red Bull Racing": "#3671C6",
    "McLaren": "#FF8000",
    "Ferrari": "#E8002D",
    "Mercedes": "#27F4D2",
    "Aston Martin": "#229971",
    "Alpine": "#0093CC",
    "Williams": "#64C4FF",
    "Racing Bulls": "#6692FF",
    "Kick Sauber": "#52E252",
    "Haas F1 Team": "#B6BABD",
    # FastF1 name variants across seasons
    "AlphaTauri": "#6692FF",
    "RB": "#6692FF",
    "Alfa Romeo": "#C92D4B",
    "Sauber": "#52E252",
    "Haas": "#B6BABD",
}

_DEFAULT = "#FFFFFF"


def team_colour(team_name: str) -> str:
    """Return the official hex colour for *team_name*, or white if unknown."""
    return TEAM_COLOURS.get(team_name, _DEFAULT)
