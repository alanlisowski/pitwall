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
from engine.sim.config import PaceSetting


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
        # cliff_lap_soft=100 keeps both test points in the linear regime
        cfg = SimConfig(deg_soft=0.10, cliff_lap_soft=100)
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


# ---------------------------------------------------------------------------
# 4. Five named scenario tests
#
# Each test is self-contained, uses hand-built fixtures, and has a comment
# explaining exactly what property is being verified and why it matters.
# ---------------------------------------------------------------------------

def test_fresh_soft_is_faster_than_fresh_hard():
    # The compound_offset component gives SOFT a fixed pace advantage over
    # HARD when both are fresh (tyre_age = 0).  We run two identical cars
    # for one lap — the only difference is their starting compound — and
    # confirm that the SOFT car posts a lower lap time.
    # We zero out degradation and fuel effect so nothing else can interfere.
    cfg = SimConfig(
        offset_soft=-0.80,
        offset_hard=0.00,
        deg_soft=0.0,
        deg_hard=0.0,
        fuel_effect=0.0,
    )
    result = simulate(
        [
            CarStrategy("SOFT_CAR", base_pace=90.0, start_compound="SOFT"),
            CarStrategy("HARD_CAR", base_pace=90.0, start_compound="HARD"),
        ],
        total_laps=1,
        cfg=cfg,
    )

    assert result.total_times["SOFT_CAR"] < result.total_times["HARD_CAR"]

    # The gap should equal exactly the configured compound offset (0.80 s).
    gap = result.total_times["HARD_CAR"] - result.total_times["SOFT_CAR"]
    assert gap == pytest.approx(0.80)


def test_tyres_get_slower_with_age():
    # The tyre_deg component adds (tyre_age × deg_rate) seconds to each lap.
    # With no pit stop, tyre_age grows by 1 every lap, so lap times must
    # increase monotonically.  We disable fuel effect so it can't mask the
    # degradation signal.
    cfg = SimConfig(
        deg_medium=0.10,    # 0.10 s/lap per lap of age — clearly visible
        offset_medium=0.0,
        fuel_effect=0.0,
    )
    result = simulate(
        [CarStrategy("A", base_pace=90.0, start_compound="MEDIUM")],
        total_laps=10,
        cfg=cfg,
    )
    snaps = {s.lap: s for s in result.snapshots}

    # Each lap must be slower than the one before it.
    for lap in range(2, 11):
        assert snaps[lap].lap_time > snaps[lap - 1].lap_time, (
            f"Lap {lap} ({snaps[lap].lap_time:.3f}s) should be slower than "
            f"lap {lap - 1} ({snaps[lap - 1].lap_time:.3f}s)"
        )

    # Over 10 laps the total slowdown must be exactly 9 × 0.10 = 0.90 s
    # (ages 0→9, so the delta between lap 1 and lap 10 is 9 × deg_rate).
    assert snaps[10].lap_time - snaps[1].lap_time == pytest.approx(0.90)


def test_car_gets_faster_late_in_race_from_fuel_burn():
    # The fuel_saving component returns −(lap − 1) × fuel_effect, so lap
    # times decrease by fuel_effect every lap as the tank lightens.
    # We zero out degradation and compound offset to see the fuel signal
    # in isolation: lap times should fall smoothly from lap 1 to lap 50.
    cfg = SimConfig(
        fuel_effect=0.04,   # 0.04 s/lap improvement per lap
        deg_medium=0.0,
        offset_medium=0.0,
    )
    result = simulate(
        [CarStrategy("A", base_pace=90.0, start_compound="MEDIUM")],
        total_laps=50,
        cfg=cfg,
    )
    snaps = {s.lap: s for s in result.snapshots}

    # Every lap must be faster than the previous one.
    for lap in range(2, 51):
        assert snaps[lap].lap_time < snaps[lap - 1].lap_time, (
            f"Lap {lap} should be faster than lap {lap - 1} due to fuel burn"
        )

    # Lap 1 is at max fuel (no saving yet); by lap 50 the car has shed
    # 49 laps of fuel → saving = 49 × 0.04 = 1.96 s.
    assert snaps[1].lap_time - snaps[50].lap_time == pytest.approx(1.96)


def test_pit_stop_costs_between_18_and_25_seconds():
    # The pit_penalty component adds cfg.pit_loss to the lap time whenever
    # a stop is taken.  Real F1 pit-lane losses range from ~18 s (Monza,
    # short pit lane) to ~25 s (Monaco, tight hairpin exit).
    # We check:
    #   (a) the default SimConfig falls within that realistic range, and
    #   (b) the pit lap's recorded time exceeds a normal lap by exactly
    #       pit_loss — no more, no less.
    cfg = SimConfig(
        pit_loss=22.0,      # default; change to test other circuits
        deg_medium=0.0,
        offset_medium=0.0,
        fuel_effect=0.0,
    )
    strat = CarStrategy(
        "A", base_pace=90.0, start_compound="MEDIUM",
        pit_stops=[PitStop(lap=5, compound="HARD")],
    )
    result = simulate([strat], total_laps=10, cfg=cfg)
    snaps = {s.lap: s for s in result.snapshots}

    # Sanity check: the configured penalty is within the realistic F1 range.
    assert 18.0 <= cfg.pit_loss <= 25.0

    # The lap before the stop is a plain reference lap.
    normal_lap = snaps[4].lap_time
    # The pit lap must be exactly pit_loss seconds longer.
    assert snaps[5].lap_time == pytest.approx(normal_lap + cfg.pit_loss)
    # The lap after the stop returns to a normal time (no residual penalty).
    assert snaps[6].lap_time == pytest.approx(normal_lap)


def test_undercut_earlier_pit_leapfrogs_rival():
    # Two cars, identical pace and strategy except for pit timing.
    # Car B pits 5 laps earlier than Car A.
    #
    # What happens lap by lap:
    #   Laps 1-19  : both cars are neck-and-neck on identical worn tyres.
    #   Lap 20     : B pits — takes the ~22 s penalty, falls way behind.
    #   Laps 21-24 : B is on fresh tyres (low deg); A is on worn tyres
    #                (high deg).  B gains ~3 s per lap on A.
    #   Lap 25     : A pits — takes the ~22 s penalty.  By this point B
    #                has recovered enough of the gap that A's penalty puts
    #                B firmly in the lead.
    #   Laps 26-30 : A has fresher tyres but can't close a >10 s gap in
    #                only 5 laps.  B wins.
    #
    # The undercut is NOT hard-coded here — it emerges purely from the
    # tyre_deg and pit_penalty components interacting over the race loop.
    cfg = SimConfig(
        deg_soft=0.15,      # high deg rate makes worn-tyre slowdown obvious
        offset_soft=-0.80,
        pit_loss=22.0,
        fuel_effect=0.0,    # disabled so only tyre effects drive the outcome
    )
    result = simulate(
        [
            CarStrategy("A", base_pace=90.0, start_compound="SOFT",
                        pit_stops=[PitStop(lap=25, compound="SOFT")]),
            CarStrategy("B", base_pace=90.0, start_compound="SOFT",
                        pit_stops=[PitStop(lap=20, compound="SOFT")]),
        ],
        total_laps=30,
        cfg=cfg,
    )
    snaps = {(s.lap, s.driver): s for s in result.snapshots}

    # B dropped behind immediately after pitting (pit_loss penalty).
    assert snaps[(21, "B")].gap_to_leader > 15, (
        "B should be well behind A right after its pit stop"
    )

    # Once A has also pitted, B should be leading.
    assert snaps[(26, "B")].gap_to_leader == pytest.approx(0.0), (
        "B should be the race leader after both cars have completed their stops"
    )

    # B wins overall.
    assert result.finishing_order[0] == "B"


# ---------------------------------------------------------------------------
# 5. Tyre cliff — non-linear degradation
# ---------------------------------------------------------------------------

class TestTyreCliff:
    """The cliff is a kink in the deg curve: rate × cliff_factor above cliff_lap.
    Tests use a convenient cliff at lap 10 with factor 3.0 for clean arithmetic.
    """

    def _cfg(self, **overrides) -> SimConfig:
        base = dict(deg_soft=0.10, cliff_lap_soft=10, cliff_factor_soft=3.0)
        base.update(overrides)
        return SimConfig(**base)

    def test_below_cliff_is_linear(self):
        cfg = self._cfg()
        assert tyre_deg(9, "SOFT", cfg) == pytest.approx(0.10 * 9)

    def test_at_cliff_boundary_is_linear(self):
        # tyre_age == cliff_lap uses the ≤ branch → still linear
        cfg = self._cfg()
        assert tyre_deg(10, "SOFT", cfg) == pytest.approx(0.10 * 10)

    def test_above_cliff_applies_multiplied_rate(self):
        cfg = self._cfg()
        # 5 laps past cliff: 0.10*10 + 0.10*3.0*5 = 1.0 + 1.5 = 2.5
        assert tyre_deg(15, "SOFT", cfg) == pytest.approx(2.5)

    def test_cliff_exceeds_linear_extrapolation(self):
        """Past-cliff deg is worse than a naive linear extrapolation would give."""
        cfg = self._cfg()
        past_cliff = tyre_deg(15, "SOFT", cfg)         # 2.5 (with factor)
        linear_extrap = cfg.deg_rate("SOFT") * 15       # 1.5 (no factor)
        assert past_cliff > linear_extrap

    def test_per_lap_rate_jumps_sharply_at_cliff(self):
        """The extra seconds added per lap is cliff_factor× higher above the cliff."""
        cfg = self._cfg()
        below = tyre_deg(10, "SOFT", cfg) - tyre_deg(9, "SOFT", cfg)   # 0.10
        above = tyre_deg(11, "SOFT", cfg) - tyre_deg(10, "SOFT", cfg)  # 0.30
        assert above == pytest.approx(below * cfg.cliff_factor_soft)

    def test_softer_compound_hits_cliff_sooner(self):
        cfg = SimConfig()
        assert cfg.cliff_lap("SOFT") < cfg.cliff_lap("MEDIUM") < cfg.cliff_lap("HARD")

    def test_softer_compound_has_higher_cliff_factor(self):
        cfg = SimConfig()
        assert cfg.cliff_factor("SOFT") >= cfg.cliff_factor("MEDIUM") >= cfg.cliff_factor("HARD")

    def test_fractional_tyre_age_works_across_cliff(self):
        """tyre_age is float; 10.5 should sit above the cliff and use the steep rate."""
        cfg = self._cfg()
        result = tyre_deg(10.5, "SOFT", cfg)
        expected = 0.10 * 10 + 0.10 * 3.0 * 0.5  # 1.0 + 0.15 = 1.15
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 6. Pace dial — lap-time delta and tyre-wear multiplier
# ---------------------------------------------------------------------------

class TestPaceDial:
    """Verify the five-level pace setting's two effects: lap-time delta and
    wear multiplier.  Wear multiplier tests operate on effective tyre age
    directly (as the runner would accumulate it).
    """

    def test_ordering_of_lap_time_deltas(self):
        cfg = SimConfig()
        assert (
            cfg.pace_delta(PaceSetting.PUSH_HARD)
            < cfg.pace_delta(PaceSetting.PUSH)
            < cfg.pace_delta(PaceSetting.NEUTRAL)
            < cfg.pace_delta(PaceSetting.CONSERVE)
            < cfg.pace_delta(PaceSetting.CONSERVE_HARD)
        )

    def test_neutral_delta_is_zero(self):
        assert SimConfig().pace_delta(PaceSetting.NEUTRAL) == pytest.approx(0.0)

    def test_neutral_wear_is_one(self):
        assert SimConfig().wear_multiplier(PaceSetting.NEUTRAL) == pytest.approx(1.0)

    def test_ordering_of_wear_multipliers(self):
        cfg = SimConfig()
        assert (
            cfg.wear_multiplier(PaceSetting.CONSERVE_HARD)
            < cfg.wear_multiplier(PaceSetting.CONSERVE)
            < cfg.wear_multiplier(PaceSetting.NEUTRAL)
            < cfg.wear_multiplier(PaceSetting.PUSH)
            < cfg.wear_multiplier(PaceSetting.PUSH_HARD)
        )

    def test_push_hard_lap_time_faster_than_neutral(self):
        cfg = SimConfig(deg_soft=0.0, offset_soft=0.0, fuel_effect=0.0)
        push = lap_time(car_pace=90.0, tyre_age=0, compound="SOFT",
                        lap_number=1, is_pit_lap=False, cfg=cfg,
                        pace_setting=PaceSetting.PUSH_HARD)
        neutral = lap_time(car_pace=90.0, tyre_age=0, compound="SOFT",
                           lap_number=1, is_pit_lap=False, cfg=cfg)
        assert push < neutral
        assert neutral - push == pytest.approx(abs(cfg.pace_push_hard_delta))

    def test_conserve_hard_lap_time_slower_than_neutral(self):
        cfg = SimConfig(deg_soft=0.0, offset_soft=0.0, fuel_effect=0.0)
        conserve = lap_time(car_pace=90.0, tyre_age=0, compound="SOFT",
                            lap_number=1, is_pit_lap=False, cfg=cfg,
                            pace_setting=PaceSetting.CONSERVE_HARD)
        neutral = lap_time(car_pace=90.0, tyre_age=0, compound="SOFT",
                           lap_number=1, is_pit_lap=False, cfg=cfg)
        assert conserve > neutral
        assert conserve - neutral == pytest.approx(cfg.pace_conserve_hard_delta)

    def test_effective_age_accumulates_faster_when_pushing(self):
        """10 real laps at PUSH_HARD accumulates 18 effective laps of wear."""
        cfg = SimConfig()
        actual_laps = 10
        eff_push = actual_laps * cfg.wear_multiplier(PaceSetting.PUSH_HARD)
        eff_neutral = actual_laps * cfg.wear_multiplier(PaceSetting.NEUTRAL)
        assert eff_push == pytest.approx(18.0)
        assert eff_neutral == pytest.approx(10.0)
        assert eff_push > eff_neutral

    def test_effective_age_accumulates_slower_when_conserving(self):
        """20 real laps at CONSERVE_HARD accumulates only 10 effective laps of wear."""
        cfg = SimConfig()
        actual_laps = 20
        eff_conserve = actual_laps * cfg.wear_multiplier(PaceSetting.CONSERVE_HARD)
        eff_neutral = actual_laps * cfg.wear_multiplier(PaceSetting.NEUTRAL)
        assert eff_conserve == pytest.approx(10.0)
        assert eff_neutral == pytest.approx(20.0)
        assert eff_conserve < eff_neutral


# ---------------------------------------------------------------------------
# 7. Cliff × pace-dial interaction — the "Race Engineer" scenarios
# ---------------------------------------------------------------------------

class TestCliffAndPaceDialInteraction:
    """End-to-end properties that span both features:
    pushing is faster now but brings the cliff forward;
    conserving is slower now but extends tyre life past the cliff.
    """

    def test_pushing_brings_cliff_forward(self):
        """10 laps of PUSH_HARD crosses the cliff; 10 neutral laps do not.

        SOFT cliff at 16. PUSH_HARD wear=1.8 → 10×1.8=18 > 16 (past cliff).
        Neutral: 10×1.0=10 < 16 (still linear).  Consequently the pusher's
        deg penalty is substantially higher despite fewer real laps driven.
        """
        cfg = SimConfig(deg_soft=0.10, cliff_lap_soft=16, cliff_factor_soft=2.5)
        actual_laps = 10
        eff_push = actual_laps * cfg.wear_multiplier(PaceSetting.PUSH_HARD)    # 18
        eff_neutral = actual_laps * cfg.wear_multiplier(PaceSetting.NEUTRAL)   # 10

        assert eff_push > cfg.cliff_lap("SOFT"), "pusher must be past the cliff"
        assert eff_neutral < cfg.cliff_lap("SOFT"), "neutral must still be linear"
        assert tyre_deg(eff_push, "SOFT", cfg) > tyre_deg(eff_neutral, "SOFT", cfg)

    def test_conserving_delays_cliff(self):
        """20 real laps at CONSERVE_HARD stays below the cliff; neutral exceeds it.

        SOFT cliff at 16. CONSERVE_HARD wear=0.5 → 20×0.5=10 < 16 (linear).
        Neutral: 20×1.0=20 > 16 (past cliff).
        """
        cfg = SimConfig(cliff_lap_soft=16)
        actual_laps = 20
        eff_conserve = actual_laps * cfg.wear_multiplier(PaceSetting.CONSERVE_HARD)  # 10
        eff_neutral = actual_laps * cfg.wear_multiplier(PaceSetting.NEUTRAL)          # 20

        assert eff_conserve < cfg.cliff_lap("SOFT"), "conserved tyre must be below cliff"
        assert eff_neutral > cfg.cliff_lap("SOFT"), "neutral tyre must be past cliff"

    def test_pushing_faster_per_lap_but_steeper_deg_when_past_cliff(self):
        """Push lap time is lower (pace delta wins) but the deg penalty grows sharply
        once effective age crosses the cliff, narrowing the net advantage.

        At real lap 3, pusher effective age = 5.4, neutral = 3 — both below cliff.
        At real lap 10, pusher effective age = 18 > cliff(16), neutral = 10 — still linear.
        We verify the deg delta expands dramatically at the latter point.
        """
        cfg = SimConfig(
            deg_soft=0.10,
            cliff_lap_soft=16,
            cliff_factor_soft=2.5,
            offset_soft=0.0,
            fuel_effect=0.0,
        )

        def net_advantage(actual_laps: int) -> float:
            """Pace-delta gain minus extra deg cost vs neutral, in seconds/lap."""
            eff_push = actual_laps * cfg.wear_multiplier(PaceSetting.PUSH_HARD)
            eff_neutral = actual_laps * cfg.wear_multiplier(PaceSetting.NEUTRAL)
            extra_deg = tyre_deg(eff_push, "SOFT", cfg) - tyre_deg(eff_neutral, "SOFT", cfg)
            pace_gain = abs(cfg.pace_delta(PaceSetting.PUSH_HARD))  # 0.40 s
            return pace_gain - extra_deg

        # Early on (lap 3) pusher advantage is positive: pace gain > extra deg
        assert net_advantage(3) > 0, "pushing should be a net benefit on fresh tyres"
        # The advantage erodes as effective age passes the cliff
        assert net_advantage(3) > net_advantage(10), (
            "pushing advantage must erode as effective age crosses the cliff"
        )
