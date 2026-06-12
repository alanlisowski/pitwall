# PitWall — F1 Race Strategy Simulator

> Pick a Grand Prix. Edit a pit-stop strategy. Watch the field reorder.

<!-- Replace with a real screen-recording once the app is deployed -->
![Demo placeholder](docs/demo.gif)

PitWall lets you replay any Formula 1 race and ask *what if?* Move a pit stop five laps earlier, swap to a different compound, and the engine re-simulates the entire field in under a second. A live delta table shows exactly who gained a position and by how many seconds.

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

### The undercut emerges — it is never hard-coded

An *undercut* works when a driver pits before their rival, gains the tyre-speed advantage, and exits the pits ahead. In PitWall this happens because fresh tyres carry zero degradation and a compound-speed benefit. If the per-lap time savings over the subsequent laps exceed the fixed pit-stop time cost, the car that pitted first comes out ahead.

This is a falsifiable prediction from the model — not a special case. There is a regression test that proves it: move one car's pit stop five laps earlier than its rival; assert it finishes P1. If someone breaks the five-component model, the test fails.

---

## Architecture

Three decoupled layers. **Simulation logic lives only in `engine/`** — the API and front-end never reimplement it.

```
pitwall/
├── engine/          Python — pure simulation + data ingestion
│   ├── engine/sim/  lap model (five components, runner, config, strategy types)
│   ├── engine/db.py SQLite helpers
│   ├── engine/ingest.py  FastF1 → SQLite (runs once)
│   └── api/         FastAPI HTTP wrapper, Pydantic schemas, three endpoints
└── web/             React + TypeScript + Vite front-end
    └── src/api/     typed fetch client — mirrors Pydantic schemas 1:1, no simulation logic
```

### Data flow

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

The API is a thin shell. It validates input with Pydantic, reads race metadata from SQLite, calls `simulate()`, and serialises the output. It contains zero lap-time logic. This means the model can be tested by calling `simulate(strategies, laps)` directly — no HTTP, no database, no fixtures.

### Why this split matters

The single-responsibility boundary is what makes the project interesting as a portfolio piece:

- The **engine** is independently testable with pure unit tests. No mocks needed; the functions have no side effects.
- The **API** can be swapped (FastAPI → Django, REST → GraphQL) without touching the model.
- The **front-end** can be rebuilt (React → Svelte, chart library swap) without touching the API or model.
- A future mobile app or CLI could call `simulate()` directly or hit the same HTTP endpoints.

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/races` | List all ingested races |
| `GET` | `/races/{id}/baseline` | Reconstruct baseline strategies from real pit data + simulate |
| `POST` | `/simulate` | Run a fully custom strategy set |
| `POST` | `/compare` | Run strategy A vs B; return both results + per-driver position/time delta |

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
| Safety-car laps | Not modelled; engine assumes green-flag racing throughout |
| Non-linear tyre cliff | Model uses linear deg; real compounds often drop off sharply in the final laps of a stint |
| Traffic / DRS | Lap times modelled in isolation; no car-following or slipstream |
| Driver error / reliability | Absent by design |

These are explicit non-goals for v1. The model produces correct *relative* ordering and credible strategic deltas, which is the meaningful output for a what-if tool.

---

## Trade-offs

| Decision | What was rejected | Reason |
|---|---|---|
| Linear tyre degradation | Quadratic or cliff model | Simpler to calibrate per compound; accuracy is sufficient for strategic insight |
| SQLite for race cache | PostgreSQL, Redis | Zero infrastructure, single file, trivially portable — right for a portfolio project |
| Full 20-car field always simulated | Simulate only the two cars being compared | Position deltas are only meaningful when the whole field moves — an undercut from P3 to P2 requires P2's car to also be running |
| No safety-car model | Probabilistic VSC | SC timing is race-specific and effectively random; adding a fixed SC would give false precision |
| Recharts for charting | D3, Observable Plot | Typed, React-native, zero config — right tool for a 20-line × 70-lap dataset |
| Drag-and-drop pit editor | Form-only interface | The lap axis makes pit strategy tangible; dragging a marker and watching the stint bars redraw is the core UX |

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

FastF1 caches the downloaded session to disk; subsequent runs are instant.

### 2 · Start the API

```bash
# From engine/, with venv active
uvicorn api.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs   (Swagger UI)
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
pytest                          # full suite
pytest -k undercut              # undercut emergence test only
pytest --cov=engine             # with line coverage
```

---

## Project layout

```
engine/
  engine/
    sim/
      components.py   five independent lap-time functions
      runner.py       simulate() — the single public entry point
      strategy.py     CarStrategy, PitStop dataclasses
      config.py       SimConfig with tuned defaults
    db.py             SQLite read/write helpers
    ingest.py         FastF1 → SQLite pipeline
    calibration.py    build_baseline_strategies(), TUNED_CFG
  api/
    main.py           FastAPI app, CORS, three route handlers
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
      client.ts       typed fetch wrappers: fetchRaces, fetchBaseline, compare
    components/
      StintTimeline.tsx    horizontal stint bars + drag-and-drop pit editor
      GapChart.tsx         Recharts gap-to-leader line chart
      ComparePanel.tsx     delta table + side-by-side gap charts
      StrategyEditor.tsx   lap-number input + compound dropdown per stop
      RacePicker.tsx       race selection dropdown
      Explainer.tsx        how-it-works panel shown before a race is loaded
    App.tsx           state orchestration, compare flow, layout
```
