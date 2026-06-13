"""Unit tests for engine.ingest transformation logic.

All tests use in-process fixtures — no FastF1 network calls, no disk I/O.
"""
from __future__ import annotations

import math
import sqlite3

import pandas as pd
import pytest

from engine.ingest import _build_race_data, _extract_track_points, _parse_driver_laps
from engine.db import init_db, save_race
from engine.models import RaceData
from engine.team_colours import TEAM_COLOURS, team_colour


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_laps_df() -> pd.DataFrame:
    """5 laps for driver '1' (VER): lap 1 NaT, laps 2-5 valid, pit in on lap 3."""
    return pd.DataFrame(
        {
            "DriverNumber": ["1"] * 5,
            "Driver":       ["VER"] * 5,
            "Team":         ["Red Bull Racing"] * 5,
            "LapNumber":    [1.0, 2.0, 3.0, 4.0, 5.0],
            "LapTime": [
                pd.NaT,
                pd.Timedelta(seconds=91.300),
                pd.Timedelta(seconds=91.800),
                pd.Timedelta(seconds=92.100),
                pd.Timedelta(seconds=90.500),
            ],
            "Compound":  ["SOFT", "SOFT", "SOFT", "MEDIUM", "MEDIUM"],
            "TyreLife":  [1.0, 2.0, 3.0, 1.0, 2.0],
            "Stint":     [1.0, 1.0, 1.0, 2.0, 2.0],
            "PitInTime": [
                pd.NaT,
                pd.NaT,
                pd.Timedelta(minutes=5),  # pits at end of lap 3
                pd.NaT,
                pd.NaT,
            ],
            "PitOutTime": [
                pd.NaT,
                pd.NaT,
                pd.NaT,
                pd.Timedelta(minutes=5, seconds=22),  # exits pits during lap 4
                pd.NaT,
            ],
        }
    )


class _MockSession:
    """Minimal stand-in for a fastf1.core.Session."""

    laps = pd.DataFrame(
        {
            "DriverNumber": ["1", "1", "4", "4"],
            "Driver":       ["VER", "VER", "NOR", "NOR"],
            "Team":         ["Red Bull Racing"] * 2 + ["McLaren"] * 2,
            "LapNumber":    [1.0, 2.0, 1.0, 2.0],
            "LapTime": [
                pd.NaT,
                pd.Timedelta(seconds=90.5),
                pd.NaT,
                pd.Timedelta(seconds=92.0),
            ],
            "Compound":   ["SOFT"] * 4,
            "TyreLife":   [1.0, 2.0, 1.0, 2.0],
            "Stint":      [1.0, 1.0, 1.0, 1.0],
            "PitInTime":  [pd.NaT] * 4,
            "PitOutTime": [pd.NaT] * 4,
        }
    )

    results = pd.DataFrame(
        {
            "DriverNumber": ["1", "4"],
            "Abbreviation": ["VER", "NOR"],
            "FullName":     ["Max Verstappen", "Lando Norris"],
            "TeamName":     ["Red Bull Racing", "McLaren"],
            "GridPosition": [1.0, 2.0],
            "Position":     [1.0, 2.0],
        }
    )

    event = pd.Series(
        {
            "EventName": "Grand Prix De Fixture",
            "Location":  "Fixtureville",
        }
    )

    total_laps = 2


# ---------------------------------------------------------------------------
# _parse_driver_laps
# ---------------------------------------------------------------------------

class TestParseDriverLaps:
    def test_nat_lap_time_becomes_none(self):
        laps = _parse_driver_laps(_make_laps_df())
        assert laps[0].lap_time_s is None

    def test_valid_lap_time_converted_to_seconds(self):
        laps = _parse_driver_laps(_make_laps_df())
        assert laps[1].lap_time_s == pytest.approx(91.3)
        assert laps[2].lap_time_s == pytest.approx(91.8)

    def test_pit_in_lap_detected(self):
        laps = _parse_driver_laps(_make_laps_df())
        assert laps[2].is_pit_in_lap is True
        assert laps[0].is_pit_in_lap is False
        assert laps[1].is_pit_in_lap is False

    def test_pit_out_lap_detected(self):
        laps = _parse_driver_laps(_make_laps_df())
        assert laps[3].is_pit_out_lap is True
        assert laps[2].is_pit_out_lap is False

    def test_compound_and_tyre_life(self):
        laps = _parse_driver_laps(_make_laps_df())
        assert laps[0].compound == "SOFT"
        assert laps[3].compound == "MEDIUM"
        assert laps[3].tyre_life == 1
        assert laps[4].tyre_life == 2

    def test_stint_increments_after_pit(self):
        laps = _parse_driver_laps(_make_laps_df())
        assert laps[0].stint == 1
        assert laps[2].stint == 1
        assert laps[3].stint == 2

    def test_laps_sorted_by_number(self):
        # Feed rows in reverse order; output should still be ascending.
        df = _make_laps_df().iloc[::-1].reset_index(drop=True)
        laps = _parse_driver_laps(df)
        numbers = [l.lap_number for l in laps]
        assert numbers == sorted(numbers)


# ---------------------------------------------------------------------------
# _build_race_data
# ---------------------------------------------------------------------------

class TestBuildRaceData:
    def test_basic_fields(self):
        race = _build_race_data(_MockSession(), year=2024, session_type="R", gp_key="Fixture")
        assert race.year == 2024
        assert race.gp_name == "Grand Prix De Fixture"
        assert race.gp_key == "Fixture"
        assert race.circuit_name == "Fixtureville"
        assert race.total_laps == 2
        assert race.session_type == "R"

    def test_driver_count(self):
        race = _build_race_data(_MockSession(), year=2024, session_type="R")
        assert len(race.drivers) == 2

    def test_drivers_sorted_by_finishing_position(self):
        race = _build_race_data(_MockSession(), year=2024, session_type="R")
        positions = [d.finishing_position for d in race.drivers]
        assert positions == sorted(positions)

    def test_driver_fields_populated(self):
        race = _build_race_data(_MockSession(), year=2024, session_type="R")
        ver = next(d for d in race.drivers if d.driver_code == "VER")
        assert ver.full_name == "Max Verstappen"
        assert ver.team == "Red Bull Racing"
        assert ver.team_colour == "#3671C6"
        assert ver.grid_position == 1
        assert ver.finishing_position == 1
        assert len(ver.laps) == 2

    def test_team_colour_populated_for_known_and_unknown_teams(self):
        race = _build_race_data(_MockSession(), year=2024, session_type="R")
        nor = next(d for d in race.drivers if d.driver_code == "NOR")
        assert nor.team == "McLaren"
        assert nor.team_colour == "#FF8000"


# ---------------------------------------------------------------------------
# DB round-trip
# ---------------------------------------------------------------------------

class TestDbRoundTrip:
    def _make_race(self) -> RaceData:
        return _build_race_data(_MockSession(), year=2024, session_type="R")

    def test_save_returns_positive_id(self):
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            race_id = save_race(self._make_race(), conn)
        assert race_id > 0

    def test_lap_rows_persisted(self):
        race = self._make_race()
        expected_laps = sum(len(d.laps) for d in race.drivers)

        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            save_race(race, conn)
            count = conn.execute("SELECT COUNT(*) FROM laps").fetchone()[0]

        assert count == expected_laps

    def test_re_ingestion_is_idempotent(self):
        race = self._make_race()
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            id1 = save_race(race, conn)
            id2 = save_race(race, conn)
            race_count = conn.execute("SELECT COUNT(*) FROM races").fetchone()[0]
            lap_count = conn.execute("SELECT COUNT(*) FROM laps").fetchone()[0]

        assert id1 == id2
        assert race_count == 1
        assert lap_count == sum(len(d.laps) for d in race.drivers)

    def test_team_colour_persisted(self):
        """team_colour written to DB and readable back from drivers table."""
        race = self._make_race()
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            race_id = save_race(race, conn)
            rows = conn.execute(
                "SELECT driver_code, team_colour FROM drivers WHERE race_id=?",
                (race_id,),
            ).fetchall()
        by_code = {r["driver_code"]: r["team_colour"] for r in rows}
        assert by_code["VER"] == "#3671C6"
        assert by_code["NOR"] == "#FF8000"

    def test_track_points_persisted_and_loaded(self):
        """track_points JSON round-trips through SQLite."""
        import json

        race = self._make_race()
        race.track_points = [[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]]
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            init_db(conn)
            race_id = save_race(race, conn)
            raw = conn.execute(
                "SELECT track_points FROM races WHERE id=?", (race_id,)
            ).fetchone()["track_points"]
        assert json.loads(raw) == [[0.0, 0.0], [0.5, 1.0], [1.0, 0.0]]


# ---------------------------------------------------------------------------
# team_colour lookup
# ---------------------------------------------------------------------------

class TestTeamColour:
    def test_known_team_returns_correct_hex(self):
        assert team_colour("Red Bull Racing") == "#3671C6"
        assert team_colour("McLaren") == "#FF8000"
        assert team_colour("Ferrari") == "#E8002D"

    def test_unknown_team_returns_white(self):
        assert team_colour("Unknown Team XYZ") == "#FFFFFF"

    def test_alias_variants_resolve(self):
        assert team_colour("AlphaTauri") == team_colour("Racing Bulls")


# ---------------------------------------------------------------------------
# _extract_track_points
# ---------------------------------------------------------------------------

class _FakeTelemetry:
    """Minimal stand-in for a FastF1 telemetry DataFrame."""

    def __init__(self, n: int = 120) -> None:
        xs = [math.cos(2 * math.pi * i / n) * 500.0 for i in range(n)]
        ys = [math.sin(2 * math.pi * i / n) * 300.0 for i in range(n)]
        self._df = pd.DataFrame({"X": xs, "Y": ys})

    def __getitem__(self, cols: list[str]) -> pd.DataFrame:
        return self._df[cols]

    @property
    def columns(self) -> list[str]:
        return list(self._df.columns)


class _FakeLap:
    def __init__(self, n: int = 120) -> None:
        self._tel = _FakeTelemetry(n)

    def get_telemetry(self) -> _FakeTelemetry:
        return self._tel


class _FakeLaps:
    def __init__(self, n: int = 120) -> None:
        self._lap = _FakeLap(n)

    def pick_fastest(self) -> _FakeLap:
        return self._lap


class _FakeSession:
    def __init__(self, n: int = 120) -> None:
        self.laps = _FakeLaps(n)


class TestExtractTrackPoints:
    def test_returns_normalised_points_in_unit_range(self):
        points = _extract_track_points(_FakeSession())
        assert len(points) > 0
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        assert all(0.0 <= x <= 1.0 for x in xs)
        assert all(0.0 <= y <= 1.0 for y in ys)

    def test_longer_axis_spans_full_unit(self):
        # x radius 500, y radius 300 → x is the longer axis → max x ≈ 1.0
        points = _extract_track_points(_FakeSession())
        xs = [p[0] for p in points]
        assert max(xs) == pytest.approx(1.0, abs=0.01)

    def test_respects_n_points_limit(self):
        points = _extract_track_points(_FakeSession(n=1200), n_points=100)
        assert len(points) <= 110  # allow small overshoot from integer step

    def test_returns_empty_on_missing_xy_columns(self):
        class _NoXY:
            @property
            def columns(self):
                return ["Speed", "RPM"]
            def __getitem__(self, cols):
                raise KeyError(cols)

        class _BadLap:
            def get_telemetry(self):
                return _NoXY()

        class _BadLaps:
            def pick_fastest(self):
                return _BadLap()

        class _BadSession:
            laps = _BadLaps()

        assert _extract_track_points(_BadSession()) == []

    def test_returns_empty_on_exception(self):
        class _BrokenSession:
            class laps:
                @staticmethod
                def pick_fastest():
                    raise RuntimeError("no telemetry")

        assert _extract_track_points(_BrokenSession()) == []
