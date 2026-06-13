"""PitWall simulation engine — public API.

Typical usage::

    from engine.sim import SimConfig, CarStrategy, PitStop, simulate

    cfg = SimConfig(pit_loss=21.5)
    result = simulate(
        [
            CarStrategy("VER", base_pace=89.8, start_compound="MEDIUM",
                        pit_stops=[PitStop(lap=33, compound="HARD")]),
            CarStrategy("NOR", base_pace=90.1, start_compound="MEDIUM",
                        pit_stops=[PitStop(lap=30, compound="HARD")]),
        ],
        total_laps=70,
        cfg=cfg,
    )
    print(result.finishing_order)
"""

from .ai import AiProfile
from .config import SimConfig
from .runner import LapSnapshot, RaceResult, simulate
from .session import (
    CarState,
    EventKind,
    PitAction,
    PlayerAction,
    RaceSession,
    RaceState,
    SessionEvent,
)
from .strategy import CarStrategy, PitStop

__all__ = [
    "SimConfig",
    "CarStrategy",
    "PitStop",
    "LapSnapshot",
    "RaceResult",
    "simulate",
    "RaceSession",
    "RaceState",
    "CarState",
    "SessionEvent",
    "EventKind",
    "PitAction",
    "PlayerAction",
    "AiProfile",
]
