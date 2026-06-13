"""Tests for the rule-based AI strategy module (engine.sim.ai).

Organised in three sections:
  1. AiProfile presets — difficulty ordering and field values
  2. ai_action pure-function tests — each heuristic in isolation
  3. Integration with RaceSession — proves undercut coverage in a real session
"""
from __future__ import annotations

import pytest

from engine.sim import (
    AiProfile,
    CarStrategy,
    PitStop,
    RaceSession,
    SimConfig,
)
from engine.sim.ai import AiCarView, AiDecision, ai_action
from engine.sim.config import PaceSetting
from engine.sim.session import EventKind, PitAction, PlayerAction

# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

_CFG = SimConfig()


def _view(
    driver: str,
    position: int,
    gap: float,
    *,
    compound: str = "MEDIUM",
    tyre_age: float = 0.0,
    pace: PaceSetting = PaceSetting.NEUTRAL,
    pitted_last_lap: bool = False,
) -> AiCarView:
    return AiCarView(
        driver=driver,
        position=position,
        gap_to_leader=gap,
        compound=compound,
        tyre_age=tyre_age,
        pace_setting=pace,
        pitted_last_lap=pitted_last_lap,
    )


def _decide(
    me: AiCarView,
    field: list[AiCarView] | None = None,
    *,
    lap: int = 10,
    total_laps: int = 60,
    planned_pits: dict[int, str] | None = None,
    profile: AiProfile | None = None,
) -> AiDecision:
    return ai_action(
        me=me,
        field=field if field is not None else [me],
        lap=lap,
        total_laps=total_laps,
        planned_pits=planned_pits or {},
        cfg=_CFG,
        profile=profile or AiProfile.hard(),
    )


# --------------------------------------------------------------------------- #
# 1. AiProfile presets                                                          #
# --------------------------------------------------------------------------- #

class TestAiProfile:
    def test_easy_does_not_cover_undercut(self):
        assert not AiProfile.easy().covers_undercut

    def test_medium_does_not_cover_undercut(self):
        assert not AiProfile.medium().covers_undercut

    def test_hard_covers_undercut(self):
        assert AiProfile.hard().covers_undercut

    def test_cliff_reaction_ordering(self):
        easy, med, hard = AiProfile.easy(), AiProfile.medium(), AiProfile.hard()
        assert easy.cliff_reaction_laps < med.cliff_reaction_laps < hard.cliff_reaction_laps

    def test_push_threshold_ordering(self):
        # Easy AI pushes more aggressively (higher threshold = PUSH almost always)
        easy, hard = AiProfile.easy(), AiProfile.hard()
        assert easy.push_gap_threshold > hard.push_gap_threshold

    def test_factory_returns_aiprofile_instance(self):
        for factory in (AiProfile.easy, AiProfile.medium, AiProfile.hard):
            assert isinstance(factory(), AiProfile)

    def test_default_profile_matches_hard(self):
        default = AiProfile()
        hard = AiProfile.hard()
        assert default.cliff_reaction_laps == hard.cliff_reaction_laps
        assert default.covers_undercut == hard.covers_undercut


# --------------------------------------------------------------------------- #
# 2. ai_action — heuristic unit tests                                           #
# --------------------------------------------------------------------------- #

class TestAiAction:

    # -- cliff protection --

    def test_pits_when_cliff_imminent_hard(self):
        # SOFT cliff at 16; tyre_age 13 → laps_to_cliff=3 ≤ cliff_reaction_laps(3)
        me = _view("AI", 1, 0.0, compound="SOFT", tyre_age=13.0)
        decision = _decide(me, profile=AiProfile.hard())
        assert decision.pit_compound is not None

    def test_pits_when_past_cliff_hard(self):
        # tyre_age 17 → laps_to_cliff = -1 ≤ 3
        me = _view("AI", 1, 0.0, compound="SOFT", tyre_age=17.0)
        decision = _decide(me, profile=AiProfile.hard())
        assert decision.pit_compound is not None

    def test_no_pit_when_cliff_far(self):
        # tyre_age 5 → laps_to_cliff = 11 > 3; no planned stop
        me = _view("AI", 1, 0.0, compound="SOFT", tyre_age=5.0)
        decision = _decide(me)
        assert decision.pit_compound is None

    def test_easy_only_pits_at_cliff(self):
        # EASY: cliff_reaction_laps=0 → only when laps_to_cliff ≤ 0
        me = _view("AI", 1, 0.0, compound="SOFT", tyre_age=13.0)
        decision = _decide(me, profile=AiProfile.easy())
        # laps_to_cliff = 3 > 0 → no pit
        assert decision.pit_compound is None

        me_over = _view("AI", 1, 0.0, compound="SOFT", tyre_age=16.0)
        decision_over = _decide(me_over, profile=AiProfile.easy())
        # laps_to_cliff = 0 ≤ 0 → pit
        assert decision_over.pit_compound is not None

    # -- planned window --

    def test_pits_within_planned_window(self):
        # planned stop at lap 20; hard window ±3 → valid at lap 18
        me = _view("AI", 1, 0.0, compound="HARD", tyre_age=5.0)
        decision = _decide(me, lap=18, planned_pits={20: "SOFT"})
        assert decision.pit_compound == "SOFT"

    def test_pits_at_exact_planned_lap(self):
        me = _view("AI", 1, 0.0, compound="HARD", tyre_age=5.0)
        decision = _decide(me, lap=20, planned_pits={20: "SOFT"})
        assert decision.pit_compound == "SOFT"

    def test_no_pit_outside_window(self):
        me = _view("AI", 1, 0.0, compound="HARD", tyre_age=5.0)
        decision = _decide(me, lap=10, planned_pits={20: "SOFT"})
        assert decision.pit_compound is None

    def test_easy_narrow_window(self):
        # easy pit_window=1; planned=20; window [19,21]
        me = _view("AI", 1, 0.0, compound="HARD", tyre_age=5.0)
        no_pit = _decide(me, lap=17, planned_pits={20: "SOFT"}, profile=AiProfile.easy())
        in_window = _decide(me, lap=19, planned_pits={20: "SOFT"}, profile=AiProfile.easy())
        assert no_pit.pit_compound is None
        assert in_window.pit_compound == "SOFT"

    # -- too late to pit --

    def test_no_pit_when_too_late(self):
        # hard: no_pit_final_laps=8; total=50, lap=44 → laps_remaining=6 < 8
        me = _view("AI", 1, 0.0, compound="SOFT", tyre_age=14.0)
        decision = _decide(me, lap=44, total_laps=50, profile=AiProfile.hard())
        assert decision.pit_compound is None

    def test_can_still_pit_just_before_cutoff(self):
        # lap=42, laps_remaining=8, no_pit_final_laps=8 → NOT too late
        me = _view("AI", 1, 0.0, compound="SOFT", tyre_age=14.0)
        decision = _decide(me, lap=42, total_laps=50, profile=AiProfile.hard())
        # laps_to_cliff = 16 - 14 = 2 ≤ 3 → cliff pit fires
        assert decision.pit_compound is not None

    # -- undercut coverage --

    def test_covers_undercut_when_nearby_rival_pitted(self):
        # Rival was ~1s behind, pitted, now shows gap ~23s (pit_loss 22 + 1)
        me = _view("AI", 1, 0.0, compound="MEDIUM", tyre_age=5.0)
        rival = _view("R", 2, 22.5 + _CFG.pit_loss, compound="HARD", tyre_age=0.0,
                      pitted_last_lap=True)
        # pre_pit_gap_approx = (22.5 + pit_loss) - pit_loss = 22.5 — too large
        # Use a closer gap:
        rival_close = _view("R", 2, 1.0 + _CFG.pit_loss, compound="HARD", tyre_age=0.0,
                            pitted_last_lap=True)
        field = [me, rival_close]
        decision = _decide(me, field, planned_pits={20: "HARD"})
        # pre_pit_gap_approx = 1.0 ≤ 3.0 → cover
        assert decision.pit_compound == "HARD"

    def test_no_cover_when_gap_too_large(self):
        # Rival was 30s behind before pitting; no cover needed
        me = _view("AI", 1, 0.0, compound="MEDIUM", tyre_age=5.0)
        rival = _view("R", 2, 30.0 + _CFG.pit_loss, compound="HARD", tyre_age=0.0,
                      pitted_last_lap=True)
        decision = _decide(me, [me, rival], planned_pits={20: "HARD"})
        # pre_pit_gap_approx = 30.0 > 3.0 (hard undercut_cover_gap)
        assert decision.pit_compound is None

    def test_no_cover_for_rival_ahead(self):
        # Rival AHEAD of us pitted; not an undercut from behind
        me = _view("AI", 2, 5.0, compound="MEDIUM", tyre_age=5.0)
        rival_ahead = _view("R", 1, 0.0, pitted_last_lap=True)
        decision = _decide(me, [rival_ahead, me], planned_pits={20: "HARD"})
        assert decision.pit_compound is None

    def test_easy_ai_ignores_undercut(self):
        me = _view("AI", 1, 0.0, compound="MEDIUM", tyre_age=5.0)
        rival = _view("R", 2, 1.0 + _CFG.pit_loss, compound="HARD", tyre_age=0.0,
                      pitted_last_lap=True)
        decision = _decide(me, [me, rival], planned_pits={20: "HARD"},
                           profile=AiProfile.easy())
        assert decision.pit_compound is None

    def test_planned_compound_used_when_covering(self):
        me = _view("AI", 1, 0.0, compound="MEDIUM", tyre_age=5.0)
        rival = _view("R", 2, 1.0 + _CFG.pit_loss, tyre_age=0.0, pitted_last_lap=True)
        decision = _decide(me, [me, rival], planned_pits={20: "SOFT"})
        assert decision.pit_compound == "SOFT"  # uses planned compound

    def test_hard_fallback_compound_when_no_planned_stop(self):
        me = _view("AI", 1, 0.0, compound="SOFT", tyre_age=14.0)
        decision = _decide(me, planned_pits={})  # no planned stops
        # cliff fires → uses HARD as fallback
        assert decision.pit_compound == "HARD"

    # -- pace dial --

    def test_push_when_close_to_car_ahead(self):
        # gap_ahead = 5.0 - 3.5 = 1.5 < push_gap_threshold(2.0)
        me = _view("AI", 2, 5.0)
        car_ahead = _view("X", 1, 3.5)
        decision = _decide(me, [car_ahead, me])
        assert decision.pace == PaceSetting.PUSH

    def test_no_push_when_gap_comfortable(self):
        me = _view("AI", 2, 10.0)
        car_ahead = _view("X", 1, 0.0)
        decision = _decide(me, [car_ahead, me])
        # gap = 10.0 > push_gap_threshold(2.0)
        assert decision.pace != PaceSetting.PUSH

    def test_conserve_when_big_lead(self):
        me = _view("AI", 1, 0.0)
        car_behind = _view("Y", 2, 8.0)
        decision = _decide(me, [me, car_behind])
        # gap_behind = 8.0 > conserve_lead_threshold(5.0)
        assert decision.pace == PaceSetting.CONSERVE

    def test_neutral_when_in_midfield(self):
        me = _view("AI", 2, 5.0)
        car_ahead = _view("X", 1, 2.0)    # gap 3.0 > push_threshold 2.0
        car_behind = _view("Y", 3, 8.0)   # gap 3.0 < conserve_threshold 5.0
        decision = _decide(me, [car_ahead, me, car_behind])
        assert decision.pace == PaceSetting.NEUTRAL

    def test_no_push_when_leading(self):
        # P1 has no car ahead → no push triggered
        me = _view("AI", 1, 0.0)
        decision = _decide(me, [me])
        assert decision.pace != PaceSetting.PUSH

    def test_no_conserve_when_last(self):
        # P-last has no car behind → no conserve triggered
        me = _view("AI", 3, 20.0)
        c1 = _view("X", 1, 0.0)
        c2 = _view("Y", 2, 8.0)
        decision = _decide(me, [c1, c2, me])
        assert decision.pace != PaceSetting.CONSERVE

    def test_easy_ai_usually_pushes(self):
        # Easy: push_gap_threshold=15.0; almost any gap triggers PUSH
        me = _view("AI", 2, 12.0)
        car_ahead = _view("X", 1, 0.0)
        decision = _decide(me, [car_ahead, me], profile=AiProfile.easy())
        # gap=12 < push_threshold(15) → PUSH
        assert decision.pace == PaceSetting.PUSH


# --------------------------------------------------------------------------- #
# 3. Integration: RaceSession with AI profiles                                  #
# --------------------------------------------------------------------------- #

class TestAiIntegrationWithSession:

    def _make_undercut_session(self, ai_profile: AiProfile) -> RaceSession:
        """
        Three-car setup for undercut coverage tests:
          PACER  — slow car that pits on lap 5 (triggers first advance() pause)
          PLAYER — slightly slower than AI1, pits on lap 6 (undercut attempt)
          AI1    — the car under test; planned stop lap 20
        """
        cfg = SimConfig()
        cars = [
            CarStrategy("PLAYER", base_pace=90.01, start_compound="MEDIUM"),
            CarStrategy("AI1", base_pace=90.0, start_compound="MEDIUM",
                        pit_stops=[PitStop(lap=20, compound="HARD")]),
            CarStrategy("PACER", base_pace=95.0, start_compound="MEDIUM",
                        pit_stops=[PitStop(lap=5, compound="HARD")]),
        ]
        return RaceSession(
            cars=cars,
            total_laps=30,
            player_id="PLAYER",
            cfg=cfg,
            seed=0,
            ai_profiles={"AI1": ai_profile},
        )

    def _find_first_pit_lap(self, session: RaceSession, driver: str) -> int | None:
        """Drive session to finish, return the first lap `driver` pitted."""
        first_pit: int | None = None
        # Prime the session: advance to lap-5 event, then pit the player.
        state = session.advance()
        session.decide(PlayerAction(pit=PitAction("HARD")))
        # Continue driving.
        while True:
            state = session.advance()
            if first_pit is None:
                for e in state.events:
                    if e.kind == EventKind.RIVAL_PITTED and e.driver == driver:
                        first_pit = e.lap
                        break
            if state.finished:
                break
        return first_pit

    def test_hard_ai_covers_undercut_early(self):
        """HARD AI pits shortly after the player to cover the undercut."""
        session = self._make_undercut_session(AiProfile.hard())
        ai1_pit_lap = self._find_first_pit_lap(session, "AI1")
        assert ai1_pit_lap is not None, "AI1 never pitted"
        # AI1 planned stop was lap 20; covering should fire around lap 7
        assert ai1_pit_lap <= 10, f"AI1 pitted on lap {ai1_pit_lap}, expected ≤ 10"

    def test_easy_ai_does_not_cover_undercut(self):
        """EASY AI ignores the undercut and pits near its planned window."""
        session = self._make_undercut_session(AiProfile.easy())
        ai1_pit_lap = self._find_first_pit_lap(session, "AI1")
        assert ai1_pit_lap is not None, "AI1 never pitted"
        # EASY has pit_window=1; planned=20; window [19,21] → pits on lap 19
        assert ai1_pit_lap >= 15, f"AI1 pitted on lap {ai1_pit_lap}, expected ≥ 15 (no cover)"

    def test_hard_pits_earlier_than_easy(self):
        """Hard AI always pits before Easy AI in the undercut scenario."""
        hard_lap = self._find_first_pit_lap(self._make_undercut_session(AiProfile.hard()), "AI1")
        easy_lap = self._find_first_pit_lap(self._make_undercut_session(AiProfile.easy()), "AI1")
        assert hard_lap is not None and easy_lap is not None
        assert hard_lap < easy_lap

    def test_ai_pit_consumes_planned_stop_no_double_pit(self):
        """After AI covers on lap 7, it must not pit again at the planned window."""
        session = self._make_undercut_session(AiProfile.hard())

        # Advance to lap-5 event
        session.advance()
        session.decide(PlayerAction(pit=PitAction("HARD")))

        ai1_pit_laps: list[int] = []
        while True:
            state = session.advance()
            for e in state.events:
                if e.kind == EventKind.RIVAL_PITTED and e.driver == "AI1":
                    ai1_pit_laps.append(e.lap)
            if state.finished:
                break

        # AI1 should pit exactly once (undercut cover), not again at lap ~20
        assert len(ai1_pit_laps) == 1, f"AI1 pitted {len(ai1_pit_laps)} times: {ai1_pit_laps}"

    def test_session_without_ai_profiles_unchanged(self):
        """Omitting ai_profiles leaves pre-planned pit behaviour intact."""
        cfg = SimConfig()
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="HARD"),
            CarStrategy("AI1", base_pace=90.5, start_compound="HARD",
                        pit_stops=[PitStop(lap=10, compound="MEDIUM")]),
        ]
        session = RaceSession(cars=cars, total_laps=20, player_id="PLAYER",
                              cfg=cfg, seed=0)
        ai1_pit_laps: list[int] = []
        while True:
            state = session.advance()
            for e in state.events:
                if e.kind == EventKind.RIVAL_PITTED and e.driver == "AI1":
                    ai1_pit_laps.append(e.lap)
            if state.finished:
                break
        assert ai1_pit_laps == [10]

    def test_ai_pace_dial_applied_in_session(self):
        """AI car's pace setting is reflected in the state after advance()."""
        cfg = SimConfig()
        cars = [
            CarStrategy("PLAYER", base_pace=90.0, start_compound="HARD"),
            CarStrategy("AI1", base_pace=90.5, start_compound="HARD"),
        ]
        # HARD profile pushes when within 2s; both cars close → AI1 should PUSH
        session = RaceSession(cars=cars, total_laps=5, player_id="PLAYER",
                              cfg=cfg, seed=0, ai_profiles={"AI1": AiProfile.hard()})
        while True:
            state = session.advance()
            if state.finished:
                break
        ai1_state = next(c for c in state.cars if c.driver == "AI1")
        # AI1 was trailing PLAYER (faster car) by a small gap → PUSH expected
        assert ai1_state.pace_setting == PaceSetting.PUSH
