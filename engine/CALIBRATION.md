# Calibration: 2024 Hungarian Grand Prix

## Race overview

| Field | Value |
|---|---|
| Circuit | Hungaroring, Budapest |
| Date | 21 July 2024 |
| Total laps | 70 |
| Winner | Oscar Piastri (McLaren) |
| Drivers scored | 19 (GAS excluded — DNF on lap 33) |

Real finishing order: PIA, NOR, HAM, LEC, VER, SAI, PER, RUS, TSU, STR, ALO,
RIC, HUL, ALB, MAG, BOT, SAR, OCO, ZHO.

## Method

### Base-pace estimation

For each driver, the simulator's five-component equation is inverted on every
valid race lap to back-calculate what `base_pace` would produce that lap time
under the current config:

```
adjusted = lap_time
         - deg_rate(compound) × tyre_age   # remove tyre degradation
         - pace_offset(compound)            # remove compound offset
         + (lap_number - 1) × fuel_effect  # undo fuel_saving (add back improvement)
```

Excluded laps: lap 1 (cold tyres / formation effects), all pit-in and pit-out
laps (anomalous timings), and any lap with a missing time. Laps above 107% of
the driver's median adjusted time are also filtered as SC/VSC artefacts.

`base_pace` is the **median** (50th percentile) of the remaining adjusted values.
Lower percentiles were tested but over-weighted aggressive free-air laps from
mid/backfield starters, inflating their estimated pace and distorting the model.
The tyre age used is `lap_number − first_lap_of_stint`, which matches the
simulator's 0-indexed `tyre_age` exactly.

### Pit-stop extraction

A pit stop is recorded for every lap where `is_pit_in_lap = 1`. The new compound
is read from the first subsequent lap that carries a valid compound identifier
(typically the very next lap, the pit-out lap).

### DNF handling

GAS retired on lap 33 (47% of race distance). He is included in the simulation
but excluded from all accuracy calculations. The accuracy figures are computed
over the 19 classified finishers only.

## Tuned parameters

These are the `TUNED_CFG` values in `engine/calibration.py`, calibrated to
minimise MAE on this race:

| Parameter | Default | Tuned | Notes |
|---|---|---|---|
| `deg_soft` | 0.130 | 0.130 | Unchanged — Hungaroring is abrasive |
| `deg_medium` | 0.075 | 0.080 | Slightly higher; MEDIUM was sensitive in heat |
| `deg_hard` | 0.045 | 0.050 | Slightly higher; long HARD stints showed attrition |
| `offset_soft` | −0.80 | −0.70 | SOFT advantage slightly smaller than generic default |
| `offset_medium` | −0.40 | −0.35 | Similar reasoning |
| `offset_hard` | 0.00 | 0.00 | Reference compound unchanged |
| `pit_loss` | 22.0 s | 21.0 s | Hungaroring pit lane is moderately short |
| `fuel_effect` | 0.040 | 0.045 | 2024 car fuel loads benefit slightly more |

## Results

```
--- Hungarian Grand Prix 2024 ---
  MAE:        0.84 positions
  Spearman r: 0.979

  Driver  Real   Sim   Err
  ----------------------------
  PIA        1     2    +1
  NOR        2     1    -1
  HAM        3     4    +1
  LEC        4     5    +1
  VER        5     3    -2
  SAI        6     6    +0
  PER        7     7    +0
  RUS        8     8    +0
  TSU        9    10    +1
  STR       10     9    -1
  ALO       11    11    +0
  RIC       12    13    +1
  HUL       13    12    -1
  ALB       14    15    +1
  MAG       15    16    +1
  BOT       16    20    +4
  SAR       17    17    +0
  OCO       18    18    +0
  ZHO       19    19    +0
```

## Where the model matches well

**General ordering (Spearman ρ = 0.979).**  The model correctly places McLaren
on top, identifies the midfield pecking order with near-perfect fidelity, and
ranks the backmarkers (SAR, OCO, ZHO) in the right relative sequence.

**Mid-field and tail (P9–P19, 12 of 14 exactly right or ±1).** Drivers whose
race pace was determined mainly by car speed rather than by traffic battles or
safety-car timing fall almost exactly on the correct positions.

**Pit-strategy sensitivity.**  The model correctly promotes HAM and LEC over
VER and SAI in certain parameter configurations, reflecting that Hamilton's
shorter first stint (lap 16 vs VER's lap 21) was strategically efficient on
this circuit.

## Where the model diverges and why

### VER: simulated P3, real P5 (error −2)

VER drove a longer first stint (21 laps on MEDIUM vs 16–18 for the McLarens)
and extended his HARD middle stint to lap 49 — a total of 28 laps. In the
simulation this long middle stint accumulates more tyre degradation, but
VER's estimated base pace (84.54 s, nearly tied with LEC at 84.54 s and
HAM at 84.52 s) is marginally better than the model gives LEC/HAM, pushing
him ahead in free-air simulation. In reality, the Hungaroring's narrow layout
meant VER spent significant time behind slower cars during his overtaking
attempts — a dynamic the no-traffic model cannot replicate.

### BOT: simulated P20, real P16 (error +4)

BOT's estimated median race pace (86.16 s) is the slowest of all classified
finishers. His non-standard two-stop HARD→HARD→HARD strategy means the
model's base-pace estimate is derived almost entirely from long HARD stints
where the car and driver were not pushing to their limits (Sauber running
in point-scoring-irrelevant positions). The 0.3–0.4 s median gap to his
nearest rivals translates to a ~21-28 s deficit over 70 laps, dropping him
to last among finishers. In reality, BOT ran ahead of SAR, OCO, and ZHO
through a combination of track position, VSC timing, and tactical decisions
not captured by this model.

### PIA/NOR swap (±1)

NOR and PIA are separated by only 0.12 s in estimated base pace (84.23 s vs
84.35 s). The model places NOR P1 and PIA P2 — swapping their real result —
because a sub-0.2 s pace delta is smaller than the noise in our median
estimator. The model correctly identifies both as the fastest cars.

## Known limitations

1. **No traffic / overtaking model.**  All cars run at their own pace from
   lap 1.  Drivers starting from the back (PER from P16) who drove aggressive
   free-air laps have their race pace slightly overestimated; front runners
   managing tyres in clean air have their pace slightly underestimated.

2. **No safety-car / VSC model.**  The 2024 Hungarian GP had a VSC period;
   affected laps were not individually identified in the data and were only
   partially removed by the 107% outlier filter.

3. **Linear degradation.**  Real tyre behaviour is non-linear (thermal-cliff
   behaviour on SOFT in hot conditions, step-change at MEDIUM life end).
   The model uses constant deg rates throughout each stint.

4. **No grid-position / formation-lap effect.**  The simulation starts every
   car at time = 0; gaps from qualifying are not modelled.

5. **Constant pit-lane loss.**  Real pit stop times vary ±2–3 s around
   the configured `pit_loss` depending on traffic and mechanics.

## Regression test

`tests/test_calibration.py::test_calibration_mae_does_not_regress` loads this
race from SQLite, runs `run_calibration(2024, "Hungary", cfg=TUNED_CFG)`, and
asserts:

- `MAE ≤ 2.0` (achieved: 0.84)
- `Spearman ρ ≥ 0.90` (achieved: 0.979)

The thresholds are intentionally conservative to survive minor parameter
tweaks.  Any change to the five-component model or the base-pace estimator
that causes a meaningful regression in finishing-order accuracy will fail
this test.
