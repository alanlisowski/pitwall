"""Input types for the simulation: a per-car strategy."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PitStop:
    """A single pit stop taken by one car."""

    lap: int
    """Race lap on which the stop is taken (1-indexed)."""

    compound: str
    """New compound fitted at this stop (SOFT / MEDIUM / HARD)."""


@dataclass
class CarStrategy:
    """Everything the simulator needs to know about one car."""

    driver: str
    """Unique identifier — typically a three-letter driver code."""

    base_pace: float
    """Baseline lap time in seconds (no tyre, fuel, or pit effects)."""

    start_compound: str
    """Compound at race start."""

    pit_stops: list[PitStop] = field(default_factory=list)
    """Ordered list of pit stops.  Empty = one-stop-free strategy."""
