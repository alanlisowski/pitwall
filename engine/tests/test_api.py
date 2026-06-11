"""API endpoint tests.

Uses FastAPI's TestClient (backed by httpx) with a temporary SQLite database
so no network calls, no FastF1, and no side effects on the dev database.
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

_RACE_ID = 1

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE races (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    year         INTEGER NOT NULL,
    gp_name      TEXT NOT NULL,
    gp_key       TEXT NOT NULL DEFAULT '',
    circuit      TEXT NOT NULL,
    total_laps   INTEGER NOT NULL,
    session_type TEXT NOT NULL DEFAULT 'R',
    UNIQUE(year, gp_name, session_type)
);
CREATE TABLE drivers (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id            INTEGER NOT NULL REFERENCES races(id),
    driver_number      TEXT NOT NULL,
    driver_code        TEXT NOT NULL,
    full_name          TEXT NOT NULL,
    team               TEXT NOT NULL,
    grid_position      INTEGER NOT NULL,
    finishing_position INTEGER NOT NULL,
    UNIQUE(race_id, driver_number)
);
CREATE TABLE laps (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_id      INTEGER NOT NULL REFERENCES drivers(id),
    lap_number     INTEGER NOT NULL,
    lap_time_s     REAL,
    compound       TEXT NOT NULL,
    tyre_life      INTEGER NOT NULL,
    stint          INTEGER NOT NULL,
    is_pit_in_lap  INTEGER NOT NULL DEFAULT 0,
    is_pit_out_lap INTEGER NOT NULL DEFAULT 0
);
"""


@pytest.fixture()
def test_db(tmp_path):
    """Temporary SQLite DB with one race, two drivers, and minimal lap data."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_SCHEMA_SQL)

    conn.execute(
        "INSERT INTO races (year, gp_name, gp_key, circuit, total_laps, session_type) "
        "VALUES (2024, 'Test GP', 'Test', 'Test Circuit', 5, 'R')"
    )
    # driver_id = 1
    conn.execute(
        "INSERT INTO drivers (race_id, driver_number, driver_code, full_name, team, "
        "grid_position, finishing_position) VALUES (1, '1', 'DRV', 'Driver A', 'Team A', 1, 1)"
    )
    # driver_id = 2
    conn.execute(
        "INSERT INTO drivers (race_id, driver_number, driver_code, full_name, team, "
        "grid_position, finishing_position) VALUES (1, '2', 'DRB', 'Driver B', 'Team B', 2, 2)"
    )

    # DRV: SOFT laps 1-3 (pit on 3), HARD laps 4-5
    conn.executemany(
        "INSERT INTO laps (driver_id, lap_number, lap_time_s, compound, tyre_life, "
        "stint, is_pit_in_lap, is_pit_out_lap) VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, 1, 91.0, "SOFT", 1, 1, 0, 0),
            (1, 2, 91.5, "SOFT", 2, 1, 0, 0),
            (1, 3, 112.0, "SOFT", 3, 1, 1, 0),  # pit-in lap
            (1, 4, 91.2, "HARD", 1, 2, 0, 1),   # pit-out lap
            (1, 5, 91.3, "HARD", 2, 2, 0, 0),
        ],
    )
    # DRB: MEDIUM all 5 laps, no pit
    conn.executemany(
        "INSERT INTO laps (driver_id, lap_number, lap_time_s, compound, tyre_life, "
        "stint, is_pit_in_lap, is_pit_out_lap) VALUES (?,?,?,?,?,?,?,?)",
        [(2, i, 91.0 + i * 0.1, "MEDIUM", i, 1, 0, 0) for i in range(1, 6)],
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def client(test_db, monkeypatch):
    import api.main as m

    monkeypatch.setattr(m, "_DB_PATH", test_db)
    with TestClient(m.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /races
# ---------------------------------------------------------------------------

def test_list_races_returns_ingested_race(client):
    r = client.get("/races")
    assert r.status_code == 200
    races = r.json()
    assert len(races) == 1
    assert races[0]["gp_name"] == "Test GP"
    assert races[0]["total_laps"] == 5
    assert races[0]["id"] == _RACE_ID


def test_list_races_empty_db(tmp_path, monkeypatch):
    """An uninitialised (schema-only) database returns an empty list."""
    import api.main as m

    empty_db = tmp_path / "empty.db"
    monkeypatch.setattr(m, "_DB_PATH", empty_db)
    with TestClient(m.app) as c:
        r = c.get("/races")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# GET /races/{id}/baseline
# ---------------------------------------------------------------------------

def test_baseline_unknown_race_returns_404(client):
    r = client.get("/races/999/baseline")
    assert r.status_code == 404


def test_baseline_structure(client):
    r = client.get(f"/races/{_RACE_ID}/baseline")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"race", "config", "strategies", "result"}

    # 5 laps × 2 drivers = 10 snapshots
    assert len(data["result"]["snapshots"]) == 10
    assert len(data["result"]["finishing_order"]) == 2
    assert set(data["result"]["total_times"].keys()) == {"DRV", "DRB"}

    # Strategies carry real pit-stop data
    by_driver = {s["driver"]: s for s in data["strategies"]}
    assert "DRV" in by_driver
    assert len(by_driver["DRV"]["pit_stops"]) == 1
    assert by_driver["DRV"]["pit_stops"][0]["compound"] == "HARD"


# ---------------------------------------------------------------------------
# POST /simulate
# ---------------------------------------------------------------------------

_TWO_CARS = [
    {
        "driver": "CAR1",
        "base_pace": 90.0,
        "start_compound": "MEDIUM",
        "pit_stops": [{"lap": 3, "compound": "HARD"}],
    },
    {
        "driver": "CAR2",
        "base_pace": 90.5,
        "start_compound": "SOFT",
        "pit_stops": [],
    },
]


def test_simulate_returns_full_result(client):
    r = client.post("/simulate", json={"race_id": _RACE_ID, "strategies": _TWO_CARS})
    assert r.status_code == 200
    data = r.json()
    # 5 laps × 2 cars = 10 snapshots
    assert len(data["snapshots"]) == 10
    assert set(data["finishing_order"]) == {"CAR1", "CAR2"}
    assert set(data["total_times"].keys()) == {"CAR1", "CAR2"}


def test_simulate_positions_cover_1_to_n_each_lap(client):
    r = client.post("/simulate", json={"race_id": _RACE_ID, "strategies": _TWO_CARS})
    snaps = r.json()["snapshots"]
    for lap in range(1, 6):
        lap_positions = sorted(s["position"] for s in snaps if s["lap"] == lap)
        assert lap_positions == [1, 2]


def test_simulate_unknown_race_returns_404(client):
    r = client.post("/simulate", json={"race_id": 999, "strategies": _TWO_CARS})
    assert r.status_code == 404


def test_simulate_custom_config_applied(client):
    """A higher pit_loss should make the pit car slower relative to default."""
    base_body = {"race_id": _RACE_ID, "strategies": _TWO_CARS}
    default_r = client.post("/simulate", json=base_body).json()

    high_loss_body = {
        "race_id": _RACE_ID,
        "strategies": _TWO_CARS,
        "config": {"pit_loss": 40.0},
    }
    high_loss_r = client.post("/simulate", json=high_loss_body).json()

    # CAR1 pits on lap 3; higher pit_loss means a worse total time for it
    default_car1 = default_r["total_times"]["CAR1"]
    high_loss_car1 = high_loss_r["total_times"]["CAR1"]
    assert high_loss_car1 > default_car1


# ---------------------------------------------------------------------------
# POST /compare
# ---------------------------------------------------------------------------

_STRATEGY_A = [
    {"driver": "X", "base_pace": 89.0, "start_compound": "SOFT", "pit_stops": []},
    {"driver": "Y", "base_pace": 91.0, "start_compound": "MEDIUM", "pit_stops": []},
]
_STRATEGY_B = [
    {"driver": "X", "base_pace": 91.0, "start_compound": "HARD", "pit_stops": []},
    {"driver": "Y", "base_pace": 89.5, "start_compound": "MEDIUM", "pit_stops": []},
]


def test_compare_returns_both_results_and_deltas(client):
    body = {
        "race_id": _RACE_ID,
        "strategy_a": _STRATEGY_A,
        "strategy_b": _STRATEGY_B,
    }
    r = client.post("/compare", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "result_a" in data
    assert "result_b" in data
    assert "deltas" in data
    assert len(data["deltas"]) == 2  # X and Y


def test_compare_delta_reflects_outcome(client):
    """X wins strategy_a but loses strategy_b — the delta should capture this."""
    body = {
        "race_id": _RACE_ID,
        "strategy_a": _STRATEGY_A,
        "strategy_b": _STRATEGY_B,
        "config": {"fuel_effect": 0.0, "deg_soft": 0.0, "deg_medium": 0.0, "deg_hard": 0.0},
    }
    r = client.post("/compare", json=body).json()

    # strategy_a: X pace 89+offset_soft=-0.8 → 88.2 effective; Y pace 91+offset_medium=-0.4 → 90.6 → X wins
    assert r["result_a"]["finishing_order"][0] == "X"
    # strategy_b: X pace 91+offset_hard=0 → 91; Y pace 89.5+offset_medium=-0.4 → 89.1 → Y wins
    assert r["result_b"]["finishing_order"][0] == "Y"

    x_delta = next(d for d in r["deltas"] if d["driver"] == "X")
    # X is P1 in A, P2 in B → position_delta = 1 - 2 = -1 (higher position number = worse)
    assert x_delta["position_delta"] == -1  # a was P1, b was P2


def test_compare_unknown_race_returns_404(client):
    body = {"race_id": 999, "strategy_a": _STRATEGY_A, "strategy_b": _STRATEGY_B}
    r = client.post("/compare", json=body)
    assert r.status_code == 404
