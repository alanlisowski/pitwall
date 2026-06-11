"""Manual sanity checks for the lap-time model.

Not a test file — just a script you RUN and eyeball.
Run it with:   python engine/tests/scratch.py
(or press the ▶ Run button in VS Code with this file open)

Each block changes ONE thing at a time so you can see what each
component does on its own.
"""
from engine.sim import SimConfig
from engine.sim.components import lap_time

cfg = SimConfig()


# ── 1. Base pace ────────────────────────────────────────────────
# Fresh HARD tyre, lap 1, no pit. Should be ~90 (= car_pace, since
# HARD offset is 0, tyre_age 0, and lap 1 has no fuel saving yet).
print("1. base pace:")
print("  ", round(lap_time(
    car_pace=90.0, tyre_age=0, compound="HARD",
    lap_number=1, is_pit_lap=False, cfg=cfg,
), 3))
print()


# ── 2. Tyre degradation ─────────────────────────────────────────
# Same lap, increasing tyre age. Numbers should RISE in a straight line.
print("2. degradation (SOFT) as tyre ages:")
for age in range(0, 21, 5):
    t = lap_time(
        car_pace=90.0, tyre_age=age, compound="SOFT",
        lap_number=1, is_pit_lap=False, cfg=cfg,
    )
    print("   age", age, "->", round(t, 3))
print()


# ── 3. Compound offset ──────────────────────────────────────────
# All fresh (age 0). SOFT should be fastest, HARD slowest.
print("3. compound offset (all fresh):")
for c in ["SOFT", "MEDIUM", "HARD"]:
    t = lap_time(
        car_pace=90.0, tyre_age=0, compound=c,
        lap_number=1, is_pit_lap=False, cfg=cfg,
    )
    print("  ", c, "->", round(t, 3))
print()


# ── 4. Fuel burn ────────────────────────────────────────────────
# Hold everything fixed, change only the lap number. Later = faster.
print("4. fuel burn (later laps faster):")
for lap in [1, 25, 50]:
    t = lap_time(
        car_pace=90.0, tyre_age=5, compound="HARD",
        lap_number=lap, is_pit_lap=False, cfg=cfg,
    )
    print("   lap", lap, "->", round(t, 3))
print()


# ── 5. Pit penalty ──────────────────────────────────────────────
# Same lap, with vs without a pit stop. Difference should be ~22s.
print("5. pit penalty:")
no_pit = lap_time(car_pace=90.0, tyre_age=0, compound="MEDIUM",
                  lap_number=20, is_pit_lap=False, cfg=cfg)
pit    = lap_time(car_pace=90.0, tyre_age=0, compound="MEDIUM",
                  lap_number=20, is_pit_lap=True, cfg=cfg)
print("   without pit:", round(no_pit, 3))
print("   with pit:   ", round(pit, 3))
print("   difference: ", round(pit - no_pit, 3), "(expect ~22)")
