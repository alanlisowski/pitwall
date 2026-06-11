"""Five independent lap-time components — each a pure, side-effect-free function.

The total lap time for a car on a given lap is the sum of all five:

    lap_time = base_pace(car_pace)
             + tyre_deg(tyre_age, compound, cfg)
             + compound_offset(compound, cfg)
             + fuel_saving(lap_number, cfg)   # negative → faster
             + pit_penalty(is_pit_lap, cfg)   # 0 or cfg.pit_loss
"""
from __future__ import annotations

from .config import SimConfig


def base_pace(car_pace: float) -> float:
    """Return the car's intrinsic lap time in seconds.

    This is the floor — the time a perfectly fresh car on a neutral
    compound would lap without any tyre, fuel, or pit effects.
    """
    return car_pace


def tyre_deg(tyre_age: int, compound: str, cfg: SimConfig) -> float:
    """Return the tyre-degradation penalty in seconds.

    Degrades linearly with age.  A fresh tyre (tyre_age=0) has zero
    penalty; each additional lap of use adds cfg.deg_rate(compound).

    Args:
        tyre_age: Laps already completed on this tyre set before the
                  current lap.  0 on the very first lap with a set.
        compound: "SOFT", "MEDIUM", or "HARD".
        cfg: Simulation configuration.
    """
    return cfg.deg_rate(compound) * tyre_age


def compound_offset(compound: str, cfg: SimConfig) -> float:
    """Return the fixed pace delta for a compound relative to HARD.

    Negative values mean faster.  Softer compounds are quicker when
    fresh but degrade more steeply (captured separately by tyre_deg).
    """
    return cfg.pace_offset(compound)


def fuel_saving(lap_number: int, cfg: SimConfig) -> float:
    """Return the fuel-burn contribution to lap time (negative = faster).

    At lap 1 the tank is full and there is no improvement yet.  Each
    subsequent lap the car is lighter by ~2 kg, improving lap time by
    cfg.fuel_effect seconds per lap.

    Args:
        lap_number: Current race lap, 1-indexed.
        cfg: Simulation configuration.
    """
    return -(lap_number - 1) * cfg.fuel_effect


def pit_penalty(is_pit_lap: bool, cfg: SimConfig) -> float:
    """Return the pit-lane time loss when a stop is taken, else 0."""
    return cfg.pit_loss if is_pit_lap else 0.0


def lap_time(
    *,
    car_pace: float,
    tyre_age: int,
    compound: str,
    lap_number: int,
    is_pit_lap: bool,
    cfg: SimConfig,
) -> float:
    """Combine all five components into a single lap time (seconds).

    Keyword-only arguments prevent accidental positional mis-ordering.
    """
    return (
        base_pace(car_pace)
        + tyre_deg(tyre_age, compound, cfg)
        + compound_offset(compound, cfg)
        + fuel_saving(lap_number, cfg)
        + pit_penalty(is_pit_lap, cfg)
    )
