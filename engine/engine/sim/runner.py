"""Lap-by-lap simulation loop.

Public entry point: :func:`simulate`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .components import lap_time as _lap_time
from .config import SimConfig
from .strategy import CarStrategy


@dataclass
class LapSnapshot:
    """State of one car at the end of one lap."""

    lap: int
    """Race lap (1-indexed)."""

    driver: str
    """Driver identifier matching :attr:`CarStrategy.driver`."""

    position: int
    """Running position at end of this lap (1 = leader)."""

    gap_to_leader: float
    """Cumulative time behind P1 at this lap (seconds).  Always 0.0 for P1."""

    compound: str
    """Compound driven on this lap (before any pit taken this lap)."""

    tyre_age: int
    """Laps already completed on this tyre set before this lap (0 = first lap
    on a fresh set).  The value fed into :func:`~.components.tyre_deg`."""

    lap_time: float
    """Time for this lap in seconds (includes pit_loss if pitted)."""

    total_time: float
    """Cumulative race time in seconds at the end of this lap."""

    pitted: bool
    """True if a pit stop was taken on this lap."""


@dataclass
class RaceResult:
    """Complete output of :func:`simulate`."""

    snapshots: list[LapSnapshot]
    """One entry per (driver × lap), in lap-then-position order.
    Total length = total_laps × number of cars."""

    finishing_order: list[str]
    """Driver codes ordered P1 → last, by cumulative race time."""

    total_times: dict[str, float]
    """Cumulative race time per driver in seconds."""


def simulate(
    strategies: list[CarStrategy],
    total_laps: int,
    cfg: SimConfig | None = None,
) -> RaceResult:
    """Simulate a race lap-by-lap and return the full result.

    The simulation:
    1. Advances one lap at a time for all cars simultaneously.
    2. Computes each car's lap time from the five independent components.
    3. Applies pit stops exactly on the declared lap (tyre change + pit loss).
    4. Recomputes running order by cumulative time after every lap.

    The undercut and overcut emerge naturally from the component model —
    they are not implemented explicitly.

    Args:
        strategies: One :class:`CarStrategy` per car.  Order does not affect
                    results (only tie-breaking where times are exactly equal).
        total_laps: Total race distance in laps.
        cfg: Tunable parameters.  Defaults to :class:`SimConfig` if None.

    Returns:
        A :class:`RaceResult` with snapshots, finishing order, and totals.
    """
    if cfg is None:
        cfg = SimConfig()

    # ------------------------------------------------------------------ #
    # Initialise mutable per-car state                                     #
    # compound / tyre_age = values to USE for the current lap's calculation
    # ------------------------------------------------------------------ #
    car_state: dict[str, dict] = {
        s.driver: {
            "compound":   s.start_compound,
            "tyre_age":   0,       # 0 = first lap on this set
            "total_time": 0.0,
        }
        for s in strategies
    }

    pit_plan: dict[str, dict[int, str]] = {
        s.driver: {stop.lap: stop.compound for stop in s.pit_stops}
        for s in strategies
    }

    base_paces: dict[str, float] = {s.driver: s.base_pace for s in strategies}
    driver_order = [s.driver for s in strategies]  # stable ordering for ties

    snapshots: list[LapSnapshot] = []

    for lap in range(1, total_laps + 1):
        # ---------------------------------------------------------------- #
        # Phase 1: compute lap times and accumulate, using pre-lap state    #
        # ---------------------------------------------------------------- #
        lap_data: dict[str, tuple[float, str, int, bool]] = {}
        # value = (lap_time, compound_driven, tyre_age_driven, pitted)

        for driver in driver_order:
            state = car_state[driver]
            compound_now = state["compound"]
            age_now      = state["tyre_age"]
            is_pit       = lap in pit_plan[driver]

            lt = _lap_time(
                car_pace=base_paces[driver],
                tyre_age=age_now,
                compound=compound_now,
                lap_number=lap,
                is_pit_lap=is_pit,
                cfg=cfg,
            )

            state["total_time"] += lt
            lap_data[driver] = (lt, compound_now, age_now, is_pit)

            # Update tyre state for the next lap
            if is_pit:
                state["compound"] = pit_plan[driver][lap]
                state["tyre_age"] = 0
            else:
                state["tyre_age"] = age_now + 1

        # ---------------------------------------------------------------- #
        # Phase 2: recompute running order and record snapshots             #
        # ---------------------------------------------------------------- #
        order = sorted(
            driver_order,
            key=lambda d: (car_state[d]["total_time"], driver_order.index(d)),
        )
        leader_time = car_state[order[0]]["total_time"]

        for pos, driver in enumerate(order, start=1):
            lt, compound_driven, age_driven, pitted = lap_data[driver]
            snapshots.append(
                LapSnapshot(
                    lap=lap,
                    driver=driver,
                    position=pos,
                    gap_to_leader=car_state[driver]["total_time"] - leader_time,
                    compound=compound_driven,
                    tyre_age=age_driven,
                    lap_time=lt,
                    total_time=car_state[driver]["total_time"],
                    pitted=pitted,
                )
            )

    finishing_order = sorted(
        driver_order,
        key=lambda d: (car_state[d]["total_time"], driver_order.index(d)),
    )

    return RaceResult(
        snapshots=snapshots,
        finishing_order=finishing_order,
        total_times={d: car_state[d]["total_time"] for d in driver_order},
    )
