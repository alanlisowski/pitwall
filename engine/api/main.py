"""PitWall FastAPI application.

Run from engine/ with the venv active:

    uvicorn api.main:app --reload

Environment variables:
    PITWALL_DB      Path to the SQLite database file.
                    Defaults to engine/pitwall.db (relative to the package).
    CORS_ORIGINS    Comma-separated list of allowed origins.
                    Defaults to the local Vite dev server.
"""
from __future__ import annotations

import json as _json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from engine.calibration import TUNED_CFG, build_baseline_strategies, load_real_race
from engine.db import DEFAULT_DB, connect, init_db
from engine.sim import (
    AiProfile,
    CarStrategy,
    PitAction,
    PitStop,
    PlayerAction,
    RaceResult,
    RaceSession,
    RaceState,
    SimConfig,
    simulate,
)
from engine.sim.config import PaceSetting

from .models import (
    AdvanceRequest,
    BaselineResponse,
    CarStateSchema,
    CarStrategySchema,
    CompareRequest,
    CompareResponse,
    DriverDelta,
    DriverSchema,
    LapSnapshotSchema,
    RaceResultSchema,
    RaceStateSchema,
    RaceSummary,
    SessionEventSchema,
    SimConfigSchema,
    SimulateRequest,
    StartRaceRequest,
    StartRaceResponse,
    TrackResponse,
)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

_DB_PATH: Path = Path(os.environ.get("PITWALL_DB", str(DEFAULT_DB)))

_CORS_ORIGINS: list[str] = os.environ.get(
    "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")


# ---------------------------------------------------------------------------
# Lifespan: initialise DB schema on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    with connect(_DB_PATH) as conn:
        init_db(conn)
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PitWall API",
    version="0.1.0",
    description="F1 race strategy simulation — lap-by-lap engine via HTTP.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# In-memory session store for Race Engineer Mode.
# Sessions are lost if the process restarts (e.g. a sleeping free-tier dyno
# will drop them on wake). Persisting seed + action list for deterministic
# replay is a future option.
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, RaceSession] = {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_race(race_id: int) -> dict:
    """Return the races row for *race_id* or raise 404."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM races WHERE id=?", (race_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Race {race_id} not found.")
    return dict(row)


def _fetch_drivers(race_id: int) -> list[DriverSchema]:
    """Return driver metadata rows for *race_id*, ordered by finishing position."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT driver_code, full_name, team, team_colour, "
            "grid_position, finishing_position "
            "FROM drivers WHERE race_id=? ORDER BY finishing_position",
            (race_id,),
        ).fetchall()
    finally:
        conn.close()
    return [DriverSchema(**dict(r)) for r in rows]


def _schema_to_engine_cfg(schema: SimConfigSchema | None) -> SimConfig:
    if schema is None:
        return TUNED_CFG
    return SimConfig(**schema.model_dump())


def _schema_to_engine_strategies(schemas: list[CarStrategySchema]) -> list[CarStrategy]:
    return [
        CarStrategy(
            driver=s.driver,
            base_pace=s.base_pace,
            start_compound=s.start_compound,
            pit_stops=[PitStop(lap=p.lap, compound=p.compound) for p in s.pit_stops],
        )
        for s in schemas
    ]


def _difficulty_to_profile(difficulty: str) -> AiProfile:
    if difficulty == "easy":
        return AiProfile.easy()
    if difficulty == "hard":
        return AiProfile.hard()
    return AiProfile.medium()


def _race_state_to_schema(state: RaceState) -> RaceStateSchema:
    return RaceStateSchema(
        lap=state.lap,
        total_laps=state.total_laps,
        cars=[
            CarStateSchema(
                driver=c.driver,
                position=c.position,
                gap_to_leader=c.gap_to_leader,
                compound=c.compound,
                tyre_age=c.tyre_age,
                total_time=c.total_time,
                pace_setting=c.pace_setting.value,
                pitted_this_lap=c.pitted_this_lap,
                current_lap_time=c.current_lap_time,
            )
            for c in state.cars
        ],
        events=[
            SessionEventSchema(lap=e.lap, kind=e.kind.value, driver=e.driver)
            for e in state.events
        ],
        finished=state.finished,
        sc_active=state.sc_active,
    )


def _engine_result_to_schema(result: RaceResult) -> RaceResultSchema:
    return RaceResultSchema(
        snapshots=[
            LapSnapshotSchema(
                lap=s.lap,
                driver=s.driver,
                position=s.position,
                gap_to_leader=s.gap_to_leader,
                compound=s.compound,
                tyre_age=s.tyre_age,
                lap_time=s.lap_time,
                total_time=s.total_time,
                pitted=s.pitted,
            )
            for s in result.snapshots
        ],
        finishing_order=result.finishing_order,
        total_times=result.total_times,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/races", response_model=list[RaceSummary])
def list_races() -> list[RaceSummary]:
    """List all races ingested into the local database."""
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, year, gp_name, gp_key, circuit, total_laps, session_type "
            "FROM races ORDER BY year, gp_name"
        ).fetchall()
    finally:
        conn.close()
    return [RaceSummary(**dict(r)) for r in rows]


@app.get("/races/{race_id}/baseline", response_model=BaselineResponse)
def get_baseline(race_id: int) -> BaselineResponse:
    """Return the tuned baseline config, reconstructed strategies, and simulated result.

    The strategies are derived from the real pit stops stored in SQLite; base
    pace is back-estimated by reversing the model equations on valid laps.
    This endpoint is the reference point for the /compare flow.
    """
    row = _fetch_race(race_id)

    real = load_real_race(row["year"], row["gp_name"], db_path=_DB_PATH)
    cfg = TUNED_CFG
    strategies = build_baseline_strategies(real, cfg)
    result = simulate(strategies, total_laps=row["total_laps"], cfg=cfg)
    drivers = _fetch_drivers(race_id)

    return BaselineResponse(
        race=RaceSummary(**{k: row[k] for k in RaceSummary.model_fields}),
        config=SimConfigSchema(**asdict(cfg)),
        strategies=[
            CarStrategySchema(
                driver=s.driver,
                base_pace=s.base_pace,
                start_compound=s.start_compound,  # type: ignore[arg-type]
                pit_stops=[
                    {"lap": p.lap, "compound": p.compound} for p in s.pit_stops  # type: ignore[misc]
                ],
            )
            for s in strategies
        ],
        result=_engine_result_to_schema(result),
        drivers=drivers,
    )


@app.get("/races/{race_id}/track", response_model=TrackResponse)
def get_track(race_id: int) -> TrackResponse:
    """Return the circuit's normalised centre-line polyline.

    Points are ``[x, y]`` pairs scaled so the longest axis spans [0, 1]
    with aspect ratio preserved.  An empty list means no telemetry was
    captured at ingestion time.
    """
    row = _fetch_race(race_id)  # raises 404 if unknown
    raw = row.get("track_points")
    points: list[list[float]] = _json.loads(raw) if raw else []
    return TrackResponse(race_id=race_id, points=points)


@app.post("/simulate", response_model=RaceResultSchema)
def run_simulate(body: SimulateRequest) -> RaceResultSchema:
    """Simulate a race with a custom strategy set.

    The race's *total_laps* is read from the database; the caller supplies
    one CarStrategy per car.  Omit *config* to use the tuned calibration defaults.
    """
    row = _fetch_race(body.race_id)
    cfg = _schema_to_engine_cfg(body.config)
    strategies = _schema_to_engine_strategies(body.strategies)
    result = simulate(strategies, total_laps=row["total_laps"], cfg=cfg)
    return _engine_result_to_schema(result)


@app.post("/compare", response_model=CompareResponse)
def run_compare(body: CompareRequest) -> CompareResponse:
    """Simulate two strategy sets and return both results plus a per-driver delta.

    *strategy_a* and *strategy_b* must cover the same set of drivers so that
    the deltas are meaningful, but the endpoint does not enforce this — missing
    drivers receive a position/time of -1/0 in the delta.
    """
    row = _fetch_race(body.race_id)
    cfg = _schema_to_engine_cfg(body.config)
    total_laps = row["total_laps"]

    result_a = simulate(_schema_to_engine_strategies(body.strategy_a), total_laps=total_laps, cfg=cfg)
    result_b = simulate(_schema_to_engine_strategies(body.strategy_b), total_laps=total_laps, cfg=cfg)

    pos_a = {d: i + 1 for i, d in enumerate(result_a.finishing_order)}
    pos_b = {d: i + 1 for i, d in enumerate(result_b.finishing_order)}
    all_drivers = sorted(set(result_a.finishing_order) | set(result_b.finishing_order))

    deltas = [
        DriverDelta(
            driver=d,
            position_a=pos_a.get(d, -1),
            position_b=pos_b.get(d, -1),
            position_delta=pos_a.get(d, 0) - pos_b.get(d, 0),
            time_a=result_a.total_times.get(d, 0.0),
            time_b=result_b.total_times.get(d, 0.0),
            time_delta=result_a.total_times.get(d, 0.0) - result_b.total_times.get(d, 0.0),
        )
        for d in all_drivers
    ]

    return CompareResponse(
        result_a=_engine_result_to_schema(result_a),
        result_b=_engine_result_to_schema(result_b),
        deltas=deltas,
    )


# ---------------------------------------------------------------------------
# Race Engineer Mode endpoints
# ---------------------------------------------------------------------------

@app.post("/race/start", response_model=StartRaceResponse)
def start_race(body: StartRaceRequest) -> StartRaceResponse:
    """Create a new interactive race session.

    Loads real pit-stop data from the database to build rival strategies,
    sets the chosen driver as the player, then advances to the first
    decision point and returns the session id plus initial state.
    """
    row = _fetch_race(body.race_id)
    real = load_real_race(row["year"], row["gp_name"], db_path=_DB_PATH)
    cfg = TUNED_CFG
    strategies = build_baseline_strategies(real, cfg)

    driver_codes = {s.driver for s in strategies}
    if body.driver_id not in driver_codes:
        raise HTTPException(
            status_code=404,
            detail=f"Driver {body.driver_id!r} not found in race {body.race_id}.",
        )

    profile = _difficulty_to_profile(body.difficulty)
    ai_profiles = {s.driver: profile for s in strategies if s.driver != body.driver_id}

    session = RaceSession(
        cars=strategies,
        total_laps=row["total_laps"],
        player_id=body.driver_id,
        cfg=cfg,
        seed=body.seed,
        ai_profiles=ai_profiles,
    )
    session_id = uuid.uuid4().hex
    _SESSIONS[session_id] = session

    return StartRaceResponse(session_id=session_id, state=_race_state_to_schema(session.grid_state()))


@app.post("/race/{session_id}/step", response_model=RaceStateSchema)
def step_race(session_id: str, body: AdvanceRequest) -> RaceStateSchema:
    """Apply the player's decision and advance exactly one lap.

    Unlike /advance, this never loops to the next decision point.
    Calling this on an already-finished session is safe and returns the
    terminal state unchanged.
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found.")

    action = PlayerAction(
        pit=PitAction(compound=body.pit_compound) if body.pit_compound else None,
        pace=PaceSetting(body.pace),
    )
    try:
        session.decide(action)
    except RuntimeError:
        pass

    return _race_state_to_schema(session.step_lap())


@app.post("/race/{session_id}/advance", response_model=RaceStateSchema)
def advance_race(session_id: str, body: AdvanceRequest) -> RaceStateSchema:
    """Apply the player's decision and advance to the next decision point.

    If *pit_compound* is set the player pits on the very next lap.
    *pace* adjusts the tyre-wear dial from the next lap onwards.
    Calling this on an already-finished session is safe and returns the
    terminal state unchanged.
    """
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found.")

    action = PlayerAction(
        pit=PitAction(compound=body.pit_compound) if body.pit_compound else None,
        pace=PaceSetting(body.pace),
    )
    try:
        session.decide(action)
    except RuntimeError:
        pass  # race already finished; advance() will return the terminal state

    return _race_state_to_schema(session.advance())
