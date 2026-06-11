from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LapData:
    lap_number: int
    lap_time_s: float | None  # None for pit/SC/first laps with no valid time
    compound: str
    tyre_life: int
    stint: int
    is_pit_in_lap: bool
    is_pit_out_lap: bool


@dataclass
class DriverData:
    driver_number: str
    driver_code: str   # three-letter abbreviation, e.g. "VER"
    full_name: str
    team: str
    grid_position: int
    finishing_position: int
    laps: list[LapData] = field(default_factory=list)


@dataclass
class RaceData:
    year: int
    gp_name: str       # full event name, e.g. "Hungarian Grand Prix"
    gp_key: str        # FastF1 short identifier, e.g. "Hungary"
    circuit_name: str  # location, e.g. "Budapest"
    total_laps: int
    session_type: str  # "R", "Q", "S", etc.
    drivers: list[DriverData] = field(default_factory=list)
