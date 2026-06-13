"""Tests for the interactive RaceSession.

Covers:
  1. Lifecycle: race finishes at the right lap, all cars present, valid positions
  2. Determinism: same seed → identical outcome
  3. Decision points: RIVAL_PITTED and TYRE_CLIFF_WARNING fire at the right laps
  4. decide(): pit is applied on the very next lap; pace dial affects tyre wear
  5. Error handling: decide()/advance() after finish
  6. Regression: no-decision session matches simulate() numerically
"""
from __future__ import annotations

import pytest

from engine.sim import CarStrategy, PitStop, SimConfig, simulate
from engine.sim.config import PaceSetting
from engine.sim.session import (
    EventKind,
    PitAction,
    PlayerAction,
    RaceSession,
    RaceState,
    SessionEvent,
)

# --------------------------------------------------------------------------- #
# Shared fixtures                                                               #
# --------------------------------------------------------------------------- #

_TOTAL_LAPS = 20
_PLAYER = "PLAYER"


def _make_session(
    seed: int = 42,
    total_laps: int = _TOTAL_LAPS,
    player_compound: str = "MEDIUM",
    ai1_pit_lap: int = 10,
) -> RaceSession:
    """Standard 3-car session: player on MEDIUM, two AI cars with planned stops."""
    cars = [
        CarStrategy(_PLAYER, base_pace=90.0, start_compound=player_compound),
        CarStrategy("AI1", base_pace=90.5, start_compound="MEDIUM",
                    pit_stops=[PitStop(lap=ai1_pit_lap, compound="HARD")]),
        CarStrategy("AI2", base_pace=91.0, start_compound="SOFT",
                    pit_stops=[PitStop(lap=8, compound="MEDIUM")]),
    ]
    return RaceSession(cars=cars, total_laps=total_laps, player_id=_PLAYER,
                       cfg=SimConfig(), seed=seed)


def _drive_to_finish(session: RaceSession) -> RaceState:
    """Drive to completion making no decisions; return the terminal state."""
    state = None
    while True:
        state = session.advance()
        if state.finished:
            return state


def _car(state: RaceState, driver: str) -> object:
    """Return the CarState for a named driver."""
    return next(c for c in state.cars if c.driver == driver)


# --------------------------------------------------------------------------- #
# 1. Lifecycle                                                                  #
# --------------------------------------------------------------------------- #

class TestLifecycle:
    def test_race_finishes_at_correct_lap(self):
        state = _drive_to_finish(_make_session())
        assert state.finished
        assert state.lap == _TOTAL_LAPS

    def test_all_cars_present_at_finish(self):
        state = _drive_to_finish(_make_session())
        drivers = {c.driver for c in state.cars}
        assert drivers == {_PLAYER, "AI1", "AI2"}

    def test_positions_are_1_to_n(self):
        state = _drive_to_finish(_make_session())
        positions = sorted(c.position for c in state.cars)
        assert positions == list(range(1, len(state.cars) + 1))

    def test_positions_valid_at_every_pause(self):
        session = _make_session()
        while True:
            state = session.advance()
            positions = sorted(c.position for c in state.cars)
            assert positions == list(range(1, len(state.cars) + 1))
            if state.finished:
                break

    def test_race_finish_event_on_last_lap(self):
        state = _drive_to_finish(_make_session())
        finish_events = [e for e in state.events if e.kind == EventKind.RACE_FINISH]
        assert len(finish_events) == 1
        assert finish_events[0].lap == _TOTAL_LAPS

    def test_lap_counter_never_goes_backwards(self):
        session = _make_session()
        prev = 0
        while True:
            state = session.advance()
            assert state.lap > prev
            prev = state.lap
            if state.finished:
                break

    def test_leader_gap_is_zero(self):
        state = _drive_to_finish(_make_session())
        leader = next(c for c in state.cars if c.position == 1)
        assert leader.gap_to_leader == pytest.approx(0.0)

    def test_non_leader_gap_positive(self):
        state = _drive_to_finish(_make_session())
        for c in state.cars:
            if c.position > 1:
                assert c.gap_to_leader > 0.0


# --------------------------------------------------------------------------- #
# 2. Determinism                                                                #
# --------------------------------------------------------------------------- #

class TestDeterminism:
    def test_same_seed_same_finish_times(self):
        s1, s2 = _make_session(seed=7), _make_session(seed=7)
        t1 = {c.driver: c.total_time for c in _drive_to_finish(s1).cars}
        t2 = {c.driver: c.total_time for c in _drive_to_finish(s2).cars}
        assert t1 == t2

    def test_same_seed_same_event_sequence(self):
        s1, s2 = _make_session(seed=0), _make_session(seed=0)
        events1, events2 = [], []
        while True:
            st1 = s1.advance()
            st2 = s2.advance()
            events1.extend(st1.events)
            events2.extend(st2.events)
            assert st1.lap == st2.lap
            if st1.finished:
                break
        assert [(e.lap, e.kind, e.driver) for e in events1] == \
               [(e.lap, e.kind, e.driver) for e in events2]

    def test_different_seeds_produce_same_result_when_no_randomness(self):
        # Current engine has no stochastic elements; seed doesn't change outcome.
        t1 = {c.driver: c.total_time for c in _drive_to_finish(_make_session(seed=1)).cars}
        t2 = {c.driver: c.total_time for c in _drive_to_finish(_make_session(seed=999)).cars}
        assert t1 == t2


# --------------------------------------------------------------------------- #
# 3. Decision points                                                            #
# --------------------------------------------------------------------------- #

class TestDecisionPoints:
    def test_rival_pit_pauses_advance(self):
        """advance() must pause on the lap AI1 pits."""
        session = _make_session(ai1_pit_lap=5)
        rival_pit_laps = []
        while True:
            state = session.advance()
            for e in state.events:
                if e.kind == EventKind.RIVAL_PITTED and e.driver == "AI1":
                    rival_pit_laps.append(e.lap)
            if state.finished:
                break
        assert rival_pit_laps == [5]

    def test_rival_pit_event_contains_correct_driver(self):
        session = _make_session(ai1_pit_lap=6)
        while True:
            state = session.advance()
            rival_events = [e for e in state.events if e.kind == EventKind.RIVAL_PITTED]
            if rival_events:
                # The event lap == state.lap (we stopped at that lap)
                assert all(e.lap == state.lap for e in rival_events)
                break
            if state.finished:
                break

    def test_both_ai_pit_events_are_reported(self):
        """AI1 on lap 10, AI2 on lap 8 — both RIVAL_PITTED events must fire."""
        session = _make_session()
        seen = set()
        while True:
            state = session.advance()
            for e in state.events:
                if e.kind == EventKind.RIVAL_PITTED:
                    seen.add(e.driver)
            if state.finished:
                break
        assert seen == {"AI1", "AI2"}

    def test_tyre_cliff_warning_fires_before_cliff(self):
        """With SOFT start (cliff=16), warning fires when effective age reaches 13."""
        # Player on SOFT, NEUTRAL pace (wear 1.0/lap): age 13 after lap 13.
        # laps_to_cliff = 16 - 13 = 3 → warning fires.
        # AI pits on lap 99 (beyond race) so only cliff warning is first event.
        cars = [
            CarStrategy(_PLAYER, base_pace=90.0, start_compound="SOFT"),
            CarStrategy("AI1", base_pace=91.0, start_compound="HARD"),
        ]
        session = RaceSession(cars=cars, total_laps=20, player_id=_PLAYER,
                              cfg=SimConfig(), seed=0)
        while True:
            state = session.advance()
            cliff_events = [e for e in state.events if e.kind == EventKind.TYRE_CLIFF_WARNING]
            if cliff_events:
                age = _car(state, _PLAYER).tyre_age  # type: ignore[attr-defined]
                cliff = SimConfig().cliff_lap("SOFT")
                assert cliff - age <= RaceSession._CLIFF_WARNING_LAPS
                assert cliff - age > 0
                break
            assert not state.finished, "race ended before cliff warning fired"

    def test_tyre_cliff_warning_fires_exactly_once_per_tyre_set(self):
        """The warning fires once; subsequent laps don't re-fire until a pit."""
        cars = [
            CarStrategy(_PLAYER, base_pace=90.0, start_compound="SOFT"),
            CarStrategy("AI1", base_pace=91.0, start_compound="HARD"),
        ]
        session = RaceSession(cars=cars, total_laps=20, player_id=_PLAYER,
                              cfg=SimConfig(), seed=0)
        warnings = []
        while True:
            state = session.advance()
            warnings.extend(e for e in state.events if e.kind == EventKind.TYRE_CLIFF_WARNING)
            if state.finished:
                break
        assert len(warnings) == 1

    def test_cliff_warning_resets_after_player_pits(self):
        """After player pits, a new warning can fire on the fresh set."""
        # Player: SOFT→pit on lap 5 to SOFT again→second warning on lap 5+13=18.
        cfg = SimConfig()
        cliff = cfg.cliff_lap("SOFT")  # 16
        warning_age = cliff - RaceSession._CLIFF_WARNING_LAPS  # 13
        # Second warning lap = 5 (pit lap, age reset to 0) + warning_age = 18
        cars = [
            CarStrategy(_PLAYER, base_pace=90.0, start_compound="SOFT"),
            CarStrategy("AI1", base_pace=91.0, start_compound="HARD"),
        ]
        session = RaceSession(cars=cars, total_laps=30, player_id=_PLAYER, cfg=cfg, seed=0)

        warnings: list[SessionEvent] = []
        pitted = False
        while True:
            state = session.advance()
            warnings.extend(e for e in state.events if e.kind == EventKind.TYRE_CLIFF_WARNING)

            # Pit on the first warning lap so new set starts immediately after
            if not pitted and any(e.kind == EventKind.TYRE_CLIFF_WARNING for e in state.events):
                session.decide(PlayerAction(pit=PitAction("SOFT")))
                pitted = True

            if state.finished:
                break

        # Should have two warnings: one on original set, one on fresh set
        assert len(warnings) == 2
        assert warnings[0].kind == EventKind.TYRE_CLIFF_WARNING
        assert warnings[1].kind == EventKind.TYRE_CLIFF_WARNING
        assert warnings[1].lap > warnings[0].lap


# --------------------------------------------------------------------------- #
# 4. decide()                                                                   #
# --------------------------------------------------------------------------- #

class TestDecide:
    def test_pit_applied_on_next_lap(self):
        """After decide(PitAction), the player pits on exactly the next lap.

        Scenario: AI2 pits lap 8, AI1 pits lap 9.  We call decide() after the
        lap-8 pause; the next advance() runs lap 9 where both the player and AI1
        pit, producing an event on that lap so we can inspect pitted_this_lap.
        """
        cars = [
            CarStrategy(_PLAYER, base_pace=90.0, start_compound="MEDIUM"),
            CarStrategy("AI1", base_pace=90.5, start_compound="MEDIUM",
                        pit_stops=[PitStop(lap=9, compound="HARD")]),
            CarStrategy("AI2", base_pace=91.0, start_compound="SOFT",
                        pit_stops=[PitStop(lap=8, compound="MEDIUM")]),
        ]
        session = RaceSession(cars=cars, total_laps=_TOTAL_LAPS, player_id=_PLAYER,
                              cfg=SimConfig(), seed=42)

        state = session.advance()           # pauses at lap 8: AI2 pits
        assert state.lap == 8
        session.decide(PlayerAction(pit=PitAction("HARD")))

        state = session.advance()           # runs lap 9: player + AI1 both pit
        assert state.lap == 9
        player = _car(state, _PLAYER)
        assert player.pitted_this_lap       # type: ignore[attr-defined]
        assert player.compound == "HARD"    # type: ignore[attr-defined]
        assert player.tyre_age == pytest.approx(0.0)  # type: ignore[attr-defined]

    def test_pit_changes_compound(self):
        """After pitting to HARD, player compound becomes HARD."""
        session = _make_session()
        decided = False
        while True:
            state = session.advance()
            if not decided:
                session.decide(PlayerAction(pit=PitAction("HARD")))
                decided = True
            else:
                player = _car(state, _PLAYER)
                if player.pitted_this_lap:  # type: ignore[attr-defined]
                    assert player.compound == "HARD"  # type: ignore[attr-defined]
                    assert player.tyre_age == pytest.approx(0.0)  # type: ignore[attr-defined]
                    break
            if state.finished:
                break

    def test_pace_push_hard_accelerates_tyre_wear(self):
        """PUSH_HARD (wear×1.8) should give higher tyre age than NEUTRAL after N laps."""
        cfg = SimConfig()
        cars_base = [
            CarStrategy(_PLAYER, base_pace=90.0, start_compound="HARD"),
            CarStrategy("DUMMY", base_pace=91.0, start_compound="HARD"),
        ]

        # NEUTRAL session — no pits, no pace change
        s_neutral = RaceSession(cars=cars_base, total_laps=5, player_id=_PLAYER, cfg=cfg, seed=0)
        s_push = RaceSession(cars=cars_base, total_laps=5, player_id=_PLAYER, cfg=cfg, seed=0)
        s_push.decide(PlayerAction(pace=PaceSetting.PUSH_HARD))

        st_neutral = _drive_to_finish(s_neutral)
        st_push = _drive_to_finish(s_push)

        age_neutral = _car(st_neutral, _PLAYER).tyre_age   # type: ignore[attr-defined]
        age_push = _car(st_push, _PLAYER).tyre_age         # type: ignore[attr-defined]

        assert age_push > age_neutral

    def test_pace_conserve_slows_tyre_wear(self):
        cfg = SimConfig()
        cars_base = [
            CarStrategy(_PLAYER, base_pace=90.0, start_compound="HARD"),
            CarStrategy("DUMMY", base_pace=91.0, start_compound="HARD"),
        ]
        s_neutral = RaceSession(cars=cars_base, total_laps=5, player_id=_PLAYER, cfg=cfg, seed=0)
        s_conserve = RaceSession(cars=cars_base, total_laps=5, player_id=_PLAYER, cfg=cfg, seed=0)
        s_conserve.decide(PlayerAction(pace=PaceSetting.CONSERVE_HARD))

        age_neutral = _car(_drive_to_finish(s_neutral), _PLAYER).tyre_age   # type: ignore[attr-defined]
        age_conserve = _car(_drive_to_finish(s_conserve), _PLAYER).tyre_age # type: ignore[attr-defined]

        assert age_conserve < age_neutral

    def test_decide_after_finish_raises(self):
        session = _make_session()
        _drive_to_finish(session)
        with pytest.raises(RuntimeError, match="finished"):
            session.decide(PlayerAction())

    def test_advance_after_finish_returns_finished_state(self):
        session = _make_session()
        _drive_to_finish(session)
        state = session.advance()
        assert state.finished
        assert state.lap == _TOTAL_LAPS
        assert state.events == []

    def test_advance_after_finish_is_stable(self):
        """Multiple advance() calls after finish return the same times."""
        session = _make_session()
        final = _drive_to_finish(session)
        times1 = {c.driver: c.total_time for c in final.cars}

        second = session.advance()
        times2 = {c.driver: c.total_time for c in second.cars}

        assert times1 == times2


# --------------------------------------------------------------------------- #
# 5. Regression: session with no decisions matches simulate()                  #
# --------------------------------------------------------------------------- #

def test_matches_simulate_no_pits():
    """With no player decisions and NEUTRAL pace, session must match simulate()
    exactly: same total times, same finishing order."""
    cfg = SimConfig()
    total_laps = 15
    cars = [
        CarStrategy("P", base_pace=90.0, start_compound="HARD"),
        CarStrategy("A", base_pace=90.3, start_compound="HARD"),
        CarStrategy("B", base_pace=91.0, start_compound="HARD"),
    ]
    # No pits, HARD compound (cliff at 42, well beyond 15 laps), so no events
    # until RACE_FINISH — advance() runs all laps in one call.
    session = RaceSession(cars=cars, total_laps=total_laps, player_id="P", cfg=cfg, seed=0)
    session_state = _drive_to_finish(session)
    session_times = {c.driver: c.total_time for c in session_state.cars}

    sim_result = simulate(cars, total_laps=total_laps, cfg=cfg)

    for driver in ("P", "A", "B"):
        assert session_times[driver] == pytest.approx(sim_result.total_times[driver], rel=1e-9)

    session_order = [c.driver for c in sorted(session_state.cars, key=lambda c: c.position)]
    assert session_order == sim_result.finishing_order


def test_invalid_player_id_raises():
    cars = [CarStrategy("VER", base_pace=90.0, start_compound="MEDIUM")]
    with pytest.raises(ValueError, match="player_id"):
        RaceSession(cars=cars, total_laps=70, player_id="HAM", cfg=SimConfig(), seed=0)
