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

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .components import lap_time as _lap_time
from .config import PaceSetting, SimConfig
from .strategy import CarStrategy


# --------------------------------------------------------------------------- #
# Public types                                                                  #
# --------------------------------------------------------------------------- #

class EventKind(Enum):
    """Events that trigger a decision-point pause in advance()."""
    RIVAL_PITTED = "rival_pitted"
    TYRE_CLIFF_WARNING = "tyre_cliff_warning"
    RACE_FINISH = "race_finish"


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


@dataclass
class RaceState:
    """Snapshot returned by advance()."""
    lap: int                        # last completed lap
    total_laps: int
    cars: list[CarState]            # sorted P1 → last
    events: list[SessionEvent]      # all events since the previous advance() call
    finished: bool


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
    ) -> None:
        if not any(c.driver == player_id for c in cars):
            raise ValueError(f"player_id {player_id!r} not found in cars list")

        self._total_laps = total_laps
        self._player_id = player_id
        self._cfg = cfg
        self._driver_order: list[str] = [c.driver for c in cars]
        self._base_paces: dict[str, float] = {c.driver: c.base_pace for c in cars}

        # Seed is reserved for future stochastic elements (safety cars, etc.)
        self._rng = random.Random(seed)

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
        player_pits = self._pending_pit is not None
        player_compound = self._pending_pit
        self._pending_pit = None

        for driver in self._driver_order:
            s = self._cars[driver]

            if s.is_player:
                is_pit = player_pits
                new_compound: str | None = player_compound
            else:
                is_pit = lap in s.planned_pits
                new_compound = s.planned_pits.get(lap)

            lt = _lap_time(
                car_pace=self._base_paces[driver],
                tyre_age=s.effective_tyre_age,
                compound=s.compound,
                lap_number=lap,
                is_pit_lap=is_pit,
                cfg=self._cfg,
                pace_setting=s.pace_setting,
            )
            s.total_time += lt
            self._last_pitted[driver] = is_pit

            if is_pit:
                assert new_compound is not None
                s.compound = new_compound
                s.effective_tyre_age = 0.0
                if s.is_player:
                    self._cliff_warned = False
            else:
                s.effective_tyre_age += self._cfg.wear_multiplier(s.pace_setting)

        events: list[SessionEvent] = []

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
            )
            for pos, d in enumerate(order, 1)
        ]
        return RaceState(
            lap=lap,
            total_laps=self._total_laps,
            cars=car_states,
            events=events,
            finished=self._finished,
        )
