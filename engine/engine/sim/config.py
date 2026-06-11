"""Simulation configuration.

All tunable parameters live here so they can be swapped in tests and
re-calibrated against real race data without touching the simulation logic.

Defaults are grounded in published F1 engineering data and the ranges noted
in engine/CALIBRATION.md.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimConfig:
    # ------------------------------------------------------------------ #
    # Tyre degradation  (seconds added per lap, linear in tyre age)        #
    # tyre_age = 0 on the first lap with a set → zero deg penalty           #
    # ------------------------------------------------------------------ #
    deg_soft: float = 0.130
    """Soft compound: ~0.10–0.15 s/lap per lap of tyre age."""

    deg_medium: float = 0.075
    """Medium compound: ~0.06–0.10 s/lap per lap of tyre age."""

    deg_hard: float = 0.045
    """Hard compound: ~0.03–0.06 s/lap per lap of tyre age."""

    # ------------------------------------------------------------------ #
    # Compound pace offsets  (s/lap relative to HARD when fresh)           #
    # Negative = faster.  Soft-to-hard typical gap: 0.6–1.0 s/lap.        #
    # ------------------------------------------------------------------ #
    offset_soft: float = -0.80
    """Soft is ~0.8 s/lap faster than Hard on a fresh set."""

    offset_medium: float = -0.40
    """Medium is ~0.4 s/lap faster than Hard on a fresh set."""

    offset_hard: float = 0.00
    """Hard is the baseline (no offset)."""

    # ------------------------------------------------------------------ #
    # Pit-lane time loss                                                    #
    # Total additional seconds from pit entry to pit exit rejoining.       #
    # Circuit-dependent: Monaco ~25s, Silverstone ~22s, Monza ~18s.        #
    # ------------------------------------------------------------------ #
    pit_loss: float = 22.0
    """Pit-lane penalty in seconds."""

    # ------------------------------------------------------------------ #
    # Fuel burn                                                             #
    # An F1 car starts with ~110 kg and burns ~2 kg/lap.  Each lap the     #
    # lighter car improves its lap time by fuel_effect seconds.             #
    # ------------------------------------------------------------------ #
    fuel_effect: float = 0.040
    """Lap-time improvement per lap driven (s/lap), from fuel mass loss."""

    # ------------------------------------------------------------------ #
    # Lookup helpers                                                        #
    # ------------------------------------------------------------------ #
    def deg_rate(self, compound: str) -> float:
        """Return degradation rate (s/lap per lap of age) for a compound."""
        c = compound.upper()
        if c == "SOFT":
            return self.deg_soft
        if c == "MEDIUM":
            return self.deg_medium
        if c == "HARD":
            return self.deg_hard
        raise ValueError(f"Unknown compound {compound!r}. Expected SOFT, MEDIUM, or HARD.")

    def pace_offset(self, compound: str) -> float:
        """Return pace offset (s/lap, negative = faster) for a compound."""
        c = compound.upper()
        if c == "SOFT":
            return self.offset_soft
        if c == "MEDIUM":
            return self.offset_medium
        if c == "HARD":
            return self.offset_hard
        raise ValueError(f"Unknown compound {compound!r}. Expected SOFT, MEDIUM, or HARD.")
