# PitWall

An interactive Formula 1 race strategy simulator. Pick a real Grand Prix, edit your pit-stop strategy, and watch the engine re-simulate the race lap-by-lap — modelling tyre degradation, fuel burn, pit-lane time loss, and the undercut/overcut. Move a pit stop and see the entire field reorder with a delta vs. the baseline strategy.

Built as a portfolio project: a pure-Python simulation engine (FastF1 data, NumPy/pandas), a FastAPI layer, and a React + TypeScript + Vite front-end.

## Structure

```
engine/   pure Python simulation + FastF1 data ingestion
web/      React + TypeScript + Vite front-end (coming soon)
```

## Quickstart

```bash
# Python (from engine/, with venv active)
pip install -e ".[dev]"
pytest

# Web (from web/)
npm run dev
```
