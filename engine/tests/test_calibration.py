"""Regression test: calibration accuracy must not silently degrade.

Requires the local SQLite database to be populated:
    python -m engine.ingest --year 2024 --gp Hungary

If the DB is absent the test is skipped so CI without ingested data still passes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

DB_PATH = Path(__file__).parent.parent / "pitwall.db"

# These thresholds lock in the accuracy achieved after parameter tuning.
# See engine/CALIBRATION.md for the full analysis.
# Tighten these only when the model improves; never loosen them without justification.
MAE_LIMIT = 2.0         # mean absolute position error (achieved: 0.84)
CORRELATION_FLOOR = 0.90  # Spearman rho (achieved: 0.979)


@pytest.mark.skipif(
    not DB_PATH.exists(),
    reason=(
        "Real race DB not present — run "
        "'python -m engine.ingest --year 2024 --gp Hungary' first"
    ),
)
def test_calibration_mae_does_not_regress() -> None:
    """Simulation accuracy on 2024 Hungarian GP must not silently degrade.

    Uses the real lap-by-lap data already in SQLite to construct driver
    strategies, runs the simulator, and compares against the real finishing order.
    Any regression in the five-component model or the base-pace estimator
    should push the MAE above the locked threshold and fail this test.
    """
    from engine.calibration import TUNED_CFG, run_calibration

    result = run_calibration(2024, "Hungary", cfg=TUNED_CFG, db_path=DB_PATH)

    assert result.mae <= MAE_LIMIT, (
        f"MAE regressed: {result.mae:.3f} > {MAE_LIMIT}. "
        "See engine/CALIBRATION.md — the simulation model may have broken."
    )
    assert result.correlation >= CORRELATION_FLOOR, (
        f"Spearman rho regressed: {result.correlation:.3f} < {CORRELATION_FLOOR}. "
        "See engine/CALIBRATION.md for the expected accuracy."
    )
