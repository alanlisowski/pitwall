import { useCallback, useEffect, useRef, useState } from "react";
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
import { RaceEngineerScreen } from "./components/RaceEngineerScreen";
import { RacePicker } from "./components/RacePicker";
import { StintTimeline } from "./components/StintTimeline";

// ─── Spinner ──────────────────────────────────────────────────────────────────

export function Spinner() {
  return (
    <span className="inline-block w-4 h-4 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin shrink-0" />
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [mode, setMode] = useState<"strategy" | "race">("race");

  const [races, setRaces] = useState<RaceSummary[]>([]);
  const [racesLoading, setRacesLoading] = useState(true);
  const [racesWaking, setRacesWaking] = useState(false);
  const [racesError, setRacesError] = useState<string | null>(null);
  const [racesRetryKey, setRacesRetryKey] = useState(0);

  // pickerValue = what's highlighted in the race dropdown (display only)
  // committedId = what actually triggers a baseline load (set only on explicit button click)
  const [pickerValue, setPickerValue] = useState<number | null>(null);
  const [committedId, setCommittedId] = useState<number | null>(null);
  const [baselineRetryKey, setBaselineRetryKey] = useState(0);
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [loadingBaseline, setLoadingBaseline] = useState(false);
  const [baselineWaking, setBaselineWaking] = useState(false);
  const [baselineError, setBaselineError] = useState<string | null>(null);

  const [editedStrategies, setEditedStrategies] = useState<CarStrategySchema[]>([]);
  const [editingDriver, setEditingDriver] = useState<string | null>(null);

  const [compareResult, setCompareResult] = useState<CompareResponse | null>(null);
  const [loadingCompare, setLoadingCompare] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const [needsRaceToast, setNeedsRaceToast] = useState(false);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Load race list with retry for Render cold-start ────────────────────────
  useEffect(() => {
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;
    let attempt = 0;

    setRacesLoading(true);
    setRacesWaking(false);
    setRacesError(null);

    async function tryFetch() {
      try {
        const data = await fetchRaces();
        if (!cancelled) {
          setRaces(data);
          setRacesLoading(false);
          setRacesWaking(false);
        }
      } catch (e) {
        if (cancelled) return;
        attempt += 1;
        if (attempt < 15) {
          setRacesLoading(false);
          setRacesWaking(true);
          timeoutId = setTimeout(tryFetch, 3000);
        } else {
          setRacesLoading(false);
          setRacesWaking(false);
          setRacesError((e as Error).message);
        }
      }
    }

    tryFetch();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [racesRetryKey]);

  // ── Load baseline only when committedId changes (set by explicit button click) ─
  useEffect(() => {
    if (committedId === null) return;
    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout>;
    let attempt = 0;

    setLoadingBaseline(true);
    setBaseline(null);
    setBaselineError(null);
    setBaselineWaking(false);
    setEditingDriver(null);
    setCompareResult(null);

    async function tryFetch() {
      try {
        const b = await fetchBaseline(committedId!);
        if (!cancelled) {
          setBaseline(b);
          setEditedStrategies(b.strategies);
          setLoadingBaseline(false);
          setBaselineWaking(false);
        }
      } catch (e) {
        if (cancelled) return;
        attempt += 1;
        if (attempt < 8) {
          setLoadingBaseline(false);
          setBaselineWaking(true);
          timeoutId = setTimeout(tryFetch, 5000);
        } else {
          setLoadingBaseline(false);
          setBaselineWaking(false);
          setBaselineError((e as Error).message);
        }
      }
    }

    tryFetch();
    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [committedId, baselineRetryKey]);

  // ── Strategy edit ───────────────────────────────────────────────────────────
  const handleStrategyChange = useCallback((updated: CarStrategySchema) => {
    setEditedStrategies((prev) =>
      prev.map((s) => (s.driver === updated.driver ? updated : s)),
    );
    setCompareResult(null); // stale — user must re-run
  }, []);

  // ── Run compare ─────────────────────────────────────────────────────────────
  const runCompare = useCallback(async () => {
    if (!baseline || committedId === null) return;
    setLoadingCompare(true);
    setCompareError(null);
    try {
      const result = await apiCompare({
        race_id: committedId,
        strategy_a: baseline.strategies,
        strategy_b: editedStrategies,
      });
      setCompareResult(result);
    } catch (e) {
      setCompareError((e as Error).message);
    } finally {
      setLoadingCompare(false);
    }
  }, [baseline, committedId, editedStrategies]);

  const resetEdits = useCallback(() => {
    if (!baseline) return;
    setEditedStrategies(baseline.strategies);
    setEditingDriver(null);
    setCompareResult(null);
  }, [baseline]);

  // ── Enter a mode (card CTA or header toggle) ────────────────────────────────
  // If no race is selected in the picker, show a toast and bail.
  // If a race is selected but not yet committed (or a different one), commit it.
  // If baseline is already loaded for this same race, just switch modes.
  const handleEnterMode = useCallback((m: "race" | "strategy") => {
    if (pickerValue === null) {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      setNeedsRaceToast(true);
      toastTimerRef.current = setTimeout(() => setNeedsRaceToast(false), 3500);
      return;
    }
    setMode(m);
    if (pickerValue !== committedId) setCommittedId(pickerValue);
  }, [pickerValue, committedId]);

  const isEdited =
    baseline !== null &&
    JSON.stringify(editedStrategies) !== JSON.stringify(baseline.strategies);

  return (
    <div className="min-h-screen text-[#ECE7DA]" style={{ backgroundColor: "#15151c", fontFamily: "'Saira', ui-monospace, monospace" }}>
      {/* ── Sticky header ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 backdrop-blur" style={{ backgroundColor: "#1d1d26dd", borderBottom: "none" }}>
        <div className="max-w-7xl mx-auto px-4 md:px-8 py-2.5 flex items-center justify-between gap-6">
          <div className="shrink-0 flex items-center gap-2">
            {/* Speed bars */}
            <div className="flex items-center gap-[3px]">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  style={{
                    width: 5,
                    height: 20,
                    background: "#E10600",
                    transform: "skewX(-14deg)",
                  }}
                />
              ))}
            </div>
            <div>
              <h1
                style={{
                  fontFamily: "'Chakra Petch', ui-monospace, monospace",
                  fontStyle: "italic",
                  fontWeight: 700,
                  fontSize: 18,
                  letterSpacing: "0.04em",
                  lineHeight: 1,
                }}
              >
                <span style={{ color: "#fff" }}>PIT</span>
                <span style={{ color: "#E10600" }}>WALL</span>
              </h1>
              <p style={{ fontSize: 9, color: "#6b7280", letterSpacing: "0.25em", textTransform: "uppercase", marginTop: 2 }}>
                F1 Race Strategy Simulator
              </p>
            </div>
          </div>
          <div className="flex-1 min-w-0">
            {racesLoading ? (
              <div className="flex items-center gap-2 text-xs text-zinc-500">
                <Spinner />
                <span>Loading races…</span>
              </div>
            ) : racesWaking ? (
              <div className="flex items-center gap-2 text-xs text-zinc-400">
                <Spinner />
                <span>
                  Waking up the server…{" "}
                  <span className="text-zinc-600">first load can take ~30s</span>
                </span>
              </div>
            ) : racesError ? (
              <div className="flex items-center gap-2 text-xs text-amber-400">
                <span>Could not reach the server.</span>
                <button
                  onClick={() => setRacesRetryKey((k) => k + 1)}
                  className="border border-amber-800 hover:border-amber-600 px-2 py-0.5 rounded text-amber-300 hover:text-amber-100 transition-colors"
                >
                  Retry
                </button>
              </div>
            ) : (
              <RacePicker
                races={races}
                selectedId={pickerValue}
                onSelect={(id) => {
                  setPickerValue(id);
                  // Already in a mode — reload baseline immediately for the new race
                  if (committedId !== null) setCommittedId(id);
                }}
              />
            )}
          </div>

          {!racesLoading && !racesWaking && !racesError && races.length > 0 && (
            <div
              className="shrink-0"
              style={{
                display: "flex",
                background: "#12121a",
                border: "1px solid #2a2a38",
                borderRadius: 6,
                padding: 3,
                gap: 2,
              }}
            >
              {(["race", "strategy"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => {
                    // Once in a mode (baseline loaded), just switch — no re-commit needed
                    if (baseline !== null) { setMode(m); return; }
                    handleEnterMode(m);
                  }}
                  style={{
                    padding: "5px 14px",
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: "0.12em",
                    textTransform: "uppercase",
                    fontFamily: "'Chakra Petch', ui-monospace, monospace",
                    border: "none",
                    cursor: "pointer",
                    background: mode === m && baseline !== null ? "#E10600" : "transparent",
                    color: mode === m && baseline !== null ? "#fff" : "#52525b",
                    transition: "background 0.15s, color 0.15s",
                    whiteSpace: "nowrap",
                  }}
                >
                  {m === "race" ? "🏁 Race" : "⚙ Strategy"}
                </button>
              ))}
            </div>
          )}
        </div>
        {/* Kerb stripe */}
        <div
          style={{
            height: 3,
            background:
              "repeating-linear-gradient(135deg, #E10600 0px, #E10600 8px, #ffffff 8px, #ffffff 16px)",
          }}
        />
      </header>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <main className="max-w-7xl mx-auto px-4 md:px-8 py-6 space-y-5">
        {/* Empty / explainer state */}
        {!baseline && !loadingBaseline && !baselineWaking && !baselineError && (
          <Explainer onEnterMode={handleEnterMode} />
        )}

        {/* Baseline loading */}
        {loadingBaseline && (
          <div className="flex items-center gap-2 text-zinc-500 text-sm py-4">
            <Spinner />
            Simulating baseline…
          </div>
        )}

        {/* Baseline waking (retrying after cold-start) */}
        {baselineWaking && (
          <div className="flex items-center gap-2 text-zinc-400 text-sm py-4">
            <Spinner />
            <span>
              Waking up the server…{" "}
              <span className="text-zinc-600">first load can take ~30s</span>
            </span>
          </div>
        )}

        {/* Baseline load error */}
        {baselineError && (
          <div className="p-3 bg-red-950/40 border border-red-900 text-red-300 text-sm rounded flex items-center gap-3">
            <span className="flex-1">{baselineError}</span>
            <button
              onClick={() => setBaselineRetryKey((k) => k + 1)}
              className="shrink-0 border border-red-800 hover:border-red-600 px-2 py-0.5 rounded text-red-300 hover:text-red-100 transition-colors text-xs"
            >
              Retry
            </button>
          </div>
        )}

        {/* ── Race Engineer Mode ──────────────────────────────────────────── */}
        {baseline && mode === "race" && (
          <RaceEngineerScreen
            baseline={baseline}
            onBack={() => setMode("strategy")}
          />
        )}

        {/* ── Race loaded ─────────────────────────────────────────────────── */}
        {baseline && mode === "strategy" && (
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

      {/* ── "Select a race first" toast ──────────────────────────────────── */}
      {needsRaceToast && (
        <div
          onClick={() => {
            if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
            setNeedsRaceToast(false);
          }}
          style={{
            position: "fixed",
            bottom: 28,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 200,
            background: "#17171f",
            border: "1px solid #3a0a0a",
            borderLeft: "3px solid #E10600",
            borderRadius: 4,
            padding: "10px 20px 10px 14px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            boxShadow: "0 6px 32px rgba(0,0,0,0.7)",
            cursor: "pointer",
            animation: "toast-in 0.28s ease-out",
            whiteSpace: "nowrap",
          }}
        >
          <span style={{ color: "#E10600", fontSize: 14, lineHeight: 1 }}>⚑</span>
          <span
            style={{
              fontFamily: "'Chakra Petch', ui-monospace, monospace",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "#ECE7DA",
            }}
          >
            Select a Grand Prix first
          </span>
          <span
            style={{
              fontFamily: "'Saira', ui-monospace, monospace",
              fontSize: 9,
              color: "#52525b",
              marginLeft: 4,
            }}
          >
            click to dismiss
          </span>
        </div>
      )}

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
