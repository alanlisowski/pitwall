"""Tests for safety-car event generation (engine.sim.events) and session integration.

Sections:
  1. Pure module — generate_safety_car_schedule, is_sc_active, effective_pit_loss
  2. Session integration — field bunches, pit-loss discount, SC as decision point
  3. AI cheap-stop hook — hard AI pits under SC, easy AI does not
"""
from __future__ import annotations

import random

import pytest

from engine.sim import (
    AiProfile,
    CarStrategy,
    PitStop,
    RaceSession,
    SimConfig,
)
from engine.sim.events import (
    SafetyCarWindow,
    effective_pit_loss,
    generate_safety_car_schedule,
    is_sc_active,
)
from engine.sim.session import EventKind, PitAction, PlayerAction


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _sc_cfg(**overrides) -> SimConfig:
    """SimConfig with SC enabled at 100% probability by default."""
    defaults = dict(
        sc_prob_per_lap=1.0,
        sc_min_duration=3,
        sc_max_duration=3,
        sc_gap_compress_factor=0.30,
        sc_pit_loss_factor=0.35,
    )
    defaults.update(overrides)
    return SimConfig(**defaults)


def _no_sc_cfg() -> SimConfig:
    return SimConfig(sc_prob_per_lap=0.0)


def _drive_to_finish(session: RaceSession):
    state = None
    while True:
        state = session.advance()
        if state.finished:
            return state


# --------------------------------------------------------------------------- #
# 1. Pure module: generate_safety_car_schedule                                  #
# --------------------------------------------------------------------------- #

class TestGenerateSchedule:

    def test_empty_when_prob_zero(self):
        cfg = SimConfig(sc_prob_per_lap=0.0)
        schedule = generate_safety_car_schedule(50, cfg, random.Random(42))
        assert schedule == []

    def test_always_sc_when_prob_one_fixed_duration(self):
        """With prob=1 and fixed 3-lap duration, SC starts on lap 1 → [1, 3]."""
        cfg = _sc_cfg(sc_prob_per_lap=1.0, sc_min_duration=3, sc_max_duration=3)
        schedule = generate_safety_car_schedule(10, cfg, random.Random(0))
        assert schedule[0] == SafetyCarWindow(start_lap=1, end_lap=3)

    def test_windows_are_non_overlapping(self):
        cfg = _sc_cfg(sc_prob_per_lap=0.5, sc_min_duration=2, sc_max_duration=4)
        for seed in range(20):
            schedule = generate_safety_car_schedule(50, cfg, random.Random(seed))
            for i in range(len(schedule) - 1):
                assert schedule[i].end_lap < schedule[i + 1].start_lap

    def test_windows_clamped_to_total_laps(self):
        cfg = _sc_cfg(sc_prob_per_lap=1.0, sc_min_duration=10, sc_max_duration=10)
        schedule = generate_safety_car_schedule(5, cfg, random.Random(0))
        assert schedule[0].end_lap <= 5

    def test_same_seed_same_schedule(self):
        cfg = _sc_cfg(sc_prob_per_lap=0.3)
        s1 = generate_safety_car_schedule(30, cfg, random.Random(7))
        s2 = generate_safety_car_schedule(30, cfg, random.Random(7))
        assert s1 == s2

    def test_different_seeds_different_schedules(self):
        cfg = _sc_cfg(sc_prob_per_lap=0.3)
        s1 = generate_safety_car_schedule(50, cfg, random.Random(1))
        s2 = generate_safety_car_schedule(50, cfg, random.Random(999))
        # Very high probability this differs for such different seeds
        assert s1 != s2

    def test_start_before_end(self):
        cfg = _sc_cfg(sc_prob_per_lap=0.5)
        for seed in range(10):
            for w in generate_safety_car_schedule(30, cfg, random.Random(seed)):
                assert w.start_lap <= w.end_lap


# --------------------------------------------------------------------------- #
# 2. is_sc_active and effective_pit_loss                                        #
# --------------------------------------------------------------------------- #

class TestQueryFunctions:

    _SCHEDULE = [SafetyCarWindow(start_lap=5, end_lap=8)]

    def test_is_active_inside_window(self):
        for lap in (5, 6, 7, 8):
            assert is_sc_active(lap, self._SCHEDULE)

    def test_is_inactive_outside_window(self):
        for lap in (1, 4, 9, 20):
            assert not is_sc_active(lap, self._SCHEDULE)

    def test_inactive_with_empty_schedule(self):
        assert not is_sc_active(10, [])

    def test_pit_loss_full_before_sc(self):
        cfg = SimConfig(pit_loss=22.0, sc_pit_loss_factor=0.35)
        assert effective_pit_loss(4, self._SCHEDULE, cfg) == pytest.approx(22.0)

    def test_pit_loss_discounted_during_sc(self):
        cfg = SimConfig(pit_loss=22.0, sc_pit_loss_factor=0.35)
        for lap in (5, 6, 7, 8):
            assert effective_pit_loss(lap, self._SCHEDULE, cfg) == pytest.approx(22.0 * 0.35)

    def test_pit_loss_full_after_sc(self):
        cfg = SimConfig(pit_loss=22.0, sc_pit_loss_factor=0.35)
        assert effective_pit_loss(9, self._SCHEDULE, cfg) == pytest.approx(22.0)

    def test_pit_loss_multiple_windows(self):
        cfg = SimConfig(pit_loss=20.0, sc_pit_loss_factor=0.35)
        schedule = [SafetyCarWindow(3, 5), SafetyCarWindow(10, 12)]
        for lap in (3, 4, 5, 10, 11, 12):
            assert effective_pit_loss(lap, schedule, cfg) == pytest.approx(20.0 * 0.35)
        for lap in (1, 2, 6, 9, 13):
            assert effective_pit_loss(lap, schedule, cfg) == pytest.approx(20.0)


# --------------------------------------------------------------------------- #
# 3. Session — SC as decision point                                             #
# --------------------------------------------------------------------------- #

class TestScDecisionPoint:

    def _session_with_forced_sc(self, total_laps: int = 20) -> RaceSession:
        """Session where SC always fires on lap 1 (prob=1, fixed 3-lap duration)."""
        cfg = _sc_cfg(total_laps=total_laps) if False else SimConfig(
            sc_prob_per_lap=1.0,
            sc_min_duration=3,
            sc_max_duration=3,
            sc_gap_compress_factor=0.30,
            sc_pit_loss_factor=0.35,
        )
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="MEDIUM"),
            CarStrategy("AI1", base_pace=91.0, start_compound="HARD"),
        ]
        return RaceSession(cars=cars, total_laps=total_laps, player_id="PLAYER",
                           cfg=cfg, seed=0)

    def test_safety_car_deployed_fires_as_event(self):
        """advance() pauses with SAFETY_CAR_DEPLOYED on the SC start lap."""
        session = self._session_with_forced_sc()
        state = session.advance()
        deployed = [e for e in state.events if e.kind == EventKind.SAFETY_CAR_DEPLOYED]
        assert len(deployed) == 1
        assert deployed[0].lap == 1

    def test_sc_active_in_race_state(self):
        """RaceState.sc_active is True on an SC lap."""
        session = self._session_with_forced_sc()
        state = session.advance()
        assert state.sc_active is True

    def test_sc_not_active_outside_window(self):
        """RaceState.sc_active is False on a normal lap."""
        session = self._session_with_forced_sc()
        # Advance past the first SC window (laps 1-3) without decisions
        # SC fires on lap 1, 4, 7, 10, ... (prob=1, so new SC starts every 3 laps)
        # Drive to a lap far into the race without SC
        cfg_no_sc = SimConfig(sc_prob_per_lap=0.0)
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="HARD"),
        ]
        session2 = RaceSession(cars=cars, total_laps=5, player_id="PLAYER",
                               cfg=cfg_no_sc, seed=0)
        state2 = _drive_to_finish(session2)
        assert state2.sc_active is False

    def test_safety_car_cleared_fires_on_end_lap(self):
        """SAFETY_CAR_CLEARED fires on the last SC lap."""
        # With prob=1 and duration=3: SC window [1,3].
        # CLEARED should fire on lap 3.
        session = self._session_with_forced_sc()
        all_events = []
        while True:
            state = session.advance()
            all_events.extend(state.events)
            if state.finished:
                break
        cleared = [e for e in all_events if e.kind == EventKind.SAFETY_CAR_CLEARED]
        assert any(e.lap == 3 for e in cleared), (
            f"Expected CLEARED on lap 3, got: {[(e.kind, e.lap) for e in cleared]}"
        )

    def test_sc_causes_advance_to_pause(self):
        """advance() must return before the race ends when SC fires."""
        session = self._session_with_forced_sc(total_laps=20)
        state = session.advance()
        assert not state.finished   # paused for SC, not at race end


# --------------------------------------------------------------------------- #
# 4. Session — field compression                                                #
# --------------------------------------------------------------------------- #

class TestFieldCompression:

    def test_sc_compresses_field(self):
        """Under SC, following cars' gaps to leader are smaller than without SC."""
        cars = [
            CarStrategy("FAST", base_pace=87.0, start_compound="HARD"),
            CarStrategy("SLOW", base_pace=95.0, start_compound="HARD"),
        ]
        total_laps = 15

        cfg_sc = SimConfig(
            sc_prob_per_lap=1.0,
            sc_min_duration=15,
            sc_max_duration=15,
            sc_gap_compress_factor=0.50,
        )
        cfg_no = SimConfig(sc_prob_per_lap=0.0)

        s_sc = RaceSession(cars=cars, total_laps=total_laps, player_id="SLOW",
                           cfg=cfg_sc, seed=0)
        s_no = RaceSession(cars=cars, total_laps=total_laps, player_id="SLOW",
                           cfg=cfg_no, seed=0)

        gap_sc = next(
            c.gap_to_leader for c in _drive_to_finish(s_sc).cars if c.driver == "SLOW"
        )
        gap_no = next(
            c.gap_to_leader for c in _drive_to_finish(s_no).cars if c.driver == "SLOW"
        )

        assert gap_sc < gap_no, (
            f"SC gap ({gap_sc:.2f}s) should be smaller than normal gap ({gap_no:.2f}s)"
        )

    def test_leader_gap_stays_zero_under_sc(self):
        """Leader's gap_to_leader is always 0, even after field compression."""
        cars = [
            CarStrategy("FAST", base_pace=87.0, start_compound="HARD"),
            CarStrategy("SLOW", base_pace=95.0, start_compound="HARD"),
        ]
        cfg = SimConfig(sc_prob_per_lap=1.0, sc_min_duration=10, sc_max_duration=10,
                        sc_gap_compress_factor=0.50)
        session = RaceSession(cars=cars, total_laps=10, player_id="SLOW", cfg=cfg, seed=0)
        state = _drive_to_finish(session)
        leader = next(c for c in state.cars if c.position == 1)
        assert leader.gap_to_leader == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 5. Session — pit-loss discount through the session                            #
# --------------------------------------------------------------------------- #

class TestPitLossDiscount:

    def test_pitting_under_sc_costs_less_time(self):
        """Total race time is lower when pitting under SC than without SC."""
        # Single-car race, player pits on lap 1.
        # SC covers whole race so pit_loss is discounted on lap 1.
        # sc_gap_compress_factor=0 isolates the pit discount from compression.
        cars = [CarStrategy("PLAYER", base_pace=90.0, start_compound="MEDIUM")]

        cfg_sc = SimConfig(
            sc_prob_per_lap=1.0,
            sc_min_duration=10,
            sc_max_duration=10,
            sc_gap_compress_factor=0.0,
            sc_pit_loss_factor=0.35,
        )
        cfg_no = SimConfig(sc_prob_per_lap=0.0, sc_gap_compress_factor=0.0)

        s_sc = RaceSession(cars=cars, total_laps=5, player_id="PLAYER",
                           cfg=cfg_sc, seed=0)
        s_no = RaceSession(cars=cars, total_laps=5, player_id="PLAYER",
                           cfg=cfg_no, seed=0)

        # Queue pit on lap 1 (will apply on first advance)
        s_sc.decide(PlayerAction(pit=PitAction("HARD")))
        s_no.decide(PlayerAction(pit=PitAction("HARD")))

        time_sc = next(iter(_drive_to_finish(s_sc).cars)).total_time
        time_no = next(iter(_drive_to_finish(s_no).cars)).total_time

        assert time_sc < time_no, (
            f"SC pit time ({time_sc:.3f}s) should be less than normal pit time ({time_no:.3f}s)"
        )

    def test_pit_loss_delta_matches_sc_factor(self):
        """The pit savings equals pit_loss × (1 – sc_pit_loss_factor)."""
        pit_loss = 20.0
        sc_factor = 0.35
        cars = [CarStrategy("PLAYER", base_pace=90.0, start_compound="MEDIUM")]

        cfg_sc = SimConfig(
            pit_loss=pit_loss,
            sc_prob_per_lap=1.0,
            sc_min_duration=10,
            sc_max_duration=10,
            sc_gap_compress_factor=0.0,
            sc_pit_loss_factor=sc_factor,
        )
        cfg_no = SimConfig(
            pit_loss=pit_loss,
            sc_prob_per_lap=0.0,
            sc_gap_compress_factor=0.0,
        )

        s_sc = RaceSession(cars=cars, total_laps=5, player_id="PLAYER",
                           cfg=cfg_sc, seed=0)
        s_no = RaceSession(cars=cars, total_laps=5, player_id="PLAYER",
                           cfg=cfg_no, seed=0)
        s_sc.decide(PlayerAction(pit=PitAction("HARD")))
        s_no.decide(PlayerAction(pit=PitAction("HARD")))

        time_sc = next(iter(_drive_to_finish(s_sc).cars)).total_time
        time_no = next(iter(_drive_to_finish(s_no).cars)).total_time

        expected_saving = pit_loss * (1.0 - sc_factor)
        assert time_no - time_sc == pytest.approx(expected_saving, rel=1e-6)


# --------------------------------------------------------------------------- #
# 6. AI cheap-stop hook                                                         #
# --------------------------------------------------------------------------- #

class TestAiScHook:

    def _session(self, ai_profile: AiProfile, total_laps: int = 20) -> RaceSession:
        cfg = SimConfig(
            sc_prob_per_lap=1.0,
            sc_min_duration=5,
            sc_max_duration=5,
            sc_gap_compress_factor=0.0,
            sc_pit_loss_factor=0.35,
        )
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="HARD"),
            CarStrategy("AI1", base_pace=90.5, start_compound="HARD",
                        pit_stops=[PitStop(lap=40, compound="MEDIUM")]),
        ]
        return RaceSession(
            cars=cars,
            total_laps=total_laps,
            player_id="PLAYER",
            cfg=cfg,
            seed=0,
            ai_profiles={"AI1": ai_profile},
        )

    def test_hard_ai_pits_under_sc(self):
        """Hard AI (pits_under_sc=True) pits on the SC start lap."""
        session = self._session(AiProfile.hard())
        all_events = []
        while True:
            state = session.advance()
            all_events.extend(state.events)
            if state.finished:
                break

        # SC starts on lap 1 (prob=1); hard AI should pit on lap 1
        ai_pits = [
            e.lap for e in all_events
            if e.kind == EventKind.RIVAL_PITTED and e.driver == "AI1"
        ]
        deployed_laps = {
            e.lap for e in all_events if e.kind == EventKind.SAFETY_CAR_DEPLOYED
        }
        assert ai_pits, "AI1 never pitted"
        assert ai_pits[0] in deployed_laps, (
            f"AI1 pitted on lap {ai_pits[0]}, but SC was deployed on {deployed_laps}"
        )

    def test_easy_ai_does_not_pit_under_sc(self):
        """Easy AI (pits_under_sc=False) ignores the SC pit opportunity."""
        session = self._session(AiProfile.easy(), total_laps=20)
        all_events = []
        while True:
            state = session.advance()
            all_events.extend(state.events)
            if state.finished:
                break

        deployed_laps = {
            e.lap for e in all_events if e.kind == EventKind.SAFETY_CAR_DEPLOYED
        }
        ai_pit_laps = {
            e.lap for e in all_events
            if e.kind == EventKind.RIVAL_PITTED and e.driver == "AI1"
        }
        # Easy AI may pit near its planned window (lap 40, beyond 20 laps → maybe not at all)
        # What it must NOT do is pit on any SC start lap
        for lap in ai_pit_laps:
            assert lap not in deployed_laps, (
                f"Easy AI pitted on SC lap {lap}, should not react to SC"
            )

    def test_hard_vs_easy_ai_sc_response(self):
        """Hard AI pits earlier than easy AI in the same SC session."""
        hard_session = self._session(AiProfile.hard())
        easy_session = self._session(AiProfile.easy())

        def first_pit(s: RaceSession) -> int | None:
            events = []
            while True:
                st = s.advance()
                events.extend(st.events)
                if st.finished:
                    break
            pits = [e.lap for e in events
                    if e.kind == EventKind.RIVAL_PITTED and e.driver == "AI1"]
            return pits[0] if pits else None

        hard_lap = first_pit(hard_session)
        easy_lap = first_pit(easy_session)

        assert hard_lap is not None, "Hard AI never pitted"
        if easy_lap is not None:
            assert hard_lap <= easy_lap


# --------------------------------------------------------------------------- #
# 7. Reproducibility                                                            #
# --------------------------------------------------------------------------- #

class TestReproducibility:

    def test_same_seed_same_sc_schedule_in_session(self):
        """Two sessions with the same seed produce identical SC schedules."""
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="MEDIUM"),
            CarStrategy("AI1", base_pace=91.0, start_compound="HARD"),
        ]
        cfg = SimConfig(sc_prob_per_lap=0.4)

        s1 = RaceSession(cars=cars, total_laps=30, player_id="PLAYER", cfg=cfg, seed=99)
        s2 = RaceSession(cars=cars, total_laps=30, player_id="PLAYER", cfg=cfg, seed=99)

        assert s1._sc_schedule == s2._sc_schedule

    def test_same_seed_same_race_outcome(self):
        """Same seed → identical final positions and times."""
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="MEDIUM"),
            CarStrategy("AI1", base_pace=91.0, start_compound="HARD"),
        ]
        cfg = SimConfig(sc_prob_per_lap=0.4)

        t1 = {c.driver: c.total_time
              for c in _drive_to_finish(
                  RaceSession(cars=cars, total_laps=30, player_id="PLAYER", cfg=cfg, seed=5)
              ).cars}
        t2 = {c.driver: c.total_time
              for c in _drive_to_finish(
                  RaceSession(cars=cars, total_laps=30, player_id="PLAYER", cfg=cfg, seed=5)
              ).cars}
        assert t1 == t2

    def test_different_seeds_different_sc_outcomes(self):
        """Different seeds produce different race outcomes when SC is enabled."""
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="MEDIUM"),
            CarStrategy("AI1", base_pace=91.0, start_compound="HARD"),
        ]
        cfg = SimConfig(sc_prob_per_lap=0.5, sc_gap_compress_factor=0.5)

        t1 = {c.driver: c.total_time
              for c in _drive_to_finish(
                  RaceSession(cars=cars, total_laps=30, player_id="PLAYER", cfg=cfg, seed=1)
              ).cars}
        t2 = {c.driver: c.total_time
              for c in _drive_to_finish(
                  RaceSession(cars=cars, total_laps=30, player_id="PLAYER", cfg=cfg, seed=999)
              ).cars}
        assert t1 != t2
