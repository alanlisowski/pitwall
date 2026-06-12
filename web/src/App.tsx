import { useCallback, useEffect, useState } from "react";
import { compare as apiCompare, fetchBaseline, fetchRaces } from "./api/client";
import type {
  BaselineResponse,
  CarStrategySchema,
  CompareResponse,
  RaceSummary,
} from "./api/types";
import { ComparePanel } from "./components/ComparePanel";
import { Explainer } from "./components/Explainer";
import { GapChart } from "./components/GapChart";
import { RacePicker } from "./components/RacePicker";
import { StintTimeline } from "./components/StintTimeline";

// ─── Spinner ──────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4 text-zinc-500"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className="opacity-20"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [races, setRaces] = useState<RaceSummary[]>([]);
  const [racesError, setRacesError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [loadingBaseline, setLoadingBaseline] = useState(false);
  const [baselineError, setBaselineError] = useState<string | null>(null);

  const [editedStrategies, setEditedStrategies] = useState<CarStrategySchema[]>([]);
  const [editingDriver, setEditingDriver] = useState<string | null>(null);

  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [loadingCompare, setLoadingCompare] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  // ── Load race list ──────────────────────────────────────────────────────────
  useEffect(() => {
    fetchRaces()
      .then(setRaces)
      .catch((e: Error) => setRacesError(e.message));
  }, []);

  // ── Load baseline when race changes ────────────────────────────────────────
  useEffect(() => {
    if (selectedId === null) return;
    setLoadingBaseline(true);
    setBaseline(null);
    setBaselineError(null);
    setEditingDriver(null);
    setCompareResult(null);
    fetchBaseline(selectedId)
      .then((b) => {
        setBaseline(b);
        setEditedStrategies(b.strategies);
      })
      .catch((e: Error) => setBaselineError(e.message))
      .finally(() => setLoadingBaseline(false));
  }, [selectedId]);

  // ── Strategy edit ───────────────────────────────────────────────────────────
  const handleStrategyChange = useCallback((updated: CarStrategySchema) => {
    setEditedStrategies((prev) =>
      prev.map((s) => (s.driver === updated.driver ? updated : s)),
    );
    setCompareResult(null); // stale — user must re-run
  }, []);

  // ── Run compare ─────────────────────────────────────────────────────────────
  const runCompare = useCallback(async () => {
    if (!baseline || selectedId === null) return;
    setLoadingCompare(true);
    setCompareError(null);
    try {
      const result = await apiCompare({
        race_id: selectedId,
        strategy_a: baseline.strategies,
        strategy_b: editedStrategies,
      });
      setCompareResult(result);
    } catch (e) {
      setCompareError((e as Error).message);
    } finally {
      setLoadingCompare(false);
    }
  }, [baseline, selectedId, editedStrategies]);

  const resetEdits = useCallback(() => {
    if (!baseline) return;
    setEditedStrategies(baseline.strategies);
    setEditingDriver(null);
    setCompareResult(null);
  }, [baseline]);

  const isEdited =
    baseline !== null &&
    JSON.stringify(editedStrategies) !== JSON.stringify(baseline.strategies);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-mono">
      {/* ── Sticky header ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 bg-zinc-950/95 backdrop-blur border-b border-zinc-800 px-4 md:px-8 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-6">
          <div className="shrink-0">
            <h1 className="text-base font-bold tracking-[0.35em] text-zinc-100">
              PITWALL
            </h1>
            <p className="text-[9px] text-zinc-600 tracking-[0.25em] uppercase leading-none mt-0.5">
              F1 Race Strategy Simulator
            </p>
          </div>
          <div className="flex-1 min-w-0">
            <RacePicker
              races={races}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
        </div>
      </header>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-4 md:px-8 py-6 space-y-5">
        {/* API connection warning */}
        {racesError && (
          <div className="p-3 bg-amber-950/40 border border-amber-900 text-amber-300 text-xs rounded flex gap-2">
            <span className="shrink-0 font-bold">!</span>
            <span>
              Could not reach the API.{" "}
              <span className="font-bold">
                Start it with:{" "}
                <code className="text-amber-200 bg-amber-950/60 px-1 py-0.5 rounded">
                  uvicorn api.main:app --reload
                </code>{" "}
                from <code className="text-amber-200">engine/</code>
              </span>
            </span>
          </div>
        )}

        {/* Empty / explainer state */}
        {!baseline && !loadingBaseline && !baselineError && <Explainer />}

        {/* Baseline loading */}
        {loadingBaseline && (
          <div className="flex items-center gap-2 text-zinc-500 text-sm py-4">
            <Spinner />
            Simulating baseline…
          </div>
        )}

        {/* Baseline load error */}
        {baselineError && (
          <div className="p-3 bg-red-950/40 border border-red-900 text-red-300 text-sm rounded">
            {baselineError}
          </div>
        )}

        {/* ── Race loaded ─────────────────────────────────────────────────── */}
        {baseline && (
          <>
            {/* Race metadata + action bar */}
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div className="text-xs text-zinc-500 space-x-2">
                <span className="text-zinc-200 font-bold">
                  {baseline.race.gp_name}
                </span>
                <span>·</span>
                <span>{baseline.race.circuit}</span>
                <span>·</span>
                <span>{baseline.race.total_laps} laps</span>
                <span>·</span>
                <span>{baseline.strategies.length} cars</span>
              </div>

              <div className="flex items-center gap-2">
                {isEdited && (
                  <button
                    onClick={resetEdits}
                    className="text-xs text-zinc-400 hover:text-zinc-100 border border-zinc-700 hover:border-zinc-500 px-3 py-1.5 rounded transition-colors"
                  >
                    Reset
                  </button>
                )}
                <button
                  onClick={runCompare}
                  disabled={loadingCompare || !isEdited}
                  className={[
                    "text-xs px-4 py-1.5 rounded font-bold tracking-wider transition-all",
                    loadingCompare || !isEdited
                      ? "bg-zinc-800 text-zinc-600 cursor-not-allowed"
                      : "bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/30",
                  ].join(" ")}
                >
                  {loadingCompare ? (
                    <span className="flex items-center gap-2">
                      <Spinner /> Simulating…
                    </span>
                  ) : (
                    "▶ Compare"
                  )}
                </button>
              </div>
            </div>

            {/* Edit hint */}
            {!isEdited && !compareResult && (
              <div className="text-[11px] text-zinc-600 -mt-1">
                Hover any driver row and click{" "}
                <span className="text-zinc-400">Edit</span> to modify their
                pit-stop strategy, then hit{" "}
                <span className="text-zinc-400">▶ Compare</span>.
              </div>
            )}

            {/* Timeline */}
            <StintTimeline
              strategies={editedStrategies}
              totalLaps={baseline.race.total_laps}
              snapshots={baseline.result.snapshots}
              editingDriver={editingDriver}
              onEditDriver={setEditingDriver}
              onStrategyChange={handleStrategyChange}
            />

            {/* Compare error */}
            {compareError && (
              <div className="p-3 bg-red-950/40 border border-red-900 text-red-300 text-sm rounded">
                {compareError}
              </div>
            )}

            {/* Compare result or baseline gap chart */}
            {compareResult ? (
              <ComparePanel
                compare={compareResult}
                baselineStrategies={baseline.strategies}
                editedStrategies={editedStrategies}
              />
            ) : (
              <GapChart
                title="Gap to Leader — Baseline"
                snapshots={baseline.result.snapshots}
              />
            )}
          </>
        )}
      </main>

      {/* ── Footer ────────────────────────────────────────────────────────── */}
      <footer className="border-t border-zinc-900 px-4 md:px-8 py-4 mt-8">
        <p className="text-[10px] text-zinc-700 max-w-7xl mx-auto">
          PITWALL · Five-component F1 lap model · Data: FastF1 / Formula 1 ·
          Built with FastAPI + React
        </p>
      </footer>
    </div>
  );
}
