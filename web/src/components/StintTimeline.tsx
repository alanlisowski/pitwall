import type { CarStrategySchema, LapSnapshotSchema } from "../api/types";

interface Stint {
  startLap: number;
  endLap: number;
  compound: string;
}

const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#ef4444",
  MEDIUM: "#eab308",
  HARD: "#d4d4d8",
};

const COMPOUND_LABEL: Record<string, string> = {
  SOFT: "S",
  MEDIUM: "M",
  HARD: "H",
};

function deriveStints(strategy: CarStrategySchema, totalLaps: number): Stint[] {
  const stints: Stint[] = [];
  let startLap = 1;
  let compound: string = strategy.start_compound;
  const sorted = [...strategy.pit_stops].sort((a, b) => a.lap - b.lap);
  for (const pit of sorted) {
    stints.push({ startLap, endLap: pit.lap, compound });
    startLap = pit.lap + 1;
    compound = pit.compound;
  }
  stints.push({ startLap, endLap: totalLaps, compound });
  return stints;
}

interface Props {
  strategies: CarStrategySchema[];
  totalLaps: number;
  snapshots: LapSnapshotSchema[];
}

export function StintTimeline({ strategies, totalLaps, snapshots }: Props) {
  const positions = new Map<string, number>();
  for (const s of snapshots) {
    if (s.lap === totalLaps) positions.set(s.driver, s.position);
  }

  const sorted = [...strategies].sort(
    (a, b) => (positions.get(a.driver) ?? 99) - (positions.get(b.driver) ?? 99),
  );

  const tickStep = totalLaps > 60 ? 10 : 5;
  const ticks: number[] = [];
  for (let t = tickStep; t < totalLaps; t += tickStep) ticks.push(t);

  return (
    <section className="bg-zinc-900 border border-zinc-700 rounded p-4">
      {/* Header row */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs uppercase tracking-widest text-zinc-400">
          Race Strategy — Baseline
        </h2>
        <div className="flex items-center gap-4 text-xs text-zinc-400">
          {(["SOFT", "MEDIUM", "HARD"] as const).map((c) => (
            <span key={c} className="flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-3 rounded-sm"
                style={{ backgroundColor: COMPOUND_COLOR[c] }}
              />
              {c}
            </span>
          ))}
        </div>
      </div>

      {/* Lap-axis ticks */}
      <div className="flex mb-1 ml-[88px] mr-12">
        <div className="relative flex-1 h-4">
          <span
            className="absolute text-[10px] text-zinc-600"
            style={{ left: 0 }}
          >
            1
          </span>
          {ticks.map((lap) => (
            <span
              key={lap}
              className="absolute text-[10px] text-zinc-600 -translate-x-1/2"
              style={{ left: `${((lap - 1) / (totalLaps - 1)) * 100}%` }}
            >
              {lap}
            </span>
          ))}
          <span className="absolute text-[10px] text-zinc-600 right-0">
            {totalLaps}
          </span>
        </div>
      </div>

      {/* Car rows */}
      <div className="space-y-[3px] max-h-[520px] overflow-y-auto pr-2">
        {sorted.map((strategy) => {
          const stints = deriveStints(strategy, totalLaps);
          const pos = positions.get(strategy.driver);
          return (
            <div key={strategy.driver} className="flex items-center gap-2">
              {/* Position badge */}
              <span className="w-7 text-right text-[10px] text-zinc-500 shrink-0">
                {pos != null ? `P${pos}` : ""}
              </span>
              {/* Driver code */}
              <span className="w-9 text-[12px] font-bold text-zinc-200 shrink-0 tracking-wider">
                {strategy.driver}
              </span>
              {/* Timeline bar */}
              <div className="relative flex-1 h-6 bg-zinc-800 rounded overflow-hidden">
                {stints.map((stint, i) => {
                  const leftPct = ((stint.startLap - 1) / totalLaps) * 100;
                  const widthPct =
                    ((stint.endLap - stint.startLap + 1) / totalLaps) * 100;
                  const color =
                    COMPOUND_COLOR[stint.compound] ?? "#71717a";
                  return (
                    <div
                      key={i}
                      className="absolute top-0 h-full flex items-center justify-center overflow-hidden"
                      style={{
                        left: `${leftPct}%`,
                        width: `${widthPct}%`,
                        backgroundColor: color,
                      }}
                      title={`${stint.compound}: Laps ${stint.startLap}–${stint.endLap}`}
                    >
                      {widthPct > 6 && (
                        <span className="text-[9px] font-bold text-black/60 select-none">
                          {COMPOUND_LABEL[stint.compound]}
                        </span>
                      )}
                    </div>
                  );
                })}
                {/* Pit-stop dividers */}
                {strategy.pit_stops.map((pit, i) => (
                  <div
                    key={i}
                    className="absolute top-0 h-full z-10 pointer-events-none"
                    style={{
                      left: `${(pit.lap / totalLaps) * 100}%`,
                      width: "2px",
                      backgroundColor: "rgba(0,0,0,0.6)",
                    }}
                    title={`Pit lap ${pit.lap} → ${pit.compound}`}
                  />
                ))}
              </div>
              {/* Stop count */}
              <span className="w-10 text-[10px] text-zinc-600 shrink-0">
                {strategy.pit_stops.length}
                {strategy.pit_stops.length === 1 ? " stop" : " stops"}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
