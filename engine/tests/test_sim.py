"""Tests for the lap-by-lap race simulation engine.

Organised in three sections:
  1. Component functions (pure, no simulation loop)
  2. Simulation runner (loop, positions, state tracking)
  3. Undercut emergence (the key strategic scenario)

No network calls, no FastF1, no SQLite.
"""
from __future__ import annotations

import pytest

from engine.sim import (
    CarStrategy,
    PitStop,
    RaceResult,
    SimConfig,
    simulate,
)
from engine.sim.components import (
    base_pace,
    compound_offset,
    fuel_saving,
    lap_time,
    pit_penalty,
    tyre_deg,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**overrides) -> SimConfig:
    """Return a SimConfig with optional field overrides."""
    cfg = SimConfig()
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _single_car(
    driver: str = "A",
    pace: float = 90.0,
    compound: str = "MEDIUM",
    stops: list[PitStop] | None = None,
) -> CarStrategy:
    return CarStrategy(
        driver=driver,
        base_pace=pace,
        start_compound=compound,
        pit_stops=stops or [],
    )


# ---------------------------------------------------------------------------
# 1. Component functions
# ---------------------------------------------------------------------------

class TestBasePace:
    def test_returns_car_pace(self):
        assert base_pace(91.5) == 91.5

    def test_zero_pace(self):
        assert base_pace(0.0) == 0.0


class TestTyreDeg:
    def test_zero_on_fresh_tyre(self):
        assert tyre_deg(0, "SOFT", SimConfig()) == 0.0

    def test_linear_growth(self):
        cfg = SimConfig(deg_soft=0.10)
        assert tyre_deg(10, "SOFT", cfg) == pytest.approx(1.0)
        assert tyre_deg(20, "SOFT", cfg) == pytest.approx(2.0)

    def test_compound_rates_differ(self):
        cfg = SimConfig(deg_soft=0.13, deg_medium=0.075, deg_hard=0.045)
        assert tyre_deg(10, "SOFT", cfg) > tyre_deg(10, "MEDIUM", cfg)
        assert tyre_deg(10, "MEDIUM", cfg) > tyre_deg(10, "HARD", cfg)

    def test_soft_degrades_fastest(self):
        cfg = SimConfig()
        assert cfg.deg_rate("SOFT") > cfg.deg_rate("MEDIUM") > cfg.deg_rate("HARD")

    def test_case_insensitive(self):
        cfg = SimConfig()
        assert tyre_deg(5, "soft", cfg) == tyre_deg(5, "SOFT", cfg)

    def test_unknown_compound_raises(self):
        with pytest.raises(ValueError, match="Unknown compound"):
            tyre_deg(5, "SUPER_SOFT", SimConfig())


class TestCompoundOffset:
    def test_hard_is_baseline_zero(self):
        assert compound_offset("HARD", SimConfig()) == 0.0

    def test_soft_is_faster_than_hard(self):
        assert compound_offset("SOFT", SimConfig()) < 0.0

    def test_medium_between_soft_and_hard(self):
        cfg = SimConfig()
        assert compound_offset("SOFT", cfg) < compound_offset("MEDIUM", cfg) < compound_offset("HARD", cfg)

    def test_values_within_realistic_range(self):
        cfg = SimConfig()
        gap = compound_offset("HARD", cfg) - compound_offset("SOFT", cfg)
        assert 0.6 <= gap <= 1.0, "Soft-to-hard gap should be 0.6–1.0 s/lap"

    def test_unknown_compound_raises(self):
        with pytest.raises(ValueError):
            compound_offset("INTER", SimConfig())


class TestFuelSaving:
    def test_zero_at_lap_one(self):
        """No fuel saving at lap 1 — tank is full, no improvement yet."""
        assert fuel_saving(1, SimConfig()) == 0.0

    def test_negative_from_lap_two(self):
        """Fuel burn makes the car faster from lap 2 onwards."""
        assert fuel_saving(2, SimConfig()) < 0.0

    def test_grows_linearly(self):
        cfg = SimConfig(fuel_effect=0.04)
        assert fuel_saving(11, cfg) == pytest.approx(-0.40)   # 10 laps × 0.04
        assert fuel_saving(51, cfg) == pytest.approx(-2.00)   # 50 laps × 0.04

    def test_proportional_to_fuel_effect(self):
        assert fuel_saving(21, _cfg(fuel_effect=0.06)) == pytest.approx(-1.20)


class TestPitPenalty:
    def test_zero_when_not_pitting(self):
        assert pit_penalty(False, SimConfig()) == 0.0

    def test_full_loss_when_pitting(self):
        cfg = SimConfig(pit_loss=22.0)
        assert pit_penalty(True, cfg) == 22.0

    def test_respects_custom_pit_loss(self):
        cfg = SimConfig(pit_loss=25.0)
        assert pit_penalty(True, cfg) == 25.0


class TestLapTime:
    def test_combines_all_five_components(self):
        cfg = SimConfig(
            deg_medium=0.08,
            offset_medium=-0.4,
            pit_loss=22.0,
            fuel_effect=0.04,
        )
        result = lap_time(
            car_pace=90.0,
            tyre_age=10,
            compound="MEDIUM",
            lap_number=11,
            is_pit_lap=False,
            cfg=cfg,
        )
        expected = (
            90.0          # base
            + 10 * 0.08   # tyre_deg: 10 laps × 0.08
            + (-0.4)      # compound_offset: MEDIUM
            + -(10 * 0.04)  # fuel_saving: lap 11 → 10 laps of saving
            + 0.0         # no pit
        )
        assert result == pytest.approx(expected)

    def test_pit_lap_adds_pit_loss(self):
        cfg = SimConfig(pit_loss=22.0, deg_medium=0.0, offset_medium=0.0, fuel_effect=0.0)
        without_pit = lap_time(car_pace=90.0, tyre_age=0, compound="MEDIUM",
                               lap_number=1, is_pit_lap=False, cfg=cfg)
        with_pit    = lap_time(car_pace=90.0, tyre_age=0, compound="MEDIUM",
                               lap_number=1, is_pit_lap=True,  cfg=cfg)
        assert with_pit - without_pit == pytest.approx(22.0)

    def test_fresh_tyre_no_deg_penalty(self):
        cfg = SimConfig(deg_soft=0.15, offset_soft=-0.8, fuel_effect=0.0)
        t = lap_time(car_pace=90.0, tyre_age=0, compound="SOFT",
                     lap_number=1, is_pit_lap=False, cfg=cfg)
        assert t == pytest.approx(90.0 + 0.0 - 0.8 + 0.0 + 0.0)


# ---------------------------------------------------------------------------
# 2. Simulation runner
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_returns_race_result(self):
        result = simulate([_single_car()], total_laps=5)
        assert isinstance(result, RaceResult)

    def test_snapshot_count(self):
        strategies = [_single_car("A"), _single_car("B"), _single_car("C")]
        result = simulate(strategies, total_laps=10)
        assert len(result.snapshots) == 10 * 3

    def test_finishing_order_contains_all_drivers(self):
        strategies = [_single_car("A"), _single_car("B")]
        result = simulate(strategies, total_laps=5)
        assert set(result.finishing_order) == {"A", "B"}

    def test_total_times_populated(self):
        result = simulate([_single_car("A")], total_laps=5)
        assert "A" in result.total_times
        assert result.total_times["A"] > 0

    def test_faster_car_wins(self):
        """A car with lower base pace should win when all else is equal."""
        strategies = [
            _single_car("FAST", pace=89.5),
            _single_car("SLOW", pace=90.5),
        ]
        result = simulate(strategies, total_laps=20, cfg=_cfg(fuel_effect=0.0))
        assert result.finishing_order[0] == "FAST"

    def test_leader_gap_is_zero(self):
        """The race leader's gap_to_leader must always be 0.0."""
        strategies = [_single_car("A", pace=89.0), _single_car("B", pace=91.0)]
        result = simulate(strategies, total_laps=10)
        leader_snaps = [s for s in result.snapshots if s.position == 1]
        for snap in leader_snaps:
            assert snap.gap_to_leader == pytest.approx(0.0)

    def test_gap_to_leader_non_negative(self):
        strategies = [_single_car("A", pace=89.0), _single_car("B", pace=91.0)]
        result = simulate(strategies, total_laps=10)
        assert all(s.gap_to_leader >= 0.0 for s in result.snapshots)

    def test_positions_cover_1_to_n_each_lap(self):
        strategies = [_single_car("A"), _single_car("B"), _single_car("C")]
        result = simulate(strategies, total_laps=5)
        for lap in range(1, 6):
            lap_positions = sorted(s.position for s in result.snapshots if s.lap == lap)
            assert lap_positions == [1, 2, 3]

    def test_tyre_age_increments_each_lap(self):
        """Without pit stops, tyre_age should grow by 1 each lap."""
        result = simulate([_single_car("A")], total_laps=5)
        snaps = sorted(
            (s for s in result.snapshots if s.driver == "A"),
            key=lambda s: s.lap,
        )
        for i, snap in enumerate(snaps):
            assert snap.tyre_age == i  # 0 on lap 1, 1 on lap 2, ...

    def test_compound_unchanged_without_pit(self):
        result = simulate([_single_car("A", compound="HARD")], total_laps=5)
        assert all(s.compound == "HARD" for s in result.snapshots if s.driver == "A")

    def test_pit_lap_recorded(self):
        """The snapshot for the pit lap must have pitted=True."""
        strat = _single_car("A", stops=[PitStop(lap=3, compound="HARD")])
        result = simulate([strat], total_laps=5)
        snaps = {s.lap: s for s in result.snapshots if s.driver == "A"}
        assert snaps[3].pitted is True
        assert snaps[1].pitted is False
        assert snaps[5].pitted is False

    def test_compound_changes_on_pit_lap(self):
        """The lap AFTER the stop should show the new compound."""
        strat = _single_car("A", compound="SOFT", stops=[PitStop(lap=3, compound="HARD")])
        result = simulate([strat], total_laps=6)
        snaps = {s.lap: s for s in result.snapshots if s.driver == "A"}
        assert snaps[1].compound == "SOFT"
        assert snaps[3].compound == "SOFT"   # driven on SOFT this lap
        assert snaps[4].compound == "HARD"   # first lap on HARD

    def test_tyre_age_resets_after_pit(self):
        """Tyre age for the lap after the pit should be 0."""
        strat = _single_car("A", stops=[PitStop(lap=5, compound="HARD")])
        result = simulate([strat], total_laps=8)
        snaps = {s.lap: s for s in result.snapshots if s.driver == "A"}
        assert snaps[5].tyre_age == 4   # 5th lap on start tyres (age 0→4)
        assert snaps[6].tyre_age == 0   # first lap on new HARD

    def test_pit_lap_time_includes_penalty(self):
        """Pit lap time must exceed a representative normal lap time."""
        cfg = _cfg(pit_loss=22.0, fuel_effect=0.0, deg_medium=0.0, offset_medium=0.0)
        strat = _single_car("A", compound="MEDIUM", stops=[PitStop(lap=5, compound="MEDIUM")])
        result = simulate([strat], total_laps=10, cfg=cfg)
        snaps = {s.lap: s for s in result.snapshots if s.driver == "A"}
        assert snaps[5].lap_time == pytest.approx(90.0 + 22.0)
        assert snaps[4].lap_time == pytest.approx(90.0)

    def test_fuel_effect_reduces_lap_time(self):
        """Later laps should be faster than early laps due to fuel burn."""
        cfg = _cfg(fuel_effect=0.05, deg_medium=0.0, offset_medium=0.0)
        result = simulate([_single_car("A", compound="MEDIUM")], total_laps=50, cfg=cfg)
        snaps = {s.lap: s for s in result.snapshots if s.driver == "A"}
        assert snaps[50].lap_time < snaps[1].lap_time

    def test_total_time_sum_of_lap_times(self):
        """Final total_time must equal the sum of all lap_time values."""
        result = simulate([_single_car("A")], total_laps=10)
        snap_sum = sum(s.lap_time for s in result.snapshots if s.driver == "A")
        assert result.total_times["A"] == pytest.approx(snap_sum)

    def test_default_cfg_used_when_none(self):
        result = simulate([_single_car("A")], total_laps=5, cfg=None)
        assert result.finishing_order == ["A"]


# ---------------------------------------------------------------------------
# 3. Undercut emergence
# ---------------------------------------------------------------------------

class TestUndercut:
    """The undercut is NOT hard-coded; it emerges from the five model
    components.  If a car pits earlier onto fresh tyres, it can run
    significantly quicker while its rival sits on worn rubber.  That
    per-lap time advantage can offset the pit-lane time loss and
    result in a position gain when the rival eventually pits.
    """

    @pytest.fixture
    def undercut_cfg(self) -> SimConfig:
        return SimConfig(
            deg_soft=0.15,      # aggressive soft deg — makes worn-tyre penalty clear
            deg_medium=0.075,
            deg_hard=0.045,
            offset_soft=-0.80,
            offset_medium=-0.40,
            offset_hard=0.00,
            pit_loss=22.0,
            fuel_effect=0.00,   # disabled to isolate tyre dynamics
        )

    def _run(self, cfg: SimConfig) -> RaceResult:
        """A pits on lap 25, B pits earlier on lap 20.  Same base pace."""
        strategies = [
            CarStrategy("A", base_pace=90.0, start_compound="SOFT",
                        pit_stops=[PitStop(lap=25, compound="SOFT")]),
            CarStrategy("B", base_pace=90.0, start_compound="SOFT",
                        pit_stops=[PitStop(lap=20, compound="SOFT")]),
        ]
        return simulate(strategies, total_laps=30, cfg=cfg)

    def test_undercut_car_wins(self, undercut_cfg):
        """B (earlier pitter) finishes ahead of identical-pace A."""
        result = self._run(undercut_cfg)
        assert result.finishing_order[0] == "B", (
            f"Expected B to win via undercut but got: {result.finishing_order}"
        )

    def test_b_temporarily_behind_after_pit(self, undercut_cfg):
        """After B's stop, it falls well behind A due to the pit-lane loss."""
        result = self._run(undercut_cfg)
        snaps = {(s.lap, s.driver): s for s in result.snapshots}
        # Immediately after B's pit, it should be >15s behind
        assert snaps[(21, "B")].gap_to_leader > 15

    def test_b_leads_after_both_have_pitted(self, undercut_cfg):
        """Once A also pits (lap 25+), B should be the race leader."""
        result = self._run(undercut_cfg)
        snaps = {(s.lap, s.driver): s for s in result.snapshots}
        # By lap 26 both have pitted; B should be P1
        assert snaps[(26, "B")].gap_to_leader == pytest.approx(0.0), (
            "B should be the race leader once both cars have completed their stops"
        )
        assert snaps[(26, "A")].gap_to_leader > 0

    def test_gap_closes_while_b_on_fresh_tyres(self, undercut_cfg):
        """During laps 21-24 B (fresh tyres) gains on A (worn tyres) each lap."""
        result = self._run(undercut_cfg)
        snaps = {(s.lap, s.driver): s for s in result.snapshots}
        # B's gap to leader must shrink monotonically in the window laps 21-24
        gaps = [snaps[(lap, "B")].gap_to_leader for lap in range(21, 25)]
        assert gaps == sorted(gaps, reverse=True), (
            "B's gap should decrease each lap while on fresh tyres"
        )

    def test_overcut_does_not_cancel_undercut(self, undercut_cfg):
        """A's later pit gives it fresher tyres for the final stint,
        but not enough to overcome B's gap built during laps 21-24."""
        result = self._run(undercut_cfg)
        # After A pits (lap 25), A has fresher tyres.  B should still win.
        assert result.finishing_order[0] == "B"
        # And the winning margin is meaningful (not just floating-point noise)
        assert result.total_times["A"] - result.total_times["B"] > 5.0
