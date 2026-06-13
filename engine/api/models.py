"""Pydantic request/response schemas for the PitWall API.

All types are shared between requests and responses.  Engine dataclasses are
converted to/from these schemas at the API boundary; the engine itself never
sees Pydantic models.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class PitStopSchema(BaseModel):
    lap: int
    compound: Literal["SOFT", "MEDIUM", "HARD"]


class CarStrategySchema(BaseModel):
    driver: str
    base_pace: float
    start_compound: Literal["SOFT", "MEDIUM", "HARD"]
    pit_stops: list[PitStopSchema] = []


class SimConfigSchema(BaseModel):
    """Mirrors SimConfig — all fields optional so callers can omit unknowns."""

    deg_soft: float = 0.130
    deg_medium: float = 0.075
    deg_hard: float = 0.045
    offset_soft: float = -0.80
    offset_medium: float = -0.40
    offset_hard: float = 0.00
    pit_loss: float = 22.0
    fuel_effect: float = 0.040


# ---------------------------------------------------------------------------
# Race metadata
# ---------------------------------------------------------------------------

class RaceSummary(BaseModel):
    id: int
    year: int
    gp_name: str
    gp_key: str
    circuit: str
    total_laps: int
    session_type: str


class DriverSchema(BaseModel):
    """Driver metadata with constructor colour — returned alongside race data."""
    driver_code: str
    full_name: str
    team: str
    team_colour: str
    grid_position: int
    finishing_position: int


class TrackResponse(BaseModel):
    race_id: int
    points: list[list[float]]


# ---------------------------------------------------------------------------
# Simulation output
# ---------------------------------------------------------------------------

class LapSnapshotSchema(BaseModel):
    lap: int
    driver: str
    position: int
    gap_to_leader: float
    compound: str
    tyre_age: int
    lap_time: float
    total_time: float
    pitted: bool


class RaceResultSchema(BaseModel):
    snapshots: list[LapSnapshotSchema]
    finishing_order: list[str]
    total_times: dict[str, float]


# ---------------------------------------------------------------------------
# Endpoint-specific request/response bodies
# ---------------------------------------------------------------------------

class BaselineResponse(BaseModel):
    race: RaceSummary
    config: SimConfigSchema
    strategies: list[CarStrategySchema]
    result: RaceResultSchema
    drivers: list[DriverSchema] = []


class SimulateRequest(BaseModel):
    race_id: int
    strategies: list[CarStrategySchema]
    config: SimConfigSchema | None = None


class DriverDelta(BaseModel):
    driver: str
    position_a: int
    position_b: int
    """Positive → driver finishes higher in strategy A."""
    position_delta: int
    time_a: float
    time_b: float
    time_delta: float
    """Positive → strategy A was slower for this driver."""


class CompareRequest(BaseModel):
    race_id: int
    strategy_a: list[CarStrategySchema]
    strategy_b: list[CarStrategySchema]
    config: SimConfigSchema | None = None


class CompareResponse(BaseModel):
    result_a: RaceResultSchema
    result_b: RaceResultSchema
    deltas: list[DriverDelta]


# ---------------------------------------------------------------------------
# Race Engineer Mode (interactive session)
# ---------------------------------------------------------------------------

class CarStateSchema(BaseModel):
    driver: str
    position: int
    gap_to_leader: float
    compound: str
    tyre_age: float
    total_time: float
    pace_setting: str
    pitted_this_lap: bool
    current_lap_time: float = 0.0


class SessionEventSchema(BaseModel):
    lap: int
    kind: str
    driver: str


class RaceStateSchema(BaseModel):
    lap: int
    total_laps: int
    cars: list[CarStateSchema]
    events: list[SessionEventSchema]
    finished: bool
    sc_active: bool


class StartRaceRequest(BaseModel):
    race_id: int
    driver_id: str
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    seed: int = 42


class StartRaceResponse(BaseModel):
    session_id: str
    state: RaceStateSchema


class AdvanceRequest(BaseModel):
    pit_compound: Literal["SOFT", "MEDIUM", "HARD"] | None = None
    pace: Literal["PUSH_HARD", "PUSH", "NEUTRAL", "CONSERVE", "CONSERVE_HARD"] = "NEUTRAL"
