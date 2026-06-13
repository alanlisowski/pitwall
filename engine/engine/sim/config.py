"""Simulation configuration.

All tunable parameters live here so they can be swapped in tests and
re-calibrated against real race data without touching the simulation logic.

Defaults are grounded in published F1 engineering data and the ranges noted
in engine/CALIBRATION.md.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class PaceSetting(enum.Enum):
    """Five-level pace dial for Race Engineer live mode.

    Each level applies a lap-time delta and a tyre-wear multiplier.
    The wear multiplier scales how fast effective tyre age accumulates;
    pushing brings the tyre cliff forward, conserving delays it.
    """

    PUSH_HARD = "PUSH_HARD"
    PUSH = "PUSH"
    NEUTRAL = "NEUTRAL"
    CONSERVE = "CONSERVE"
    CONSERVE_HARD = "CONSERVE_HARD"


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
    # Tyre cliff — non-linear degradation acceleration                      #
    # Below cliff_lap: pure linear.  Above: rate × cliff_factor per lap.   #
    # Softer compounds hit the cliff sooner (lower lap threshold).          #
    # ------------------------------------------------------------------ #
    cliff_lap_soft: int = 16
    """Soft compound: cliff at ~16 laps (hot conditions, high grip demand)."""

    cliff_lap_medium: int = 28
    """Medium compound: cliff at ~28 laps."""

    cliff_lap_hard: int = 42
    """Hard compound: cliff at ~42 laps."""

    cliff_factor_soft: float = 2.5
    """Soft post-cliff deg multiplier (rate × 2.5 above cliff_lap_soft)."""

    cliff_factor_medium: float = 2.0
    """Medium post-cliff deg multiplier."""

    cliff_factor_hard: float = 1.8
    """Hard post-cliff deg multiplier."""

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
    # Pace dial — per-level lap-time deltas (s/lap, negative = faster)     #
    # ------------------------------------------------------------------ #
    pace_push_hard_delta: float = -0.40
    pace_push_delta: float = -0.20
    pace_neutral_delta: float = 0.00
    pace_conserve_delta: float = 0.30
    pace_conserve_hard_delta: float = 0.60

    # ------------------------------------------------------------------ #
    # Pace dial — per-level tyre-wear multipliers                          #
    # Applied to effective_tyre_age accumulation each lap.                 #
    # PUSH_HARD at 1.8× means 10 laps of pushing = 18 laps of wear.       #
    # ------------------------------------------------------------------ #
    pace_push_hard_wear: float = 1.8
    pace_push_wear: float = 1.3
    pace_neutral_wear: float = 1.0
    pace_conserve_wear: float = 0.7
    pace_conserve_hard_wear: float = 0.5

    # ------------------------------------------------------------------ #
    # Safety car                                                           #
    # ------------------------------------------------------------------ #
    sc_prob_per_lap: float = 0.015
    """Probability (0–1) that a safety car deploys on any given lap.
    Set to 0.0 in a SimConfig to disable safety cars entirely."""

    sc_min_duration: int = 3
    """Minimum number of laps a safety car period lasts."""

    sc_max_duration: int = 5
    """Maximum number of laps a safety car period lasts."""

    sc_gap_compress_factor: float = 0.30
    """Fraction of each following car's gap that closes per SC lap (0–1).
    Applied multiplicatively each lap: gap_new = gap * (1 – factor)."""

    sc_pit_loss_factor: float = 0.35
    """Pit-lane loss multiplier under a safety car.
    Effective pit loss = pit_loss × factor (slow traffic makes stops cheap).
    At defaults, 22s × 0.35 ≈ 7.7s — roughly the real SC pit delta."""

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

    def cliff_lap(self, compound: str) -> int:
        """Return the tyre-age lap at which the cliff begins for a compound."""
        c = compound.upper()
        if c == "SOFT":
            return self.cliff_lap_soft
        if c == "MEDIUM":
            return self.cliff_lap_medium
        if c == "HARD":
            return self.cliff_lap_hard
        raise ValueError(f"Unknown compound {compound!r}. Expected SOFT, MEDIUM, or HARD.")

    def cliff_factor(self, compound: str) -> float:
        """Return the post-cliff degradation multiplier for a compound."""
        c = compound.upper()
        if c == "SOFT":
            return self.cliff_factor_soft
        if c == "MEDIUM":
            return self.cliff_factor_medium
        if c == "HARD":
            return self.cliff_factor_hard
        raise ValueError(f"Unknown compound {compound!r}. Expected SOFT, MEDIUM, or HARD.")

    def pace_delta(self, setting: PaceSetting) -> float:
        """Return lap-time delta (s/lap) for a pace setting."""
        _map = {
            PaceSetting.PUSH_HARD:     self.pace_push_hard_delta,
            PaceSetting.PUSH:          self.pace_push_delta,
            PaceSetting.NEUTRAL:       self.pace_neutral_delta,
            PaceSetting.CONSERVE:      self.pace_conserve_delta,
            PaceSetting.CONSERVE_HARD: self.pace_conserve_hard_delta,
        }
        return _map[setting]

    def wear_multiplier(self, setting: PaceSetting) -> float:
        """Return effective-tyre-age accumulation rate for a pace setting."""
        _map = {
            PaceSetting.PUSH_HARD:     self.pace_push_hard_wear,
            PaceSetting.PUSH:          self.pace_push_wear,
            PaceSetting.NEUTRAL:       self.pace_neutral_wear,
            PaceSetting.CONSERVE:      self.pace_conserve_wear,
            PaceSetting.CONSERVE_HARD: self.pace_conserve_hard_wear,
        }
        return _map[setting]
