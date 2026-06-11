"""Unit tests for engine.ingest transformation logic.

All tests use in-process fixtures — no FastF1 network calls, no disk I/O.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from engine.ingest import _build_race_data, _parse_driver_laps
from engine.db import init_db, save_race
from engine.models import RaceData


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
        assert ver.grid_position == 1
        assert ver.finishing_position == 1
        assert len(ver.laps) == 2


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
