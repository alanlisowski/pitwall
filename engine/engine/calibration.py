"""Calibration: validate the simulator against real race data from SQLite.

Typical usage::

    python -m engine.calibration --year 2024 --gp Hungary

Flow:
    1. Load real lap data from SQLite (already ingested via engine.ingest).
    2. Build a CarStrategy per driver using their real pit stops / compounds
       and base pace estimated by reversing the model equations on valid laps.
    3. Run simulate().
    4. Compare simulated finishing order vs real order with MAE and Spearman rho.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .db import DEFAULT_DB
from .sim import CarStrategy, PitStop, RaceResult, SimConfig, simulate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuned configuration — calibrated against the 2024 Hungarian GP.
# Updated after parameter search; see CALIBRATION.md for analysis.
# ---------------------------------------------------------------------------
TUNED_CFG = SimConfig(
    deg_soft=0.130,
    deg_medium=0.080,
    deg_hard=0.050,
    offset_soft=-0.70,
    offset_medium=-0.35,
    offset_hard=0.00,
    pit_loss=21.0,
    fuel_effect=0.045,
)

_VALID_COMPOUNDS = frozenset({"SOFT", "MEDIUM", "HARD"})

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DriverRecord:
    driver_code: str
    finishing_position: int
    grid_position: int
    laps: list[dict]


@dataclass
class RealRaceData:
    gp_name: str
    circuit: str
    year: int
    total_laps: int
    drivers: list[DriverRecord]


@dataclass
class PositionError:
    driver: str
    real_pos: int
    sim_pos: int
    error: int


@dataclass
class CalibrationResult:
    gp_name: str
    year: int
    mae: float
    correlation: float
    errors: list[PositionError]
    simulated_order: list[str]
    real_order: list[str]

    def summary(self) -> str:
        lines = [
            f"--- {self.gp_name} {self.year} ---",
            f"  MAE:        {self.mae:.2f} positions",
            f"  Spearman r: {self.correlation:.3f}",
            "",
            f"  {'Driver':<6}  {'Real':>4}  {'Sim':>4}  {'Err':>4}",
            "  " + "-" * 28,
        ]
        for e in sorted(self.errors, key=lambda x: x.real_pos):
            lines.append(
                f"  {e.driver:<6}  {e.real_pos:>4}  {e.sim_pos:>4}  {e.error:>+4}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Loading from SQLite
# ---------------------------------------------------------------------------


def load_real_race(
    year: int,
    gp: str,
    db_path: Path | str = DEFAULT_DB,
) -> RealRaceData:
    """Return per-driver lap data from the local SQLite database."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    race = conn.execute(
        "SELECT * FROM races WHERE year=? AND (gp_name LIKE ? OR gp_key LIKE ?)",
        (year, f"%{gp}%", f"%{gp}%"),
    ).fetchone()
    if race is None:
        raise ValueError(
            f"Race not found: {year} {gp!r}. "
            "Run 'python -m engine.ingest --year ... --gp ...' first."
        )

    race_id = race["id"]
    driver_rows = conn.execute(
        "SELECT * FROM drivers WHERE race_id=? ORDER BY finishing_position",
        (race_id,),
    ).fetchall()

    drivers: list[DriverRecord] = []
    for row in driver_rows:
        laps = conn.execute(
            """SELECT lap_number, lap_time_s, compound, tyre_life, stint,
                      is_pit_in_lap, is_pit_out_lap
               FROM laps WHERE driver_id=? ORDER BY lap_number""",
            (row["id"],),
        ).fetchall()
        drivers.append(
            DriverRecord(
                driver_code=row["driver_code"],
                finishing_position=row["finishing_position"],
                grid_position=row["grid_position"],
                laps=[dict(l) for l in laps],
            )
        )

    conn.close()
    return RealRaceData(
        gp_name=race["gp_name"],
        circuit=race["circuit"],
        year=year,
        total_laps=race["total_laps"],
        drivers=drivers,
    )


# ---------------------------------------------------------------------------
# Strategy construction helpers
# ---------------------------------------------------------------------------


def _start_compound(laps: list[dict]) -> str:
    """Return the compound on lap 1, defaulting to MEDIUM."""
    for lap in sorted(laps, key=lambda l: l["lap_number"])[:3]:
        c = (lap["compound"] or "").upper()
        if c in _VALID_COMPOUNDS:
            return c
    return "MEDIUM"


def _extract_pit_stops(laps: list[dict]) -> list[PitStop]:
    """
    Identify pit stop laps from is_pit_in_lap flags.

    The new compound is read from the first subsequent lap with a valid
    compound (typically the very next lap, the pit-out lap).
    """
    by_lap: dict[int, dict] = {l["lap_number"]: l for l in laps}
    stops: list[PitStop] = []

    for lap in sorted(laps, key=lambda l: l["lap_number"]):
        if not lap["is_pit_in_lap"]:
            continue
        for offset in range(1, 6):
            next_lap = by_lap.get(lap["lap_number"] + offset)
            if next_lap is None:
                continue
            c = (next_lap["compound"] or "").upper()
            if c in _VALID_COMPOUNDS:
                stops.append(PitStop(lap=lap["lap_number"], compound=c))
                break

    return stops


def _estimate_base_pace(laps: list[dict], cfg: SimConfig) -> float:
    """
    Reverse the model equations on valid race laps to back-estimate base pace.

    For each valid lap:
        adjusted = lap_time
                   - deg_rate(compound) * sim_age
                   - pace_offset(compound)
                   + (lap_number - 1) * fuel_effect    # undo fuel_saving

    sim_age is computed as lap_number - first_lap_of_this_stint, anchored
    to lap 1 of the race (matches how simulate() initialises tyre_age=0).

    Returns the 25th-percentile of adjusted values — a representative
    clean-air pace that discards laps slowed by traffic or yellow flags.
    Fallback: 90.0 s (mid-pack F1 lap time) if no valid laps exist.
    """
    # Find first lap number per stint for robust age calculation
    stint_starts: dict[int, int] = {}
    for lap in laps:
        s = lap["stint"]
        n = lap["lap_number"]
        if s not in stint_starts or n < stint_starts[s]:
            stint_starts[s] = n

    adjusted: list[float] = []
    for lap in laps:
        t = lap["lap_time_s"]
        if t is None or t <= 0:
            continue
        if lap["is_pit_in_lap"] or lap["is_pit_out_lap"]:
            continue
        if lap["lap_number"] <= 1:
            continue

        c = (lap["compound"] or "").upper()
        if c not in _VALID_COMPOUNDS:
            continue

        # Tyre age before this lap, anchored to race lap 1 as age=0
        first = stint_starts.get(lap["stint"], lap["lap_number"])
        sim_age = max(0, lap["lap_number"] - first)

        deg    = cfg.deg_rate(c) * sim_age
        offset = cfg.pace_offset(c)
        fuel   = -(lap["lap_number"] - 1) * cfg.fuel_effect  # fuel_saving value (negative)

        adjusted.append(t - deg - offset - fuel)

    if not adjusted:
        return 90.0

    # Filter statistical outliers: drop laps > 107% of median (SC / VSC laps)
    median_val = float(np.median(adjusted))
    clean = [v for v in adjusted if v <= median_val * 1.07]
    if not clean:
        clean = adjusted

    clean.sort()
    # Median (50th pct) outperforms lower percentiles on Hungarian GP calibration.
    # Lower percentiles over-weight free-air laps from backmarkers, inflating their pace.
    median_idx = max(0, int(len(clean) * 0.50))
    return clean[median_idx]


def build_baseline_strategies(
    real: RealRaceData,
    cfg: SimConfig,
) -> list[CarStrategy]:
    """One CarStrategy per driver, using real pit stops and estimated base pace."""
    return [
        CarStrategy(
            driver=dr.driver_code,
            base_pace=_estimate_base_pace(dr.laps, cfg),
            start_compound=_start_compound(dr.laps),
            pit_stops=_extract_pit_stops(dr.laps),
        )
        for dr in real.drivers
    ]


# ---------------------------------------------------------------------------
# Accuracy metrics
# ---------------------------------------------------------------------------


def _spearman_r(positions_a: list[int], positions_b: list[int]) -> float:
    """Spearman rank correlation for two equal-length lists."""
    n = len(positions_a)
    if n < 2:
        return 1.0
    a = np.argsort(np.argsort(positions_a)).astype(float) + 1
    b = np.argsort(np.argsort(positions_b)).astype(float) + 1
    d2 = float(np.sum((a - b) ** 2))
    return float(1.0 - 6.0 * d2 / (n * (n**2 - 1)))


def compare(
    simulated_order: list[str],
    real_order: list[str],
    gp_name: str = "",
    year: int = 0,
) -> CalibrationResult:
    """
    Compare a simulated finishing order against the real one.

    Only drivers present in both lists are scored.  Pass a real_order
    that already excludes DNF cars to omit them from the accuracy metric.
    """
    sim_set = set(simulated_order)
    common = [d for d in real_order if d in sim_set]

    real_pos = {d: i + 1 for i, d in enumerate(common)}
    sim_ranks = {d: simulated_order.index(d) + 1 for d in common}

    errors = [
        PositionError(
            driver=d,
            real_pos=real_pos[d],
            sim_pos=sim_ranks[d],
            error=sim_ranks[d] - real_pos[d],
        )
        for d in common
    ]

    reals = [real_pos[d] for d in common]
    sims = [sim_ranks[d] for d in common]

    mae = float(np.mean(np.abs(np.array(sims, dtype=float) - np.array(reals, dtype=float))))
    rho = _spearman_r(reals, sims)

    return CalibrationResult(
        gp_name=gp_name,
        year=year,
        mae=mae,
        correlation=rho,
        errors=errors,
        simulated_order=simulated_order,
        real_order=real_order,
    )


# ---------------------------------------------------------------------------
# End-to-end calibration
# ---------------------------------------------------------------------------


def run_calibration(
    year: int,
    gp: str,
    cfg: SimConfig | None = None,
    db_path: Path | str = DEFAULT_DB,
) -> CalibrationResult:
    """Load real data, build strategies, simulate, and compare.

    DNF drivers (fewer than half total laps completed) are excluded from
    the accuracy metric but still simulated.
    """
    if cfg is None:
        cfg = TUNED_CFG

    real = load_real_race(year, gp, db_path)
    strategies = build_baseline_strategies(real, cfg)
    result = simulate(strategies, total_laps=real.total_laps, cfg=cfg)

    # Exclude DNFs from accuracy scoring
    dnf_threshold = real.total_laps // 2
    finishers = [d for d in real.drivers if len(d.laps) >= dnf_threshold]
    real_order = [d.driver_code for d in finishers]

    return compare(
        simulated_order=result.finishing_order,
        real_order=real_order,
        gp_name=real.gp_name,
        year=year,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Calibrate sim against real race data in SQLite"
    )
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--gp", default="Hungary")
    parser.add_argument("--db", default=None)
    parser.add_argument(
        "--default-cfg",
        action="store_true",
        help="Use SimConfig() defaults instead of TUNED_CFG",
    )
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else DEFAULT_DB
    cfg = SimConfig() if args.default_cfg else TUNED_CFG

    result = run_calibration(args.year, args.gp, cfg=cfg, db_path=db_path)
    print(result.summary())


if __name__ == "__main__":
    main()
