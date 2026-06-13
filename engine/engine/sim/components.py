"""Five independent lap-time components — each a pure, side-effect-free function.

The total lap time for a car on a given lap is the sum of all five:

    lap_time = base_pace(car_pace)
             + tyre_deg(tyre_age, compound, cfg)
             + compound_offset(compound, cfg)
             + fuel_saving(lap_number, cfg)   # negative → faster
             + pit_penalty(is_pit_lap, cfg)   # 0 or cfg.pit_loss
             + cfg.pace_delta(pace_setting)   # negative = faster
"""
from __future__ import annotations

from .config import PaceSetting, SimConfig


def base_pace(car_pace: float) -> float:
    """Return the car's intrinsic lap time in seconds."""
    return car_pace


def tyre_deg(tyre_age: float, compound: str, cfg: SimConfig) -> float:
    """Return the tyre-degradation penalty in seconds.

    Below cfg.cliff_lap(compound) the penalty is linear in tyre_age.
    Above the cliff the degradation rate is multiplied by cfg.cliff_factor,
    modelling the thermal cliff seen on older rubber.

    tyre_age accepts float to accommodate fractional effective ages that
    accumulate when a pace setting's wear multiplier is not 1.0.

    Args:
        tyre_age: Effective laps already completed on this tyre set before
                  the current lap.  0.0 on the very first lap with a set.
        compound: "SOFT", "MEDIUM", or "HARD".
        cfg: Simulation configuration.
    """
    rate = cfg.deg_rate(compound)
    cliff = cfg.cliff_lap(compound)
    if tyre_age <= cliff:
        return rate * tyre_age
    return rate * cliff + rate * cfg.cliff_factor(compound) * (tyre_age - cliff)


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
    tyre_age: float,
    compound: str,
    lap_number: int,
    is_pit_lap: bool,
    cfg: SimConfig,
    pace_setting: PaceSetting = PaceSetting.NEUTRAL,
) -> float:
    """Combine all five components plus the pace-dial delta into a lap time.

    Keyword-only arguments prevent accidental positional mis-ordering.

    Args:
        tyre_age: Effective tyre age (float); incorporates wear multipliers
                  accumulated by the runner when pace_setting != NEUTRAL.
        pace_setting: Current pace instruction.  NEUTRAL (default) leaves
                      lap time and wear rate unchanged.
    """
    return (
        base_pace(car_pace)
        + tyre_deg(tyre_age, compound, cfg)
        + compound_offset(compound, cfg)
        + fuel_saving(lap_number, cfg)
        + pit_penalty(is_pit_lap, cfg)
        + cfg.pace_delta(pace_setting)
    )
