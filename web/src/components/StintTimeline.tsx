import { useRef } from "react";
import type { CarStrategySchema, LapSnapshotSchema, PitStopSchema } from "../api/types";
import { StrategyEditor } from "./StrategyEditor";

// ─── Constants ────────────────────────────────────────────────────────────────

const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#ef4444",
  MEDIUM: "#eab308",
  HARD: "#f4f4f5",
};

const COMPOUND_LABEL: Record<string, string> = {
  SOFT: "S",
  MEDIUM: "M",
  HARD: "H",
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

interface Stint {
  startLap: number;
  endLap: number;
  compound: string;
}

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

// ─── Draggable pit marker ─────────────────────────────────────────────────────

interface PitMarkerProps {
  sortedIdx: number;
  lap: number;
  totalLaps: number;
  sortedPits: PitStopSchema[];
  barRef: React.RefObject<HTMLDivElement | null>;
  onMove: (sortedIdx: number, newLap: number) => void;
}

function PitMarker({ sortedIdx, lap, totalLaps, sortedPits, barRef, onMove }: PitMarkerProps) {
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const bar = barRef.current;
    if (!bar) return;
    const rect = bar.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const raw = Math.round(pct * totalLaps);
    // Clamp: can't cross adjacent stops
    const prevLap = sortedIdx > 0 ? sortedPits[sortedIdx - 1].lap + 1 : 1;
    const nextLap =
      sortedIdx < sortedPits.length - 1
        ? sortedPits[sortedIdx + 1].lap - 1
        : totalLaps - 1;
    const newLap = Math.max(prevLap, Math.min(nextLap, raw));
    onMove(sortedIdx, newLap);
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.releasePointerCapture(e.pointerId);
  };

  return (
    <div
      className="absolute top-0 h-full w-5 -translate-x-1/2 z-20 cursor-ew-resize flex items-center justify-center group/marker touch-none select-none"
      style={{ left: `${(lap / totalLaps) * 100}%` }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      {/* Visible handle */}
      <div className="w-[3px] h-[80%] rounded-full bg-white/70 shadow-lg group-hover/marker:bg-white group-active/marker:bg-yellow-300 transition-colors" />
    </div>
  );
}

// ─── Static car row ───────────────────────────────────────────────────────────

interface StaticRowProps {
  strategy: CarStrategySchema;
  totalLaps: number;
  position: number | undefined;
  isEditing: boolean;
  onEdit: () => void;
}

function StaticCarRow({ strategy, totalLaps, position, isEditing, onEdit }: StaticRowProps) {
  const stints = deriveStints(strategy, totalLaps);

  return (
    <div className="flex items-center gap-2 group/row">
      <span className="w-7 text-right text-[10px] text-zinc-600 shrink-0">
        {position != null ? `P${position}` : ""}
      </span>
      <span
        className={[
          "w-9 text-[12px] font-bold shrink-0 tracking-wider",
          isEditing ? "text-red-400" : "text-zinc-300",
        ].join(" ")}
      >
        {strategy.driver}
      </span>
      {/* Timeline bar */}
      <div className="relative flex-1 h-6 bg-zinc-800 rounded overflow-hidden">
        {stints.map((stint, i) => {
          const leftPct = ((stint.startLap - 1) / totalLaps) * 100;
          const widthPct = ((stint.endLap - stint.startLap + 1) / totalLaps) * 100;
          return (
            <div
              key={i}
              className="absolute top-0 h-full flex items-center justify-center overflow-hidden"
              style={{
                left: `${leftPct}%`,
                width: `${widthPct}%`,
                backgroundColor: COMPOUND_COLOR[stint.compound] ?? "#52525b",
              }}
              title={`${stint.compound}: Laps ${stint.startLap}–${stint.endLap}`}
            >
              {widthPct > 5 && (
                <span className="text-[9px] font-bold text-black/50 select-none">
                  {COMPOUND_LABEL[stint.compound]}
                </span>
              )}
            </div>
          );
        })}
        {strategy.pit_stops.map((pit, i) => (
          <div
            key={i}
            className="absolute top-0 h-full w-px bg-black/50 z-10 pointer-events-none"
            style={{ left: `${(pit.lap / totalLaps) * 100}%` }}
            title={`Pit lap ${pit.lap} → ${pit.compound}`}
          />
        ))}
      </div>
      {/* Edit button */}
      <button
        onClick={onEdit}
        className="w-10 text-[10px] text-zinc-700 hover:text-zinc-300 transition-colors shrink-0 text-right opacity-0 group-hover/row:opacity-100 focus:opacity-100"
        title={`Edit ${strategy.driver}'s strategy`}
      >
        Edit
      </button>
    </div>
  );
}

// ─── Editable car row ─────────────────────────────────────────────────────────

interface EditableRowProps {
  strategy: CarStrategySchema;
  totalLaps: number;
  position: number | undefined;
  onStrategyChange: (updated: CarStrategySchema) => void;
}

function EditableCarRow({ strategy, totalLaps, position, onStrategyChange }: EditableRowProps) {
  const barRef = useRef<HTMLDivElement | null>(null);
  const stints = deriveStints(strategy, totalLaps);
  const sortedPits = [...strategy.pit_stops].sort((a, b) => a.lap - b.lap);

  const handlePitMove = (sortedIdx: number, newLap: number) => {
    const updated = sortedPits.map((p, i) =>
      i === sortedIdx ? { ...p, lap: newLap } : p,
    );
    onStrategyChange({ ...strategy, pit_stops: updated });
  };

  return (
    <div className="flex items-center gap-2">
      <span className="w-7 text-right text-[10px] text-zinc-600 shrink-0">
        {position != null ? `P${position}` : ""}
      </span>
      <span className="w-9 text-[12px] font-bold shrink-0 tracking-wider text-red-400">
        {strategy.driver}
      </span>
      {/* Bar — overflow-visible so markers can extend slightly */}
      <div className="relative flex-1 h-7" ref={barRef}>
        {/* Stint bars — clipped to bar bounds */}
        <div className="absolute inset-0 rounded overflow-hidden ring-1 ring-red-500/30">
          {stints.map((stint, i) => {
            const leftPct = ((stint.startLap - 1) / totalLaps) * 100;
            const widthPct = ((stint.endLap - stint.startLap + 1) / totalLaps) * 100;
            return (
              <div
                key={i}
                className="absolute top-0 h-full flex items-center justify-center overflow-hidden"
                style={{
                  left: `${leftPct}%`,
                  width: `${widthPct}%`,
                  backgroundColor: COMPOUND_COLOR[stint.compound] ?? "#52525b",
                }}
              >
                {widthPct > 5 && (
                  <span className="text-[9px] font-bold text-black/50 select-none">
                    {COMPOUND_LABEL[stint.compound]}
                  </span>
                )}
              </div>
            );
          })}
        </div>
        {/* Draggable markers — on top, overflow-visible */}
        {sortedPits.map((pit, i) => (
          <PitMarker
            key={i}
            sortedIdx={i}
            lap={pit.lap}
            totalLaps={totalLaps}
            sortedPits={sortedPits}
            barRef={barRef}
            onMove={handlePitMove}
          />
        ))}
      </div>
      {/* Stop count */}
      <span className="w-10 text-[10px] text-zinc-600 shrink-0">
        {strategy.pit_stops.length}{" "}
        {strategy.pit_stops.length === 1 ? "stop" : "stops"}
      </span>
    </div>
  );
}

// ─── Lap axis ─────────────────────────────────────────────────────────────────

function LapAxis({ totalLaps }: { totalLaps: number }) {
  const step = totalLaps > 60 ? 10 : 5;
  const ticks: number[] = [];
  for (let t = step; t < totalLaps; t += step) ticks.push(t);

  return (
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
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

interface Props {
  strategies: CarStrategySchema[];
  totalLaps: number;
  snapshots: LapSnapshotSchema[];
  editingDriver: string | null;
  onEditDriver: (driver: string | null) => void;
  onStrategyChange: (updated: CarStrategySchema) => void;
}

export function StintTimeline({
  strategies,
  totalLaps,
  snapshots,
  editingDriver,
  onEditDriver,
  onStrategyChange,
}: Props) {
  // Build finishing-position map from the last simulated lap
  const positions = new Map<string, number>();
  for (const s of snapshots) {
    if (s.lap === totalLaps) positions.set(s.driver, s.position);
  }

  const sorted = [...strategies].sort(
    (a, b) =>
      (positions.get(a.driver) ?? 99) - (positions.get(b.driver) ?? 99),
  );

  return (
    <section className="bg-zinc-900 border border-zinc-700 rounded p-4">
      {/* Header + legend */}
      <div className="flex items-center justify-between mb-3 gap-4 flex-wrap">
        <h2 className="text-xs uppercase tracking-widest text-zinc-400">
          Race Strategy
        </h2>
        <div className="flex items-center gap-4 text-xs text-zinc-500">
          {(["SOFT", "MEDIUM", "HARD"] as const).map((c) => (
            <span key={c} className="flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-3 rounded-[2px]"
                style={{ backgroundColor: COMPOUND_COLOR[c] }}
              />
              {c}
            </span>
          ))}
        </div>
      </div>

      {/* Lap axis */}
      <div className="flex mb-1 ml-[88px] mr-[52px]">
        <LapAxis totalLaps={totalLaps} />
      </div>

      {/* Car rows */}
      <div className="space-y-[3px] max-h-[560px] overflow-y-auto pr-1">
        {sorted.map((strategy) => {
          const isEditing = strategy.driver === editingDriver;

          if (isEditing) {
            return (
              <div key={strategy.driver}>
                <EditableCarRow
                  strategy={strategy}
                  totalLaps={totalLaps}
                  position={positions.get(strategy.driver)}
                  onStrategyChange={onStrategyChange}
                />
                <StrategyEditor
                  strategy={strategy}
                  totalLaps={totalLaps}
                  onChange={onStrategyChange}
                  onClose={() => onEditDriver(null)}
                />
              </div>
            );
          }

          return (
            <StaticCarRow
              key={strategy.driver}
              strategy={strategy}
              totalLaps={totalLaps}
              position={positions.get(strategy.driver)}
              isEditing={false}
              onEdit={() => onEditDriver(strategy.driver)}
            />
          );
        })}
      </div>

      {!editingDriver && (
        <p className="mt-3 text-[10px] text-zinc-700">
          Hover a row and click Edit to modify a driver's pit strategy.
        </p>
      )}
    </section>
  );
}
