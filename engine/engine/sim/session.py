"""Interactive race session — plays a race one decision at a time.

Public API
----------
RaceSession  — create once, then call advance()/decide() in a loop
RaceState    — snapshot returned by advance()
CarState     — one car's current race state
SessionEvent — a notable occurrence that triggered the current pause
EventKind    — enum of event types
PitAction    — pit + compound choice
PlayerAction — combined pit + pace instruction
"""
from __future__ import annotations

import dataclasses
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .ai import AiCarView, AiDecision, AiProfile, ai_action
from .components import lap_time as _lap_time
from .config import PaceSetting, SimConfig
from .events import SafetyCarWindow, generate_safety_car_schedule, is_sc_active
from .strategy import CarStrategy


# --------------------------------------------------------------------------- #
# Public types                                                                  #
# --------------------------------------------------------------------------- #

class EventKind(Enum):
    """Events that trigger a decision-point pause in advance()."""
    RIVAL_PITTED = "rival_pitted"
    TYRE_CLIFF_WARNING = "tyre_cliff_warning"
    RACE_FINISH = "race_finish"
    SAFETY_CAR_DEPLOYED = "safety_car_deployed"
    SAFETY_CAR_CLEARED = "safety_car_cleared"


@dataclass
class SessionEvent:
    """An event that occurred since the last advance() call."""
    lap: int
    kind: EventKind
    driver: str  # driver that triggered the event


@dataclass
class CarState:
    """One car's state after the most recently completed lap."""
    driver: str
    position: int
    gap_to_leader: float    # seconds; 0.0 for the leader
    compound: str           # current compound (post-pit if pitted this lap)
    tyre_age: float         # effective laps on current set (post-lap)
    total_time: float       # cumulative race time in seconds
    pace_setting: PaceSetting
    pitted_this_lap: bool
    current_lap_time: float = 0.0  # last computed lap time; lets UI estimate track position


@dataclass
class RaceState:
    """Snapshot returned by advance()."""
    lap: int                        # last completed lap
    total_laps: int
    cars: list[CarState]            # sorted P1 → last
    events: list[SessionEvent]      # all events since the previous advance() call
    finished: bool
    sc_active: bool = False         # True while safety car is deployed on this lap


@dataclass
class PitAction:
    """Instruct the player's car to pit on the very next lap."""
    compound: str


@dataclass
class PlayerAction:
    """Combined player decision applied before the next advance() call."""
    pit: Optional[PitAction] = None
    pace: PaceSetting = PaceSetting.NEUTRAL


# --------------------------------------------------------------------------- #
# Private per-car mutable state                                                 #
# --------------------------------------------------------------------------- #

@dataclass
class _Car:
    driver: str
    compound: str
    effective_tyre_age: float       # float; accumulates via wear_multiplier
    total_time: float
    pace_setting: PaceSetting
    planned_pits: dict[int, str]    # lap → new compound (AI only; empty for player)
    is_player: bool
    last_lap_time: float = 0.0      # most recent computed lap time


# --------------------------------------------------------------------------- #
# RaceSession                                                                   #
# --------------------------------------------------------------------------- #

class RaceSession:
    """Race played one decision at a time.

    Usage::

        session = RaceSession(cars, total_laps=70, player_id="VER",
                              cfg=SimConfig(), seed=42)
        while True:
            state = session.advance()
            if state.finished:
                break
            # inspect state.events, then optionally:
            session.decide(PlayerAction(pit=PitAction("HARD")))
    """

    _CLIFF_WARNING_LAPS: int = 3    # warn this many effective laps before the cliff

    def __init__(
        self,
        cars: list[CarStrategy],
        total_laps: int,
        player_id: str,
        cfg: SimConfig,
        seed: int,
        ai_profiles: dict[str, AiProfile] | None = None,
    ) -> None:
        if not any(c.driver == player_id for c in cars):
            raise ValueError(f"player_id {player_id!r} not found in cars list")

        self._total_laps = total_laps
        self._player_id = player_id
        self._cfg = cfg
        self._driver_order: list[str] = [c.driver for c in cars]
        self._base_paces: dict[str, float] = {c.driver: c.base_pace for c in cars}

        self._rng = random.Random(seed)
        # SC schedule is pre-generated from the seed so races are reproducible.
        self._sc_schedule: list[SafetyCarWindow] = generate_safety_car_schedule(
            total_laps, cfg, self._rng
        )

        self._cars: dict[str, _Car] = {
            c.driver: _Car(
                driver=c.driver,
                compound=c.start_compound,
                effective_tyre_age=0.0,
                total_time=0.0,
                pace_setting=PaceSetting.NEUTRAL,
                planned_pits={} if c.driver == player_id
                              else {s.lap: s.compound for s in c.pit_stops},
                is_player=(c.driver == player_id),
            )
            for c in cars
        }

        self._ai_profiles: dict[str, AiProfile] = ai_profiles or {}

        self._current_lap: int = 0
        self._pending_pit: str | None = None    # queued compound for player
        self._finished: bool = False
        self._cliff_warned: bool = False         # resets after each player pit
        self._last_pitted: dict[str, bool] = {d: False for d in self._driver_order}

    # ---------------------------------------------------------------------- #
    # Public API                                                               #
    # ---------------------------------------------------------------------- #

    def advance(self) -> RaceState:
        """Run laps until the next decision point or the race ends.

        Decision points:
        - a rival pits
        - the player's tyres are within ``_CLIFF_WARNING_LAPS`` of the cliff
        - the last lap completes (RACE_FINISH)

        The player's future pit stops are not precomputed; only laps actually
        advanced here are simulated.

        Returns the current race state with all events since the last call.
        Calling advance() on an already-finished session returns the terminal
        state unchanged.
        """
        if self._finished:
            return self._build_state(self._current_lap, [])

        accumulated: list[SessionEvent] = []

        while self._current_lap < self._total_laps:
            lap = self._current_lap + 1
            lap_events = self._step_lap(lap)
            self._current_lap = lap
            accumulated.extend(lap_events)

            if self._finished or accumulated:
                return self._build_state(lap, accumulated)

        # Guard: RACE_FINISH always fires on the last lap, so this is unreachable.
        return self._build_state(self._current_lap, accumulated)  # pragma: no cover

    def decide(self, action: PlayerAction) -> None:
        """Queue the player's decision; applied on the next advance() call.

        ``action.pit``:  if set, the player pits on the very next lap.
        ``action.pace``: sets the pace dial from the next lap onwards.
        """
        if self._finished:
            raise RuntimeError("Race is already finished; no decisions remaining.")

        self._cars[self._player_id].pace_setting = action.pace
        if action.pit is not None:
            self._pending_pit = action.pit.compound

    # ---------------------------------------------------------------------- #
    # Internal helpers                                                         #
    # ---------------------------------------------------------------------- #

    def _step_lap(self, lap: int) -> list[SessionEvent]:
        """Advance all cars by one lap; return events generated this lap."""
        sc_now = is_sc_active(lap, self._sc_schedule)

        # Under SC, pit loss is heavily discounted — use a modified config for this lap only.
        effective_cfg = (
            dataclasses.replace(self._cfg, pit_loss=self._cfg.pit_loss * self._cfg.sc_pit_loss_factor)
            if sc_now else self._cfg
        )

        # Phase 1: compute AI decisions based on state BEFORE this lap.
        ai_decisions: dict[str, AiDecision] = {}
        if self._ai_profiles:
            views = self._build_ai_views(lap)
            view_by = {v.driver: v for v in views}
            for driver in self._driver_order:
                s = self._cars[driver]
                if not s.is_player and driver in self._ai_profiles:
                    ai_decisions[driver] = ai_action(
                        me=view_by[driver],
                        field=views,
                        lap=lap,
                        total_laps=self._total_laps,
                        planned_pits=s.planned_pits,
                        cfg=self._cfg,
                        profile=self._ai_profiles[driver],
                    )

        # Phase 2: resolve player pit.
        player_pits = self._pending_pit is not None
        player_compound = self._pending_pit
        self._pending_pit = None

        # Phase 3: run each car for this lap.
        for driver in self._driver_order:
            s = self._cars[driver]

            if s.is_player:
                is_pit = player_pits
                new_compound: str | None = player_compound
            elif driver in ai_decisions:
                decision = ai_decisions[driver]
                s.pace_setting = decision.pace  # applied this lap
                is_pit = decision.pit_compound is not None
                new_compound = decision.pit_compound
                if is_pit:
                    # Consume the nearest future planned stop so window doesn't re-fire.
                    future = [l for l in s.planned_pits if l >= lap]
                    if future:
                        del s.planned_pits[min(future)]
            else:
                is_pit = lap in s.planned_pits
                new_compound = s.planned_pits.get(lap)

            lt = _lap_time(
                car_pace=self._base_paces[driver],
                tyre_age=s.effective_tyre_age,
                compound=s.compound,
                lap_number=lap,
                is_pit_lap=is_pit,
                cfg=effective_cfg,
                pace_setting=s.pace_setting,
            )
            s.total_time += lt
            s.last_lap_time = lt
            self._last_pitted[driver] = is_pit

            if is_pit:
                assert new_compound is not None
                s.compound = new_compound
                s.effective_tyre_age = 0.0
                if s.is_player:
                    self._cliff_warned = False
            else:
                s.effective_tyre_age += self._cfg.wear_multiplier(s.pace_setting)

        # Phase 4: compress field under SC (applied after all lap times are settled).
        if sc_now:
            self._compress_field()

        events: list[SessionEvent] = []

        # Safety car events — both are decision points.
        for window in self._sc_schedule:
            if window.start_lap == lap:
                events.append(SessionEvent(
                    lap=lap, kind=EventKind.SAFETY_CAR_DEPLOYED, driver="SC",
                ))
            elif window.end_lap == lap:
                events.append(SessionEvent(
                    lap=lap, kind=EventKind.SAFETY_CAR_CLEARED, driver="SC",
                ))

        # Rival pit events
        for driver in self._driver_order:
            if driver != self._player_id and self._last_pitted[driver]:
                events.append(SessionEvent(lap=lap, kind=EventKind.RIVAL_PITTED, driver=driver))

        # Tyre cliff warning (fires once per tyre set, resets after player pits)
        player = self._cars[self._player_id]
        if not self._cliff_warned:
            cliff = self._cfg.cliff_lap(player.compound)
            laps_to_cliff = cliff - player.effective_tyre_age
            if 0 < laps_to_cliff <= self._CLIFF_WARNING_LAPS:
                events.append(SessionEvent(
                    lap=lap,
                    kind=EventKind.TYRE_CLIFF_WARNING,
                    driver=self._player_id,
                ))
                self._cliff_warned = True

        # Race finish
        if lap == self._total_laps:
            self._finished = True
            winner = min(
                self._driver_order,
                key=lambda d: (self._cars[d].total_time, self._driver_order.index(d)),
            )
            events.append(SessionEvent(lap=lap, kind=EventKind.RACE_FINISH, driver=winner))

        return events

    def _build_ai_views(self, lap: int) -> list[AiCarView]:
        """Build a fog-of-war snapshot from the current (post-previous-lap) state."""
        sc_now = is_sc_active(lap, self._sc_schedule)
        order = self._sorted_drivers()
        leader_time = self._cars[order[0]].total_time
        return [
            AiCarView(
                driver=d,
                position=pos,
                gap_to_leader=self._cars[d].total_time - leader_time,
                compound=self._cars[d].compound,
                tyre_age=self._cars[d].effective_tyre_age,
                pace_setting=self._cars[d].pace_setting,
                pitted_last_lap=self._last_pitted.get(d, False),
                sc_active=sc_now,
            )
            for pos, d in enumerate(order, 1)
        ]

    def _compress_field(self) -> None:
        """Compress inter-car gaps each lap the safety car is deployed.

        Each SC lap, following cars' gap to the leader shrinks by
        cfg.sc_gap_compress_factor (multiplicative).  The leader is
        unaffected; a 0-gap car stays at 0.
        """
        leader_time = min(c.total_time for c in self._cars.values())
        for car in self._cars.values():
            gap = car.total_time - leader_time
            car.total_time -= gap * self._cfg.sc_gap_compress_factor

    def _sorted_drivers(self) -> list[str]:
        return sorted(
            self._driver_order,
            key=lambda d: (self._cars[d].total_time, self._driver_order.index(d)),
        )

    def _build_state(self, lap: int, events: list[SessionEvent]) -> RaceState:
        order = self._sorted_drivers()
        leader_time = self._cars[order[0]].total_time
        car_states = [
            CarState(
                driver=d,
                position=pos,
                gap_to_leader=self._cars[d].total_time - leader_time,
                compound=self._cars[d].compound,
                tyre_age=self._cars[d].effective_tyre_age,
                total_time=self._cars[d].total_time,
                pace_setting=self._cars[d].pace_setting,
                pitted_this_lap=self._last_pitted.get(d, False),
                current_lap_time=self._cars[d].last_lap_time,
            )
            for pos, d in enumerate(order, 1)
        ]
        return RaceState(
            lap=lap,
            total_laps=self._total_laps,
            cars=car_states,
            events=events,
            finished=self._finished,
            sc_active=is_sc_active(lap, self._sc_schedule),
        )
