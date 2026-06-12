import type { CarStrategySchema, Compound } from "../api/types";

interface Props {
  strategy: CarStrategySchema;
  totalLaps: number;
  onChange: (updated: CarStrategySchema) => void;
  onClose: () => void;
}

const COMPOUNDS: Compound[] = ["SOFT", "MEDIUM", "HARD"];

export function StrategyEditor({ strategy, totalLaps, onChange, onClose }: Props) {
  const sorted = [...strategy.pit_stops].sort((a, b) => a.lap - b.lap);

  function updateLap(idx: number, raw: number) {
    const lap = Math.max(1, Math.min(totalLaps - 1, raw));
    const next = sorted.map((p, i) => (i === idx ? { ...p, lap } : p));
    onChange({ ...strategy, pit_stops: next });
  }

  function updateCompound(idx: number, compound: Compound) {
    const next = sorted.map((p, i) => (i === idx ? { ...p, compound } : p));
    onChange({ ...strategy, pit_stops: next });
  }

  function addStop() {
    const lastLap = sorted.length > 0 ? sorted[sorted.length - 1].lap : 0;
    const gap = Math.floor(totalLaps / (sorted.length + 2));
    const lap = Math.min(totalLaps - 1, lastLap + gap);
    onChange({
      ...strategy,
      pit_stops: [...sorted, { lap, compound: "HARD" }],
    });
  }

  function removeStop(idx: number) {
    onChange({ ...strategy, pit_stops: sorted.filter((_, i) => i !== idx) });
  }

  return (
    <div className="ml-[88px] mr-[60px] mt-px mb-2 px-3 py-2.5 bg-zinc-950 border border-t-0 border-zinc-700 rounded-b text-xs">
      <div className="flex items-center justify-between mb-2.5">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500 font-bold">
          Editing: {strategy.driver}
        </span>
        <button
          onClick={onClose}
          className="text-zinc-600 hover:text-zinc-300 transition-colors leading-none px-1"
          aria-label="Close editor"
        >
          ✕
        </button>
      </div>

      <div className="space-y-1.5">
        {sorted.map((pit, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="text-zinc-600 w-12 shrink-0">Stop {i + 1}</span>
            <span className="text-zinc-600 shrink-0">Lap</span>
            <input
              type="number"
              min={1}
              max={totalLaps - 1}
              value={pit.lap}
              onChange={(e) => updateLap(i, parseInt(e.target.value, 10) || 1)}
              className="w-14 bg-zinc-800 border border-zinc-700 focus:border-zinc-500 text-zinc-100 px-2 py-0.5 rounded text-xs focus:outline-none"
            />
            <select
              value={pit.compound}
              onChange={(e) => updateCompound(i, e.target.value as Compound)}
              className="bg-zinc-800 border border-zinc-700 text-zinc-100 px-2 py-0.5 rounded text-xs focus:outline-none focus:border-zinc-500"
            >
              {COMPOUNDS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <button
              onClick={() => removeStop(i)}
              className="text-zinc-700 hover:text-red-400 transition-colors ml-1 text-base leading-none"
              aria-label={`Remove stop ${i + 1}`}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {sorted.length < 3 && (
        <button
          onClick={addStop}
          className="mt-2 text-zinc-600 hover:text-zinc-300 transition-colors"
        >
          + Add stop
        </button>
      )}

      <p className="mt-2.5 text-zinc-700 text-[10px]">
        Drag the white handles on the bar above, or type a lap number directly.
      </p>
    </div>
  );
}
