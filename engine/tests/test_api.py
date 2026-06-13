"""API endpoint tests.

Uses FastAPI's TestClient (backed by httpx) with a temporary SQLite database
so no network calls, no FastF1, and no side effects on the dev database.
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

_RACE_ID = 1

_TRACK_POINTS = [[0.0, 0.0], [0.5, 0.5], [1.0, 0.0]]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_db(tmp_path):
    """Temporary SQLite DB with one race, two drivers, and minimal lap data."""
    from engine.db import init_db

    db = tmp_path / "test.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    init_db(conn)

    conn.execute(
        "INSERT INTO races (year, gp_name, gp_key, circuit, total_laps, session_type, track_points) "
        "VALUES (2024, 'Test GP', 'Test', 'Test Circuit', 5, 'R', ?)",
        (json.dumps(_TRACK_POINTS),),
    )
    # driver_id = 1
    conn.execute(
        "INSERT INTO drivers (race_id, driver_number, driver_code, full_name, team, "
        "team_colour, grid_position, finishing_position) "
        "VALUES (1, '1', 'DRV', 'Driver A', 'Team A', '#FF0000', 1, 1)"
    )
    # driver_id = 2
    conn.execute(
        "INSERT INTO drivers (race_id, driver_number, driver_code, full_name, team, "
        "team_colour, grid_position, finishing_position) "
        "VALUES (1, '2', 'DRB', 'Driver B', 'Team B', '#0000FF', 2, 2)"
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
    assert set(data.keys()) >= {"race", "config", "strategies", "result", "drivers"}

    # 5 laps × 2 drivers = 10 snapshots
    assert len(data["result"]["snapshots"]) == 10
    assert len(data["result"]["finishing_order"]) == 2
    assert set(data["result"]["total_times"].keys()) == {"DRV", "DRB"}

    # Strategies carry real pit-stop data
    by_driver = {s["driver"]: s for s in data["strategies"]}
    assert "DRV" in by_driver
    assert len(by_driver["DRV"]["pit_stops"]) == 1
    assert by_driver["DRV"]["pit_stops"][0]["compound"] == "HARD"


def test_baseline_drivers_include_team_colour(client):
    data = client.get(f"/races/{_RACE_ID}/baseline").json()
    drivers = {d["driver_code"]: d for d in data["drivers"]}
    assert set(drivers.keys()) == {"DRV", "DRB"}
    assert drivers["DRV"]["team_colour"] == "#FF0000"
    assert drivers["DRB"]["team_colour"] == "#0000FF"
    assert drivers["DRV"]["team"] == "Team A"


# ---------------------------------------------------------------------------
# GET /races/{id}/track
# ---------------------------------------------------------------------------

def test_track_returns_normalised_points(client):
    r = client.get(f"/races/{_RACE_ID}/track")
    assert r.status_code == 200
    data = r.json()
    assert data["race_id"] == _RACE_ID
    assert data["points"] == _TRACK_POINTS


def test_track_unknown_race_returns_404(client):
    r = client.get("/races/999/track")
    assert r.status_code == 404


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


# ---------------------------------------------------------------------------
# POST /race/start  +  POST /race/{session_id}/advance
# ---------------------------------------------------------------------------
# Test DB recap:
#   DRV — SOFT start, pits on lap 3 → HARD  (is_pit_in_lap=1 on lap 3)
#   DRB — MEDIUM start, no pit stops
#
# When player=DRB the AI (DRV) pits on lap 3, creating a RIVAL_PITTED decision
# point, so start returns a non-finished state and we can exercise advance().

def test_start_race_returns_session_id_and_initial_state(client):
    r = client.post("/race/start", json={
        "race_id": _RACE_ID,
        "driver_id": "DRB",
        "difficulty": "easy",
        "seed": 0,
    })
    assert r.status_code == 200
    data = r.json()

    assert isinstance(data["session_id"], str) and len(data["session_id"]) > 0

    state = data["state"]
    assert state["total_laps"] == 5
    assert state["lap"] >= 1
    assert len(state["cars"]) == 2
    positions = sorted(c["position"] for c in state["cars"])
    assert positions == [1, 2]
    assert isinstance(state["finished"], bool)
    assert isinstance(state["sc_active"], bool)
    assert isinstance(state["events"], list)


def test_start_race_unknown_race_returns_404(client):
    r = client.post("/race/start", json={"race_id": 999, "driver_id": "DRB"})
    assert r.status_code == 404


def test_start_race_unknown_driver_returns_404(client):
    r = client.post("/race/start", json={"race_id": _RACE_ID, "driver_id": "NOBODY"})
    assert r.status_code == 404


def test_advance_drives_race_to_finish(client):
    """Start a race and keep advancing until finished; verify terminal state."""
    start = client.post("/race/start", json={
        "race_id": _RACE_ID,
        "driver_id": "DRB",
        "seed": 42,
    }).json()
    session_id = start["session_id"]
    state = start["state"]

    steps = 0
    while not state["finished"]:
        r = client.post(f"/race/{session_id}/advance", json={})
        assert r.status_code == 200
        state = r.json()
        steps += 1
        assert steps < 20, "race should finish within 20 advance() calls"

    assert state["finished"]
    assert state["lap"] == 5
    positions = sorted(c["position"] for c in state["cars"])
    assert positions == [1, 2]
    # Gap to leader for P1 is 0; everyone else is positive
    leader = next(c for c in state["cars"] if c["position"] == 1)
    assert leader["gap_to_leader"] == 0.0


def test_advance_unknown_session_returns_404(client):
    r = client.post("/race/BADSESSIONID/advance", json={})
    assert r.status_code == 404


def test_advance_with_pit_changes_player_compound(client):
    """Queuing a pit via advance changes the player's compound by the final lap.

    AiProfile.easy() has no_pit_final_laps=3 so the AI DRV pits within the
    5-lap window, giving us a decision point before the race finishes.
    """
    start = client.post("/race/start", json={
        "race_id": _RACE_ID,
        "driver_id": "DRB",
        "difficulty": "easy",
        "seed": 0,
    }).json()
    session_id = start["session_id"]
    state = start["state"]

    # Queue a pit on the first advance call; if the race somehow already finished
    # (extremely unlikely with easy difficulty) the test is still safe.
    r = client.post(f"/race/{session_id}/advance", json={"pit_compound": "HARD"})
    assert r.status_code == 200
    state = r.json()

    # Drive to finish
    while not state["finished"]:
        state = client.post(f"/race/{session_id}/advance", json={}).json()

    drb = next(c for c in state["cars"] if c["driver"] == "DRB")
    assert drb["compound"] == "HARD"


def test_advance_after_finish_returns_stable_terminal_state(client):
    """Calling advance() on a finished session is safe and idempotent."""
    start = client.post("/race/start", json={
        "race_id": _RACE_ID,
        "driver_id": "DRB",
        "seed": 1,
    }).json()
    session_id = start["session_id"]
    state = start["state"]
    while not state["finished"]:
        state = client.post(f"/race/{session_id}/advance", json={}).json()

    # Extra advance after finish — must not crash and must still be finished
    r = client.post(f"/race/{session_id}/advance", json={})
    assert r.status_code == 200
    extra = r.json()
    assert extra["finished"]
    assert extra["lap"] == 5
    # Times must not change
    times_first = {c["driver"]: c["total_time"] for c in state["cars"]}
    times_extra = {c["driver"]: c["total_time"] for c in extra["cars"]}
    assert times_first == times_extra


def test_advance_with_pace_setting_accepted(client):
    """Pace settings other than NEUTRAL are accepted without error."""
    start = client.post("/race/start", json={
        "race_id": _RACE_ID,
        "driver_id": "DRB",
        "seed": 7,
    }).json()
    session_id = start["session_id"]

    r = client.post(f"/race/{session_id}/advance", json={"pace": "PUSH_HARD"})
    assert r.status_code == 200
    assert "cars" in r.json()


def test_advance_cars_expose_current_lap_time(client):
    """Each CarState must carry a positive current_lap_time after the first advance."""
    start = client.post("/race/start", json={
        "race_id": _RACE_ID,
        "driver_id": "DRB",
        "seed": 3,
    }).json()
    state = start["state"]
    for car in state["cars"]:
        assert "current_lap_time" in car
        assert car["current_lap_time"] > 0.0


def test_rival_pit_event_reported_during_session(client):
    """DRV (AI, easy difficulty) pits during the 5-lap race; its RIVAL_PITTED
    event must appear somewhere across all advance() calls."""
    start = client.post("/race/start", json={
        "race_id": _RACE_ID,
        "driver_id": "DRB",
        "difficulty": "easy",  # no_pit_final_laps=3 → AI pits within 5 laps
        "seed": 0,
    }).json()
    session_id = start["session_id"]

    all_events = list(start["state"]["events"])
    state = start["state"]
    while not state["finished"]:
        state = client.post(f"/race/{session_id}/advance", json={}).json()
        all_events.extend(state["events"])

    rival_pits = [e for e in all_events if e["kind"] == "rival_pitted" and e["driver"] == "DRV"]
    assert len(rival_pits) >= 1, "DRV must pit at least once during the race"
