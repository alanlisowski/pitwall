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

import os
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from engine.calibration import TUNED_CFG, build_baseline_strategies, load_real_race
from engine.db import DEFAULT_DB, connect, init_db
from engine.sim import CarStrategy, PitStop, RaceResult, SimConfig, simulate

from .models import (
    BaselineResponse,
    CarStrategySchema,
    CompareRequest,
    CompareResponse,
    DriverDelta,
    LapSnapshotSchema,
    RaceResultSchema,
    RaceSummary,
    SimConfigSchema,
    SimulateRequest,
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
    )


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
