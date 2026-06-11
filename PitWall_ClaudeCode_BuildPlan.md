# PitWall — Claude Code Build Plan & Prompts

An F1 race strategy simulator. Build the engine until it's *correct*, then the interface until it's *beautiful*. Ship it live.

**Stack:** Python sim engine + FastAPI · React + TypeScript + Vite (Recharts/D3) · SQLite · FastF1 · deploy on Vercel (web) + Render/Fly/Railway (API).

---

## How to use this with Claude Code

- Work **one phase at a time**, in order. Don't paste the whole plan at once.
- For any non-trivial prompt, **let Claude Code plan first**: press `Shift+Tab` to enter plan mode, paste the prompt, review the plan, then approve. This stops it from sprawling.
- **Commit after every green phase.** A prompt is included for it, or just say `commit this with a sensible message`.
- After Phase 0, run `/init` so Claude Code writes a `CLAUDE.md` — it'll carry project context between sessions.
- If a phase is big, tell it: `do this in small steps and stop after each for me to review.`
- Keep the engine **decoupled** from the web layer the whole way through. That separation is the thing you'll talk about in interviews.

---

## Phase 0 — Scaffold the repo

```
Set up a new project called "pitwall", an F1 race strategy simulator. Structure it as a monorepo with two top-level folders:

- `engine/` — a pure Python package (Python 3.11+) for the simulation, plus data ingestion from the FastF1 library. Use a virtualenv and a pyproject.toml. Add pytest, numpy, pandas, and fastf1 as dependencies. No web framework here yet.
- `web/` — placeholder for a React + TypeScript + Vite front-end (leave empty for now, just a README note).

Add a root README.md describing the project in 3-4 sentences, a .gitignore for Python + Node + a local FastF1 cache folder, and initialise git. Do NOT install a web framework or build any features yet — just the skeleton, the Python env, and a passing `pytest` that runs zero tests. Confirm the env works.
```

Then: `/init` to generate `CLAUDE.md`, and commit.

---

## Phase 1 — Data ingestion (FastF1 → SQLite)

```
In the `engine/` package, build a data ingestion module that uses FastF1 to fetch one Grand Prix race session and cache it locally.

Requirements:
- Enable FastF1's on-disk cache (a local folder, gitignored) so we never re-download.
- A function `load_race(year, gp, session="R")` that returns a clean, typed structure containing, per driver: starting grid position, every lap's time, the tyre compound, tyre life (age in laps), stint number, and pit in/out laps. Also expose the final classification (real finishing order) and the circuit name + total lap count.
- Persist this into a local SQLite database (tables for races, drivers, and laps) so the rest of the app reads from SQLite, never from FastF1 directly.
- A small CLI: `python -m engine.ingest --year 2024 --gp "Hungary"` that fetches and stores a race, and prints a summary.

Use the 2024 Hungarian GP as the test case. Write a short script or notebook cell that plots real lap times coloured by stint, so I can eyeball the data shape. Add a couple of unit tests with a tiny fixture (don't hit the network in tests).
```

Commit.

---

## Phase 2 — The simulation engine (the core)

```
In `engine/`, build the lap-by-lap race simulation as a PURE Python module with NO web or DB dependencies. It takes a race config + a strategy in, and returns a lap-by-lap result out.

The lap time for each car each lap is the sum of these components (make each one a separate, testable function):
1. Base pace — a per-car constant (seconds/lap).
2. Tyre degradation — linear loss that grows with tyre age, with a per-compound rate.
3. Compound offset — a fixed pace delta between compounds (softer = faster when fresh).
4. Fuel burn — lap time improves linearly as the car gets lighter over the race.
5. Pit-lane loss — a one-off time penalty (~20s) on the lap a stop is taken.

Model:
- `Strategy` = the list of pit stops per car (lap number + new compound).
- The simulation loop advances lap by lap, accumulates each car's total time, and recomputes running order each lap.
- Return a result object with, per lap: each car's position, gap to leader, current compound and tyre age — plus the final finishing order and total race times.

Store all tunable parameters (deg rates, compound offsets, pit loss, fuel effect) in a clearly-documented config dataclass with sensible defaults grounded in real F1 (soft deg ~0.10-0.15 s/lap, medium ~0.06-0.10, hard ~0.03-0.06; pit loss ~18-25s; compound gap ~0.6-1.0 s/lap).

Write thorough pytest unit tests, including one that proves the UNDERCUT emerges: a car pitting earlier onto fresh tyres can leapfrog a rival who stays out on worn tyres. Do this in small steps and run the tests after each.
```

Commit when green. This is the heart of the project — don't rush it.

---

## Phase 3 — Calibrate & validate against a real race

```
Add a calibration/validation module to `engine/`. Using the real 2024 Hungarian GP data already in SQLite:

- Build a function that constructs a "baseline" race config from the real data: each car's base pace from their actual race pace, their real starting grid, and their real pit stops/compounds as the strategy.
- Run the simulation on this baseline and compare the simulated finishing order against the REAL finishing order. Report a simple accuracy metric (e.g. position correlation / mean position error).
- Tune the default parameters so the simulated order is a reasonable match to reality, and write a short markdown note (`engine/CALIBRATION.md`) explaining where the model matches, where it diverges, and why.

Add a regression test that locks in the achieved accuracy so it can't silently get worse.
```

Commit. The `CALIBRATION.md` is gold for your case study.

---

## Phase 4 — FastAPI layer

```
Add a FastAPI app in `engine/` (or a sibling `api/` package) that wraps the simulation. The web layer must call the engine, never reimplement logic.

Endpoints:
- `GET /races` — list races available in SQLite.
- `GET /races/{id}/baseline` — the baseline config + the baseline simulated result.
- `POST /simulate` — accepts a race id + a strategy (pit stops per car), runs the engine, returns the full lap-by-lap result (positions, gaps, compounds, tyre ages, finishing order, total times).
- `POST /compare` — accepts a race id + two strategies, returns both results plus the delta (who finishes ahead and by how many seconds).

Use Pydantic models for all request/response shapes. Add CORS for a local Vite dev server. Add a few endpoint tests with FastAPI's TestClient. Deploy a "hello world" version to a free-tier host (Render or Fly.io) to prove deployment works early — tell me what config files you need.
```

Commit.

---

## Phase 5 — React front-end: the interactive timeline

```
Scaffold the `web/` app with Vite + React + TypeScript + Tailwind. Build the core race-timeline screen that talks to the FastAPI backend.

Features:
- Pick a race from `GET /races`.
- Show a horizontal timeline: a lap axis, and one "stint bar" per car coloured by tyre compound, with pit stops as markers.
- A line chart (Recharts) showing each car's gap to the leader over the race.
- Let the user EDIT a strategy: change a pit-stop lap and the new compound. For v1 start with a simple numeric lap input + compound dropdown per stop (drag-and-drop comes later).
- On edit, call `POST /simulate` and re-render the timeline + chart, animating the new running order.
- A summary panel: finishing positions, total race time, and net gain/loss vs. the baseline strategy.

Use a typed API client (one module, fetch wrappers matching the Pydantic shapes). Keep components small and clean. Build it incrementally and stop after the timeline renders so I can check it before we add interactivity.
```

Commit.

---

## Phase 6 — Compare mode, drag-and-drop, polish

```
Polish the front-end:
- Add "compare mode": pit two strategies against each other using `POST /compare`, showing both results and the delta (e.g. one-stop vs two-stop, who wins and by how much).
- Upgrade the pit-stop editor to drag-and-drop along the lap axis (keep the numeric input as a fallback).
- Make it responsive and visually sharp — an F1 pit-wall aesthetic (dark theme, compound colours matching real F1: soft=red, medium=yellow, hard=white).
- Add empty/loading/error states and a short on-screen explainer of what the simulator does.
- Write a strong root README as a case study: problem, the model, the decoupled architecture, how you validated against a real race, and trade-offs. Include a spot for a demo GIF.
```

Commit.

---

## Phase 7 — Deploy & write-up

```
Take the whole project to production:
- Deploy the FastAPI backend to the free-tier host with the SQLite database (pre-seed it with 2-3 ingested races so the app works without live FastF1 calls).
- Deploy the React front-end to Vercel, pointed at the deployed API URL via an env var.
- Verify the live site end-to-end and give me the public URL.
- Add a 30-60 second demo: tell me exactly how to screen-record dragging a pit stop and watching the order change, and where to drop the GIF in the README and on my portfolio.
```

Commit and tag `v1`.

---

## Stretch prompts (after v1 is live)

```
Add auto-calibration: fit per-compound degradation rates and compound offsets from real stint data using linear regression (lap time vs tyre age per stint), per circuit, replacing the hand-tuned defaults. Show before/after validation accuracy.
```

```
Add a Monte Carlo mode: introduce randomness (safety cars, pit-stop time variance, per-lap noise) and run thousands of simulations of a strategy to report a win-probability distribution rather than a single outcome. Visualise it.
```

```
Model safety car / virtual safety car periods, where the pit-loss penalty is heavily discounted — the biggest strategic swing in real F1 — and let the user drop an SC window onto the timeline.
```

```
Add an optimal-strategy solver that searches over pit laps and compound choices to recommend the fastest strategy for a given car, instead of only evaluating the user's input.
```

---

### One-liner for your CV / README
> A lap-by-lap F1 race strategy simulator built on real timing data (FastF1), with an interactive React front-end where moving a single pit stop re-orders the whole field.
