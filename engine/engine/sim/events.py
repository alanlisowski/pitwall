"""Safety-car event generation — pure module, no I/O.

A safety car compresses the field (gaps shrink each deployed lap) and
heavily discounts the pit-lane time loss (slow traffic → cheap stops).
Both effects are driven by the RaceSession's seeded RNG so races are
reproducible for tests and replays.

Public API
----------
SafetyCarWindow               — immutable lap range for a single SC period
generate_safety_car_schedule  — build the full race SC calendar from a seeded RNG
is_sc_active                  — bool query for a single lap
effective_pit_loss            — cfg.pit_loss, discounted when SC is active
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .config import SimConfig


@dataclass(frozen=True)
class SafetyCarWindow:
    """One safety-car period: active from start_lap through end_lap, inclusive."""
    start_lap: int
    end_lap: int


def generate_safety_car_schedule(
    total_laps: int,
    cfg: SimConfig,
    rng: random.Random,
) -> list[SafetyCarWindow]:
    """Roll a safety-car schedule for a full race.

    For each uncovered lap, draws a Bernoulli sample with probability
    cfg.sc_prob_per_lap.  When a SC triggers the window lasts between
    cfg.sc_min_duration and cfg.sc_max_duration laps (clamped to
    total_laps).  A new SC cannot start while one is already active.

    Returns:
        Sorted list of non-overlapping SafetyCarWindow objects.  May be empty.
    """
    windows: list[SafetyCarWindow] = []
    lap = 1
    while lap <= total_laps:
        if rng.random() < cfg.sc_prob_per_lap:
            duration = rng.randint(cfg.sc_min_duration, cfg.sc_max_duration)
            end = min(lap + duration - 1, total_laps)
            windows.append(SafetyCarWindow(start_lap=lap, end_lap=end))
            lap = end + 1
        else:
            lap += 1
    return windows


def is_sc_active(lap: int, schedule: list[SafetyCarWindow]) -> bool:
    """Return True if a safety car is active on the given lap."""
    return any(w.start_lap <= lap <= w.end_lap for w in schedule)


def effective_pit_loss(
    lap: int,
    schedule: list[SafetyCarWindow],
    cfg: SimConfig,
) -> float:
    """Return the effective pit-lane time loss for the given lap.

    Under an active safety car the normal pit_loss is multiplied by
    cfg.sc_pit_loss_factor, reflecting that slow traffic makes the pit
    delta much cheaper than in green-flag conditions.
    """
    if is_sc_active(lap, schedule):
        return cfg.pit_loss * cfg.sc_pit_loss_factor
    return cfg.pit_loss
