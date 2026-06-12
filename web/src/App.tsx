import { useEffect, useState } from "react";
import { fetchBaseline, fetchRaces } from "./api/client";
import type { BaselineResponse, RaceSummary } from "./api/types";
import { GapChart } from "./components/GapChart";
import { RacePicker } from "./components/RacePicker";
import { StintTimeline } from "./components/StintTimeline";

export default function App() {
  const [races, setRaces] = useState<RaceSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [baseline, setBaseline] = useState<BaselineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRaces()
      .then(setRaces)
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    setLoading(true);
    setBaseline(null);
    setError(null);
    fetchBaseline(selectedId)
      .then(setBaseline)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [selectedId]);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 font-mono p-4 md:p-6">
      {/* Header */}
      <header className="mb-6 pb-4 border-b border-zinc-800">
        <h1 className="text-2xl font-bold tracking-[0.3em] text-zinc-100">
          PITWALL
        </h1>
        <p className="text-[11px] text-zinc-600 mt-0.5 tracking-[0.2em] uppercase">
          F1 Race Strategy Simulator
        </p>
      </header>

      <div className="max-w-7xl mx-auto space-y-6">
        <RacePicker
          races={races}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />

        {error && (
          <div className="p-3 bg-red-950/60 border border-red-800 text-red-300 text-sm rounded">
            {error}
          </div>
        )}

        {loading && (
          <p className="text-zinc-500 text-sm animate-pulse">
            Simulating baseline…
          </p>
        )}

        {baseline && (
          <>
            <div className="text-xs text-zinc-600 -mb-2">
              {baseline.race.circuit} · {baseline.race.total_laps} laps ·{" "}
              {baseline.strategies.length} cars
            </div>
            <StintTimeline
              strategies={baseline.strategies}
              totalLaps={baseline.race.total_laps}
              snapshots={baseline.result.snapshots}
            />
            <GapChart snapshots={baseline.result.snapshots} />
          </>
        )}
      </div>
    </div>
  );
}
