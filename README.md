# PitWall — F1 Race Strategy Simulator

> Pick a Grand Prix. Edit a pit-stop strategy — or race it yourself in real time.

**Live demo:** <!-- add your Vercel URL --> · **API:** https://pitwall-rugf.onrender.com/docs
<sub>(free-tier API — the first request may take ~30s to wake the server)</sub>

<!-- Drop a screen-recording here once deployed (e.g. Loom → GIF via gifski) -->
![Demo placeholder](docs/demo.gif)

PitWall has two modes:

**Strategy editor** — pick a real Grand Prix, drag pit-stop markers on the stint timeline, and the engine re-simulates the entire field in under a second. A live delta table shows exactly who gained a position and by how many seconds.

**Race Engineer Mode (live)** — the headline feature. Pick a driver (their real grid slot doubles as your difficulty), then race it live against a **reactive AI field** that covers undercuts and reacts to the chaos under the same fog of war you have. The race opens with a lights-out start and plays out lap-by-lap on a broadcast-style screen: a team-colour timing tower, a sector-coloured live track map, a five-step **push/conserve** pace dial, and team radio. You call the pit stops in the moment — and the model pauses the instant a **safety car** is deployed or your **tyres hit the cliff**, the two moments that actually demand a decision. Boxing triggers a broadcast pit-stop HUD (stationary clock, four corners lighting up, compound swap). A post-race debrief generates a narrative verdict from your actual decisions. The same model runs under the hood; your choices feed into it in real time.

---

## The problem

F1 strategy is invisible to most viewers. You see a driver pit on lap 27 and wonder: was that too early? Would lap 32 have triggered a faster undercut? The timing data exists — FastF1 exposes every lap time from every session — but there was no tool that let you replay the counterfactual in real time and see whether it worked for the whole field, not just your driver.

PitWall is that tool. Load a real race, edit one driver's pit-stop sequence by dragging the lap markers, hit **Compare**, and the five-component model re-runs the race and shows you the position and time delta for every car.

---

## The simulation model

Each car's lap time per lap is the sum of **five independent, separately-tested components**:

| Component | Effect |
|---|---|
| **Base pace** | Per-car constant (s/lap), back-estimated from real timing data |
| **Tyre degradation** | Linear penalty growing with tyre age; rate differs by compound |
| **Compound offset** | Fixed speed delta between compounds (SOFT fastest fresh, HARD slowest) |
| **Fuel burn** | Car gets faster as fuel burns off, ~0.04 s/lap improvement |
| **Pit-lane loss** | One-off time penalty (~22 s) applied on the lap a stop is taken |

### Two more dynamics layered on top

The base five components are extended by two non-linear effects that make live racing tense:

- **Tyre cliff** — degradation is linear up to a per-compound age threshold, then accelerates sharply. Staying out one lap too long becomes a real gamble, not a smooth penalty. (Soft cliffs at ~16 laps, medium ~28, hard ~42; degradation multiplies by ~1.8–2.5× beyond it.)
- **Push / conserve dial** — a five-step pace input (Race Mode) trading lap time against tyre wear in opposite directions. Pushing is faster now but brings the cliff forward; conserving extends the stint. There is no free lunch in either direction.

| Pace setting | Lap-time delta | Tyre-wear rate |
|---|---|---|
| Push hard | −0.40 s/lap | 1.8× |
| Push | −0.20 s/lap | 1.3× |
| Neutral | 0 | 1.0× |
| Conserve | +0.30 s/lap | 0.7× |
| Conserve hard | +0.60 s/lap | 0.5× |

**Tuned defaults** (calibrated against the 2024 Hungarian Grand Prix):

| Parameter | Value |
|---|---|
| Soft degradation | 0.130 s/lap |
| Medium degradation | 0.075 s/lap |
| Hard degradation | 0.045 s/lap |
| Soft → Medium compound gap | 0.40 s/lap |
| Soft → Hard compound gap | 0.80 s/lap |
| Pit-lane loss | 22 s |
| Fuel effect | 0.040 s/lap |
| Tyre cliff (soft / med / hard) | 16 / 28 / 42 laps |
| Cliff multiplier (soft / med / hard) | 2.5× / 2.0× / 1.8× |

### The undercut emerges — it is never hard-coded

An *undercut* works when a driver pits before their rival, gains the tyre-speed advantage, and exits the pits ahead. In PitWall this happens because fresh tyres carry zero degradation and a compound-speed benefit. If the per-lap time savings over the subsequent laps exceed the fixed pit-stop time cost, the car that pitted first comes out ahead.

This is a falsifiable prediction from the model — not a special case. There is a regression test that proves it: move one car's pit stop five laps earlier than its rival; assert it finishes P1. If someone breaks the five-component model, the test fails.

---

## Architecture

Three decoupled layers. **Simulation logic lives only in `engine/`** — the API and front-end never reimplement it.

```
pitwall/
├── engine/          Python — pure simulation + data ingestion
│   ├── engine/sim/  lap model + cliff/pace, runner, interactive session, reactive AI, safety-car events
│   ├── engine/db.py SQLite helpers
│   ├── engine/ingest.py  FastF1 → SQLite (runs once)
│   └── api/         FastAPI HTTP wrapper, Pydantic schemas
└── web/             React + TypeScript + Vite front-end
    └── src/api/     typed fetch client — mirrors Pydantic schemas 1:1, no simulation logic
```

### Data flow

**Strategy editor:**
```
FastF1 (network, once)
    │  engine/ingest.py
    ▼
SQLite cache  ←→  engine/db.py
    │  API reads cache only — no live FastF1 calls at request time
    ▼
FastAPI  ·  GET /races  ·  GET /races/{id}/baseline  ·  POST /compare
    │  fetch() wrappers in src/api/client.ts
    ▼
React UI — StintTimeline, GapChart, ComparePanel
```

**Race Engineer Mode:**
```
Same SQLite cache
    │
    ▼
FastAPI  ·  POST /race/start  ·  POST /race/{id}/step  ·  POST /race/{id}/advance
    │  lap-by-lap interactive session, pace + pit decisions fed in each request
    ▼
React UI — RaceEngineerScreen (timing tower, track map, pit HUD, team radio)
    │
    ▼
VerdictScreen — narrative debrief generated from recorded events + decisions
```

The API is a thin shell. It validates input with Pydantic, reads race metadata from SQLite, calls `simulate()`, and serialises the output. It contains zero lap-time logic.

### Why this split matters

- The **engine** is independently testable with pure unit tests. No mocks needed; the functions have no side effects.
- The **API** can be swapped (FastAPI → Django, REST → GraphQL) without touching the model.
- The **front-end** can be rebuilt without touching the API or model.
- The narrative debrief is generated from race data, not hard-coded — it reads the same `SessionEventSchema` events the radio system uses.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/races` | List all ingested races |
| `GET` | `/races/{id}/baseline` | Reconstruct baseline strategies from real pit data + simulate |
| `GET` | `/races/{id}/track` | Normalised circuit outline (from FastF1 position telemetry) for the live track map |
| `POST` | `/simulate` | Run a fully custom strategy set |
| `POST` | `/compare` | Run strategy A vs B; return both results + per-driver position/time delta |
| `POST` | `/race/start` | Start an interactive race session; returns session ID + grid state |
| `POST` | `/race/{id}/step` | Advance exactly one lap with pace + pit decision |
| `POST` | `/race/{id}/advance` | Advance to the next event (rival pit, safety car, tyre cliff) |

Full OpenAPI docs at `http://localhost:8000/docs` when the server is running.

---

## Validation

Calibrated against the **2024 Hungarian Grand Prix** (70 laps, 20 cars).

**Method:**
1. Ingest real lap times, pit-stop laps, and compounds from FastF1.
2. Back-estimate each driver's base pace by stripping the modelled compound, degradation, and fuel effects from each valid lap time and averaging the residual.
3. Hand-tune degradation rates and pit-loss constants until the simulated finishing order matches the real order for the majority of drivers.
4. Lock the calibration with a regression test — if the finishing order accuracy drops below the recorded threshold, CI fails.

**Known divergences from reality:**

| Gap | Root cause |
|---|---|
| Safety-car laps | The calibration baseline is run green-flag for a deterministic comparison. Safety cars *are* modelled in Race Mode as seeded random events, but are excluded from the accuracy baseline since their real timing is race-specific |
| Traffic / DRS | Lap times modelled in isolation; no car-following or slipstream |
| Driver error / reliability | Absent by design |

These are explicit non-goals for v1. The model produces correct *relative* ordering and credible strategic deltas, which is the meaningful output for a what-if tool. (The non-linear tyre cliff, originally a known gap, is now part of the model.)

---

## Trade-offs

| Decision | What was rejected | Reason |
|---|---|---|
| Linear degradation + a discrete cliff | Fully quadratic wear curve | Linear is trivial to calibrate per compound; a per-compound cliff threshold adds the end-of-stint drama without a hard-to-tune curve |
| SQLite for race cache | PostgreSQL, Redis | Zero infrastructure, single file, trivially portable |
| Full 20-car field always simulated | Simulate only the two cars being compared | Position deltas are only meaningful when the whole field moves |
| Seeded random safety cars (Race Mode) | Replaying each race's real SC laps | Real SC timing is race-specific; a seeded probabilistic model keeps every race different and reproducible for tests, and is excluded from the deterministic calibration baseline |
| Rule-based AI rivals | LLM-driven opponents | Heuristics (pit at the cliff, cover an undercut, take the cheap SC stop) are explainable, tunable by difficulty, and deterministic to test |
| Recharts for charting | D3, Observable Plot | Typed, React-native, zero config |
| Drag-and-drop pit editor | Form-only interface | The lap axis makes pit strategy tangible; dragging a marker and watching the stint bars redraw is the core UX |
| Narrative debrief from events | LLM-generated copy | The event log already contains every decision; deterministic generation is faster, cheaper, and always accurate |

---

## Running locally

### 1 · Ingest a race (once)

```bash
cd engine
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m engine.ingest --year 2024 --gp "Hungary"
```

### 2 · Start the API

```bash
# From engine/, with venv active
uvicorn api.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs
```

### 3 · Start the front-end

```bash
cd web
npm install
npm run dev
# → http://localhost:5173
```

### Tests

```bash
cd engine
pytest                  # full suite
pytest -k undercut      # undercut emergence test only
pytest --cov=engine     # with line coverage
```

---

## Deployment

**Front-end → Vercel**

```bash
cd web
vercel deploy --prod
# Set environment variable in Vercel dashboard:
#   VITE_API_URL = https://<your-render-service>.onrender.com
```

**API → Render**

Deploy `engine/` as a Python web service. Set:
```
CORS_ORIGINS=https://<your-vercel-app>.vercel.app
PITWALL_DB=/path/to/pitwall.db
```

The SQLite file must be present on the Render instance (upload it or build it during the deploy step with `python -m engine.ingest --year 2024 --gp Hungary`).

---

## Project layout

```
engine/
  engine/
    sim/
      components.py   five lap-time functions + non-linear tyre cliff
      runner.py       simulate() — the single public entry point
      session.py      RaceSession — interactive lap-by-lap race (step/advance, events, grid)
      ai.py           rule-based rival strategy (cliff pit, undercut cover, cheap SC stop)
      events.py       seeded random safety-car deployment
      strategy.py     CarStrategy, PitStop dataclasses
      config.py       SimConfig — tuned defaults, cliff thresholds, pace-dial values
    db.py             SQLite read/write helpers
    ingest.py         FastF1 → SQLite pipeline
    calibration.py    build_baseline_strategies(), TUNED_CFG
  api/
    main.py           FastAPI app, CORS, route handlers
    models.py         Pydantic request/response schemas
  tests/
    test_components.py
    test_runner.py
    test_undercut.py
    test_db.py
    test_calibration.py
web/
  src/
    api/
      types.ts        TypeScript interfaces mirroring Pydantic schemas exactly
      client.ts       typed fetch wrappers
    components/
      RaceEngineerScreen.tsx  live race mode — timing tower, track map, pit HUD,
                              team radio, VerdictScreen with narrative debrief
      StintTimeline.tsx       horizontal stint bars + drag-and-drop pit editor
      GapChart.tsx            Recharts gap-to-leader line chart
      ComparePanel.tsx        delta table + side-by-side gap charts
      StrategyEditor.tsx      lap-number input + compound dropdown per stop
      RacePicker.tsx          race selection dropdown
      Explainer.tsx           how-it-works panel shown before a race is loaded
    App.tsx           state orchestration, compare flow, layout
```
