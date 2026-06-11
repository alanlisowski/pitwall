from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from .models import RaceData

DEFAULT_DB: Path = Path(__file__).parent.parent / "pitwall.db"


@contextmanager
def connect(db_path: Path | str = DEFAULT_DB) -> Generator[sqlite3.Connection, None, None]:
    """Yield a connection that auto-commits on exit and rolls back on error."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't already exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS races (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            year         INTEGER NOT NULL,
            gp_name      TEXT NOT NULL,
            gp_key       TEXT NOT NULL DEFAULT '',
            circuit      TEXT NOT NULL,
            total_laps   INTEGER NOT NULL,
            session_type TEXT NOT NULL DEFAULT 'R',
            UNIQUE(year, gp_name, session_type)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id            INTEGER NOT NULL REFERENCES races(id),
            driver_number      TEXT NOT NULL,
            driver_code        TEXT NOT NULL,
            full_name          TEXT NOT NULL,
            team               TEXT NOT NULL,
            grid_position      INTEGER NOT NULL,
            finishing_position INTEGER NOT NULL,
            UNIQUE(race_id, driver_number)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS laps (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_id      INTEGER NOT NULL REFERENCES drivers(id),
            lap_number     INTEGER NOT NULL,
            lap_time_s     REAL,
            compound       TEXT NOT NULL,
            tyre_life      INTEGER NOT NULL,
            stint          INTEGER NOT NULL,
            is_pit_in_lap  INTEGER NOT NULL DEFAULT 0,
            is_pit_out_lap INTEGER NOT NULL DEFAULT 0
        )
    """)


def save_race(race: RaceData, conn: sqlite3.Connection) -> int:
    """Upsert a RaceData into the database and return the race id."""
    conn.execute(
        """
        INSERT INTO races (year, gp_name, gp_key, circuit, total_laps, session_type)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(year, gp_name, session_type) DO UPDATE SET
            gp_key     = excluded.gp_key,
            circuit    = excluded.circuit,
            total_laps = excluded.total_laps
        """,
        (race.year, race.gp_name, race.gp_key, race.circuit_name, race.total_laps, race.session_type),
    )
    race_id: int = conn.execute(
        "SELECT id FROM races WHERE year=? AND gp_name=? AND session_type=?",
        (race.year, race.gp_name, race.session_type),
    ).fetchone()[0]

    for driver in race.drivers:
        conn.execute(
            """
            INSERT INTO drivers
                (race_id, driver_number, driver_code, full_name, team,
                 grid_position, finishing_position)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(race_id, driver_number) DO UPDATE SET
                driver_code        = excluded.driver_code,
                grid_position      = excluded.grid_position,
                finishing_position = excluded.finishing_position
            """,
            (
                race_id,
                driver.driver_number,
                driver.driver_code,
                driver.full_name,
                driver.team,
                driver.grid_position,
                driver.finishing_position,
            ),
        )
        driver_id: int = conn.execute(
            "SELECT id FROM drivers WHERE race_id=? AND driver_number=?",
            (race_id, driver.driver_number),
        ).fetchone()[0]

        # Replace laps wholesale on re-ingestion — raw race data never changes.
        conn.execute("DELETE FROM laps WHERE driver_id=?", (driver_id,))
        conn.executemany(
            """
            INSERT INTO laps
                (driver_id, lap_number, lap_time_s, compound, tyre_life,
                 stint, is_pit_in_lap, is_pit_out_lap)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    driver_id,
                    lap.lap_number,
                    lap.lap_time_s,
                    lap.compound,
                    lap.tyre_life,
                    lap.stint,
                    int(lap.is_pit_in_lap),
                    int(lap.is_pit_out_lap),
                )
                for lap in driver.laps
            ],
        )

    return race_id
