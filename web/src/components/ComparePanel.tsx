import type { CarStrategySchema, CompareResponse } from "../api/types";
import { GapChart } from "./GapChart";

interface Props {
  compare: CompareResponse;
  baselineStrategies: CarStrategySchema[];
  editedStrategies: CarStrategySchema[];
}

export function ComparePanel({ compare: result, baselineStrategies, editedStrategies }: Props) {
  const sorted = [...result.deltas].sort((a, b) => a.position_b - b.position_b);

  const changedDriver = editedStrategies.find((es) => {
    const base = baselineStrategies.find((bs) => bs.driver === es.driver);
    return base != null && JSON.stringify(base.pit_stops) !== JSON.stringify(es.pit_stops);
  })?.driver;

  return (
    <div className="space-y-4">
      {/* Delta table */}
      <section className="bg-zinc-900 border border-zinc-700 rounded p-4">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="text-xs uppercase tracking-widest text-zinc-400">
            {changedDriver
              ? `Strategy Comparison — ${changedDriver} modified`
              : "Strategy Comparison"}
          </h2>
          <div className="flex items-center gap-5 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-5 h-px bg-zinc-500" />
              Baseline (A)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-5 h-px bg-red-500" />
              Modified (B)
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-left border-b border-zinc-800 text-zinc-500">
                <th className="py-2 pr-6 font-medium">Driver</th>
                <th className="py-2 px-3 text-center font-medium">Pos A</th>
                <th className="py-2 px-3 text-center font-medium">Pos B</th>
                <th className="py-2 px-3 text-center font-medium">Pos Δ</th>
                <th className="py-2 pl-3 text-right font-medium">Time Δ</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((d) => {
                // position_delta = a - b; positive = improved in B (lower number is better)
                const posDelta = d.position_a - d.position_b;
                // time_delta = a - b; positive = B was faster
                const timeDelta = d.time_a - d.time_b;
                const isEdited = d.driver === changedDriver;
                const moved = posDelta !== 0;

                return (
                  <tr
                    key={d.driver}
                    className={[
                      "border-b border-zinc-900",
                      isEdited ? "bg-zinc-800/25" : "",
                    ].join(" ")}
                  >
                    <td
                      className={[
                        "py-2 pr-6 font-bold",
                        isEdited
                          ? "text-white"
                          : moved
                          ? "text-zinc-200"
                          : "text-zinc-500",
                      ].join(" ")}
                    >
                      {d.driver}
                      {isEdited && (
                        <span className="ml-2 text-[9px] text-red-400 font-normal uppercase tracking-widest">
                          edited
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-center text-zinc-500">
                      P{d.position_a}
                    </td>
                    <td className="py-2 px-3 text-center text-zinc-200">
                      P{d.position_b}
                    </td>
                    <td className="py-2 px-3 text-center font-bold">
                      {posDelta === 0 ? (
                        <span className="text-zinc-700">—</span>
                      ) : posDelta > 0 ? (
                        <span className="text-emerald-400">▲ {posDelta}</span>
                      ) : (
                        <span className="text-red-400">▼ {Math.abs(posDelta)}</span>
                      )}
                    </td>
                    <td className="py-2 pl-3 text-right tabular-nums">
                      {Math.abs(timeDelta) < 0.05 ? (
                        <span className="text-zinc-700">—</span>
                      ) : timeDelta > 0 ? (
                        <span className="text-emerald-400">
                          −{timeDelta.toFixed(1)} s
                        </span>
                      ) : (
                        <span className="text-red-400">
                          +{Math.abs(timeDelta).toFixed(1)} s
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Side-by-side gap charts */}
      <div className="grid lg:grid-cols-2 gap-4">
        <GapChart
          title="Gap to Leader — Baseline (A)"
          snapshots={result.result_a.snapshots}
          highlightDriver={changedDriver}
        />
        <GapChart
          title="Gap to Leader — Modified (B)"
          snapshots={result.result_b.snapshots}
          highlightDriver={changedDriver}
        />
      </div>
    </div>
  );
}
