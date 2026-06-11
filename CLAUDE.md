# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

**PitWall** — an interactive Formula 1 race strategy simulator. The user picks a real Grand Prix (data from the FastF1 library), edits a pit-stop strategy, and the engine re-simulates the race lap-by-lap, modelling tyre degradation, fuel burn, pit-lane time loss, and the undercut/overcut. The headline interaction: move a pit stop and watch the whole field re-order, with a delta vs. the baseline strategy.

It is a portfolio project — judged on code quality, a correct simulation, and a polished, demoable live front-end.

## Architecture (and the one rule that matters)

Three decoupled layers:

- `engine/` — **pure Python** simulation + FastF1 data ingestion. No web, no HTTP. Takes a race config + strategy in, returns a lap-by-lap result out.
- `api/` (or inside `engine/`) — **FastAPI** wrapper exposing the engine over HTTP. Contains NO simulation logic of its own.
- `web/` — **React + TypeScript + Vite** front-end. Talks to the API only.

**THE RULE: simulation logic lives only in `engine/`.** The API and front-end must never reimplement or duplicate it. This separation keeps the engine unit-testable in isolation and is the project's main architectural talking point. Do not break it.

Data flow: FastF1 → cached to local SQLite once → everything else reads from SQLite. **Never call FastF1 live from the API or in tests.**

## Tech stack

- Python 3.11+, NumPy, pandas, FastF1, FastAPI, Pydantic, pytest. Dependencies in `pyproject.toml`; use a virtualenv.
- React + TypeScript + Vite + Tailwind; charts via Recharts. Typed API client in one module mirroring the Pydantic shapes.
- SQLite for persistence.
- Deploy: front-end on Vercel; API on a free-tier host (Render/Fly.io/Railway).

## Common commands

```bash
# Python (run from engine/ with venv active)
pytest                                   # run all tests
pytest -k undercut                       # run a specific test
python -m engine.ingest --year 2024 --gp "Hungary"   # fetch + cache a race into SQLite
uvicorn api.main:app --reload            # run the API locally

# Web (run from web/)
npm run dev        # Vite dev server
npm run build      # production build
npm run lint
```

## The simulation model

Each car's lap time each lap = sum of these independent, separately-tested components:

1. **Base pace** — per-car constant (s/lap), from real race pace.
2. **Tyre degradation** — linear loss growing with tyre age, per compound.
3. **Compound offset** — fixed pace delta between compounds (softer = faster fresh).
4. **Fuel burn** — lap time improves linearly as fuel burns off.
5. **Pit-lane loss** — one-off penalty (~20s) on the lap a stop is taken.

The simulation advances lap by lap, accumulates total time per car, and recomputes running order each lap. **The undercut/overcut must emerge from these components — never hard-code it.** There is a test that proves an early pit can leapfrog a rival; keep it passing.

All tunable parameters live in a documented config dataclass. Defaults are grounded in real F1:

| Parameter | Realistic default |
|---|---|
| Soft degradation | ~0.10–0.15 s/lap |
| Medium degradation | ~0.06–0.10 s/lap |
| Hard degradation | ~0.03–0.06 s/lap |
| Compound gap (soft→hard) | ~0.6–1.0 s/lap |
| Pit-lane loss (total) | ~18–25 s, circuit dependent |
| Fuel effect | ~0.03–0.06 s/lap improvement per lap |

`engine/CALIBRATION.md` records how the simulated finishing order compares to the real race and where/why it diverges. A regression test locks in the achieved accuracy — don't let it silently regress.

## Conventions

- Keep the engine free of side effects and I/O; pass data in, return data out.
- Type everything: Python type hints + Pydantic models on the API; no `any` on the front-end.
- Components small and focused; one typed API-client module on the web side.
- Tests must not hit the network — use small fixtures, not live FastF1.
- Real F1 compound colours in the UI: soft = red, medium = yellow, hard = white. Dark, pit-wall aesthetic.

## Workflow expectations

- Work in small, reviewable steps; **run `pytest` after engine changes** before moving on.
- Commit after each working chunk with a clear message.
- For larger tasks, propose a short plan before editing.
- The build follows phased milestones (see `PitWall_ClaudeCode_BuildPlan.md` / the project plan): data ingestion → engine → calibration → API → front-end → compare mode & polish → deploy. Build the engine until correct, then the interface until polished.

## Don't

- Don't put simulation logic outside `engine/`.
- Don't call FastF1 from the API or from tests.
- Don't hard-code the undercut.
- Don't add scope beyond the five model components for v1 — extras (Monte Carlo, safety cars, auto-calibration, optimal-strategy solver) are explicit stretch goals, not v1.
