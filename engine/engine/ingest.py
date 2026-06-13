"""FastF1 → RaceData transformation and SQLite persistence.

Public API
----------
load_race(year, gp, session="R") -> RaceData
    Fetch from FastF1 (or on-disk cache) and return structured data.
    Does NOT write to the database.

Run as a module to fetch and store a race:
    python -m engine.ingest --year 2024 --gp "Hungary"
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from .models import DriverData, LapData, RaceData
from .team_colours import team_colour as _team_colour

if TYPE_CHECKING:
    pass

_CACHE_DIR: Path = Path(__file__).parent.parent / "fastf1_cache"
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enable_cache() -> None:
    import fastf1 as _ff1
    _CACHE_DIR.mkdir(exist_ok=True)
    _ff1.Cache.enable_cache(str(_CACHE_DIR))


def _to_seconds(value: Any) -> float | None:
    """Convert a pandas Timedelta/NaT to float seconds, or None."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return float(value.total_seconds())


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return int(value)


def _safe_str(value: Any, default: str = "") -> str:
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    return s if s else default


# ---------------------------------------------------------------------------
# Transformation (no FastF1 imports; testable with plain DataFrames)
# ---------------------------------------------------------------------------

def _parse_driver_laps(driver_laps: pd.DataFrame) -> list[LapData]:
    """Convert one driver's laps DataFrame rows into a list of LapData."""
    result: list[LapData] = []
    for _, row in driver_laps.sort_values("LapNumber").iterrows():
        result.append(
            LapData(
                lap_number=_safe_int(row["LapNumber"]),
                lap_time_s=_to_seconds(row["LapTime"]),
                compound=_safe_str(row.get("Compound"), "UNKNOWN"),
                tyre_life=_safe_int(row.get("TyreLife"), 0),
                stint=_safe_int(row.get("Stint"), 1),
                is_pit_in_lap=bool(pd.notna(row.get("PitInTime"))),
                is_pit_out_lap=bool(pd.notna(row.get("PitOutTime"))),
            )
        )
    return result


def _build_race_data(
    session: Any,
    year: int,
    session_type: str,
    gp_key: str = "",
) -> RaceData:
    """Transform a loaded FastF1 session object into a RaceData.

    ``session`` must expose ``.laps`` (DataFrame), ``.results``
    (DataFrame), and ``.event`` (dict-like / pandas Series).
    ``year`` and ``session_type`` are passed in rather than extracted from
    the session to avoid fragile attribute spelunking.
    """
    laps: pd.DataFrame = session.laps
    results: pd.DataFrame = session.results
    event = session.event

    gp_name = _safe_str(event["EventName"], "Unknown GP")
    circuit_name = _safe_str(event.get("Location"), gp_name)

    # FastF1 exposes session.total_laps for race sessions; fall back to
    # the max lap number seen in timing data.
    raw_total = getattr(session, "total_laps", None)
    total_laps = int(raw_total) if raw_total else _safe_int(laps["LapNumber"].max())

    # Build lookup dicts keyed by driver number (always a string in FastF1)
    grid: dict[str, int] = {}
    finish: dict[str, int] = {}
    names: dict[str, str] = {}

    for _, row in results.iterrows():
        dn = _safe_str(row["DriverNumber"])
        grid[dn] = _safe_int(row.get("GridPosition"), 0)
        finish[dn] = _safe_int(row.get("Position"), 0)
        # FullName is always present in FastF1 3.x results
        names[dn] = (
            _safe_str(row.get("FullName"))
            or _safe_str(row.get("BroadcastName"))
            or dn
        )

    drivers: list[DriverData] = []
    for driver_number, group in laps.groupby("DriverNumber"):
        dn = str(driver_number)
        first_row = group.iloc[0]
        team_name = _safe_str(first_row.get("Team"), "Unknown")
        drivers.append(
            DriverData(
                driver_number=dn,
                # Driver column = 3-letter code; Team column is in laps too
                driver_code=_safe_str(first_row.get("Driver"), dn),
                full_name=names.get(dn, dn),
                team=team_name,
                team_colour=_team_colour(team_name),
                grid_position=grid.get(dn, 0),
                finishing_position=finish.get(dn, 0),
                laps=_parse_driver_laps(group),
            )
        )

    # Sort by finishing position; DNFs / unclassified go to the back.
    drivers.sort(key=lambda d: d.finishing_position if d.finishing_position > 0 else 99)

    return RaceData(
        year=year,
        gp_name=gp_name,
        gp_key=gp_key,
        circuit_name=circuit_name,
        total_laps=total_laps,
        session_type=session_type,
        drivers=drivers,
    )


# ---------------------------------------------------------------------------
# Track geometry extraction
# ---------------------------------------------------------------------------

def _extract_track_points(session: Any, n_points: int = 300) -> list[list[float]]:
    """Return a normalised centre-line polyline from the session's fastest lap.

    Coordinates are scaled so the longest axis spans [0, 1] (aspect ratio
    preserved); the shorter axis is in [0, scale] where scale <= 1.
    Returns an empty list if telemetry is unavailable.
    """
    try:
        fastest = session.laps.pick_fastest()
        tel = fastest.get_telemetry()
        if "X" not in tel.columns or "Y" not in tel.columns:
            return []
        tel = tel[["X", "Y"]].dropna()
        if len(tel) < 10:
            return []

        step = max(1, len(tel) // n_points)
        tel = tel.iloc[::step]

        x = tel["X"].to_numpy(dtype=float)
        y = tel["Y"].to_numpy(dtype=float)

        x_range = float(x.max() - x.min())
        y_range = float(y.max() - y.min())
        scale = max(x_range, y_range) or 1.0

        x_norm = (x - x.min()) / scale
        y_norm = (y - y.min()) / scale

        return [[round(float(xi), 4), round(float(yi), 4)] for xi, yi in zip(x_norm, y_norm)]
    except Exception as exc:
        logger.warning("Could not extract track points: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_race(year: int, gp: str, session: str = "R") -> RaceData:
    """Fetch a Grand Prix session from FastF1 (or local cache).

    Returns a fully-populated :class:`~engine.models.RaceData`.
    Does not write to the database — call :func:`engine.db.save_race`
    separately to persist.
    """
    import fastf1 as _ff1

    _enable_cache()
    logger.info("Loading %s %d session=%s from FastF1...", gp, year, session)
    sess = _ff1.get_session(year, gp, session)
    sess.load(laps=True, telemetry=True, weather=False, messages=False)
    race = _build_race_data(sess, year=year, session_type=session, gp_key=gp)
    race.track_points = _extract_track_points(sess)
    return race


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch an F1 session from FastF1 and store it in SQLite."
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--gp", required=True, help="GP name, e.g. 'Hungary'")
    parser.add_argument("--session", default="R", help="Session type (default: R)")
    parser.add_argument("--db", default=None, help="Override SQLite path")
    args = parser.parse_args()

    from . import db as _db

    db_path = Path(args.db) if args.db else _db.DEFAULT_DB
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print(f"Fetching {args.year} {args.gp} (session={args.session}) ...")
    race = load_race(args.year, args.gp, args.session)

    with _db.connect(db_path) as conn:
        _db.init_db(conn)
        race_id = _db.save_race(race, conn)

    total_laps_rows = sum(len(d.laps) for d in race.drivers)
    valid_times = sum(
        1 for d in race.drivers for lap in d.laps if lap.lap_time_s is not None
    )

    print(f"\n{race.gp_name} {race.year} - {race.circuit_name} ({race.total_laps} laps)")
    print(f"Drivers: {len(race.drivers)}  |  Lap rows: {total_laps_rows}  |  Valid times: {valid_times}\n")
    print(f"{'Pos':>3}  {'Code':<5}  {'Team':<26}  {'Grid':>4}  {'Laps':>4}")
    print("-" * 56)
    for d in race.drivers:
        print(
            f"{d.finishing_position:>3}  {d.driver_code:<5}  {d.team:<26}  "
            f"{d.grid_position:>4}  {len(d.laps):>4}"
        )
    print(f"\nSaved to {db_path}  (race_id={race_id})")


if __name__ == "__main__":
    main()
