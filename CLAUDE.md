# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**PitWall** — an interactive Formula 1 race strategy simulator. The user picks a real Grand Prix (data from the FastF1 library), edits a pit-stop strategy, and the engine re-simulates the race lap-by-lap modelling tyre degradation, fuel burn, pit-lane time loss, and the undercut/overcut. Move a pit stop and watch the field reorder with a delta vs. the baseline strategy.

Portfolio project — judged on code quality, a correct simulation, and a polished live front-end.

## Architecture

Three decoupled layers, built in this order:

| Layer | Location | Status |
|---|---|---|
| Simulation engine + data ingestion | `engine/` | skeleton only |
| FastAPI HTTP wrapper | `api/` (inside or alongside `engine/`) | not yet created |
| React + TypeScript + Vite front-end | `web/` | placeholder only |

**The one rule: simulation logic lives only in `engine/`.** The API and front-end must never reimplement or duplicate it. This is the project's main architectural talking point.

Data flow: FastF1 → cached to local SQLite once → everything else reads SQLite. **Never call FastF1 live from the API or in tests.**

## Commands

All Python commands run from `engine/` with the venv active.

```bash
# Activate venv (Windows)
engine\.venv\Scripts\activate

# Activate venv (Unix/macOS)
source engine/.venv/bin/activate

# Install / update deps
pip install -e ".[dev]"

# Tests
pytest                          # all tests
pytest -k undercut              # filter by name
pytest --cov=engine             # with coverage

# Data ingestion (once engine.ingest exists)
python -m engine.ingest --year 2024 --gp "Hungary"

# API (once api/ exists)
uvicorn api.main:app --reload

# Web (from web/)
npm run dev
npm run build
npm run lint
```

Run `pytest` after every engine change before moving on.

## Simulation model

Each car's lap time per lap = sum of five independently-tested components:

1. **Base pace** — per-car constant (s/lap) from real race pace.
2. **Tyre degradation** — linear loss growing with tyre age, per compound.
3. **Compound offset** — fixed pace delta between compounds (softer = faster fresh).
4. **Fuel burn** — lap time improves linearly as fuel burns off.
5. **Pit-lane loss** — one-off penalty on the lap a stop is taken.

The undercut/overcut **must emerge** from these five components — never hard-code it. There is a test that proves an early stop can leapfrog a rival; keep it passing.

All tunable parameters live in a config dataclass. Realistic defaults:

| Parameter | Default |
|---|---|
| Soft degradation | ~0.10–0.15 s/lap |
| Medium degradation | ~0.06–0.10 s/lap |
| Hard degradation | ~0.03–0.06 s/lap |
| Compound gap (soft→hard) | ~0.6–1.0 s/lap |
| Pit-lane loss (total) | ~18–25 s, circuit-dependent |
| Fuel effect | ~0.03–0.06 s/lap improvement per lap |

`engine/CALIBRATION.md` (to be created) records simulated vs. real finishing order and why they diverge. A regression test locks in achieved accuracy — don't let it silently regress.

## Conventions

- Engine: pure functions, no I/O, no side effects — data in, results out.
- Python: full type hints; Pydantic models at the API boundary.
- Front-end: no `any`; one typed API-client module that mirrors the Pydantic shapes.
- Tests: small fixtures only, no network calls, no live FastF1.
- UI colours: soft = red, medium = yellow, hard = white. Dark pit-wall aesthetic.

## Do not

- Put simulation logic outside `engine/`.
- Call FastF1 from the API or from tests.
- Hard-code the undercut/overcut.
- Add scope beyond the five model components for v1 — Monte Carlo, safety cars, auto-calibration, and optimal-strategy solver are explicit stretch goals.
- commit into my github repository