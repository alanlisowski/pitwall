"""Rule-based AI strategy for non-player cars.

Pure module — no I/O, no mutation of shared state, no look-ahead.
Each AI car sees only what has already happened (same fog of war as the player).

Heuristics (evaluated in priority order each lap):
  1. Tyre cliff imminent  — box before the degradation cliff hits.
  2. Cover an undercut    — a nearby rival just pitted; match them to protect
                           track position.
  3. Planned pit window   — nominal strategy window opens; time the stop.
  4. Pace dial            — push to close a gap, conserve to extend a lead.

Difficulty scales how proactively and optimally the AI applies these rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import PaceSetting, SimConfig


# --------------------------------------------------------------------------- #
# Public data types                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class AiCarView:
    """One car's observable state at the start of a lap (fog-of-war snapshot)."""
    driver: str
    position: int
    gap_to_leader: float    # seconds, 0.0 for the leader
    compound: str
    tyre_age: float         # effective laps on current set
    pace_setting: PaceSetting
    pitted_last_lap: bool
    sc_active: bool = False  # safety car deployed on this lap


@dataclass
class AiDecision:
    """What an AI car will do on the upcoming lap."""
    pit_compound: Optional[str] = None   # None = no pit this lap
    pace: PaceSetting = PaceSetting.NEUTRAL


@dataclass
class AiProfile:
    """Controls how optimal and aggressive the AI is.

    Lower difficulty → reacts late to the cliff, ignores undercuts, over-pushes.
    Higher difficulty → proactive cliff management, covers undercuts cleanly.
    """

    cliff_reaction_laps: int = 3
    """Box this many effective laps BEFORE the cliff.  0 = pit at the cliff."""

    covers_undercut: bool = True
    """React when a nearby rival pits (undercut threat)."""

    undercut_cover_gap: float = 3.0
    """A rival within this many seconds (pre-pit gap) triggers undercut cover."""

    pit_window: int = 3
    """Acceptable range around each planned stop (±laps)."""

    push_gap_threshold: float = 2.0
    """PUSH when trailing a car by fewer than this many seconds."""

    conserve_lead_threshold: float = 5.0
    """CONSERVE when leading the next car by more than this many seconds."""

    no_pit_final_laps: int = 8
    """Do not pit in the final N laps of the race."""

    pits_under_sc: bool = True
    """Opportunistically take a cheap stop when the safety car is active."""

    @classmethod
    def easy(cls) -> AiProfile:
        """Reacts late to the cliff, over-pushes tyres, ignores undercuts."""
        return cls(
            cliff_reaction_laps=0,
            covers_undercut=False,
            pit_window=1,
            push_gap_threshold=15.0,    # almost always in PUSH mode
            conserve_lead_threshold=50.0,
            no_pit_final_laps=3,
            pits_under_sc=False,
        )

    @classmethod
    def medium(cls) -> AiProfile:
        """Reasonable timing, does not cover undercuts."""
        return cls(
            cliff_reaction_laps=1,
            covers_undercut=False,
            pit_window=2,
            push_gap_threshold=4.0,
            conserve_lead_threshold=8.0,
            no_pit_final_laps=6,
        )

    @classmethod
    def hard(cls) -> AiProfile:
        """Nails windows, covers undercuts, manages pace cleanly."""
        return cls(
            cliff_reaction_laps=3,
            covers_undercut=True,
            undercut_cover_gap=3.0,
            pit_window=3,
            push_gap_threshold=2.0,
            conserve_lead_threshold=5.0,
            no_pit_final_laps=8,
        )


# --------------------------------------------------------------------------- #
# Core decision function                                                        #
# --------------------------------------------------------------------------- #

def ai_action(
    me: AiCarView,
    field: list[AiCarView],   # all cars sorted P1 first (includes self)
    lap: int,
    total_laps: int,
    planned_pits: dict[int, str],   # reference strategy: lap → compound
    cfg: SimConfig,
    profile: AiProfile,
) -> AiDecision:
    """Decide what the AI car does on the upcoming lap.

    Pure function — takes a snapshot of the race and returns a decision.
    ``planned_pits`` is a reference only; the AI may deviate from it.
    """
    laps_remaining = total_laps - lap
    too_late = laps_remaining < profile.no_pit_final_laps

    pit_compound: str | None = None

    if not too_late:
        # 0. Cheap stop under Safety Car — opportunistic free pitstop
        if profile.pits_under_sc and me.sc_active:
            pit_compound = _planned_compound(lap, planned_pits)

        if pit_compound is None:
            cliff = cfg.cliff_lap(me.compound)
            laps_to_cliff = cliff - me.tyre_age

            # 1. Tyre cliff — non-negotiable safety stop
            if laps_to_cliff <= profile.cliff_reaction_laps:
                pit_compound = _planned_compound(lap, planned_pits)

        # 2. Cover an undercut — a rival behind us just pitted
        if pit_compound is None and profile.covers_undercut:
            pit_compound = _check_undercut(me, field, planned_pits, lap, cfg, profile)

        # 3. Planned pit window — execute the nominal strategy
        if pit_compound is None:
            pit_compound = _check_window(lap, planned_pits, profile)

    return AiDecision(
        pit_compound=pit_compound,
        pace=_pace_setting(me, field, profile),
    )


# --------------------------------------------------------------------------- #
# Private helpers                                                               #
# --------------------------------------------------------------------------- #

def _planned_compound(lap: int, planned_pits: dict[int, str]) -> str:
    """Return the compound for the next planned stop at or after `lap`."""
    future = {l: c for l, c in planned_pits.items() if l >= lap}
    return future[min(future)] if future else "HARD"


def _check_undercut(
    me: AiCarView,
    field: list[AiCarView],
    planned_pits: dict[int, str],
    lap: int,
    cfg: SimConfig,
    profile: AiProfile,
) -> str | None:
    """Return a pit compound if a rival behind us is an undercut threat, else None.

    The pre-pit gap is approximated by subtracting cfg.pit_loss from the
    current gap — the rival's gap grew by roughly pit_loss when they stopped.
    """
    for car in field:
        if car.driver == me.driver or not car.pitted_last_lap:
            continue
        if car.position <= me.position:
            continue  # rival is AHEAD — not an undercut threat from behind
        gap = car.gap_to_leader - me.gap_to_leader   # positive = rival is behind
        pre_pit_gap = gap - cfg.pit_loss
        if 0 < pre_pit_gap <= profile.undercut_cover_gap:
            return _planned_compound(lap, planned_pits)
    return None


def _check_window(
    lap: int,
    planned_pits: dict[int, str],
    profile: AiProfile,
) -> str | None:
    """Return the planned compound if the current lap falls inside a pit window."""
    for planned_lap, compound in planned_pits.items():
        lo = planned_lap - profile.pit_window
        hi = planned_lap + profile.pit_window
        if lo <= lap <= hi:
            return compound
    return None


def _pace_setting(
    me: AiCarView,
    field: list[AiCarView],
    profile: AiProfile,
) -> PaceSetting:
    """Choose a pace dial based on gaps to immediately adjacent cars."""
    car_ahead = next((c for c in field if c.position == me.position - 1), None)
    car_behind = next((c for c in field if c.position == me.position + 1), None)

    if car_ahead is not None:
        gap_ahead = me.gap_to_leader - car_ahead.gap_to_leader  # >0 = they lead
        if gap_ahead < profile.push_gap_threshold:
            return PaceSetting.PUSH

    if car_behind is not None:
        gap_behind = car_behind.gap_to_leader - me.gap_to_leader  # >0 = we lead
        if gap_behind > profile.conserve_lead_threshold:
            return PaceSetting.CONSERVE

    return PaceSetting.NEUTRAL
