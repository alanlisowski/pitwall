import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { advanceRace, fetchTrack, startRace } from "../api/client";
import type {
  BaselineResponse,
  CarStateSchema,
  Compound,
  Difficulty,
  PaceSetting,
  RaceStateSchema,
  SessionEventSchema,
} from "../api/types";

// ─── Constants ────────────────────────────────────────────────────────────────

const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#E10600",
  MEDIUM: "#EFC027",
  HARD: "#F0F0F0",
};
const COMPOUND_LABEL: Record<string, string> = { SOFT: "S", MEDIUM: "M", HARD: "H" };
const MAX_TYRE_AGE: Record<string, number> = { SOFT: 22, MEDIUM: 35, HARD: 55 };
const PACE_OPTIONS: PaceSetting[] = [
  "PUSH_HARD", "PUSH", "NEUTRAL", "CONSERVE", "CONSERVE_HARD",
];
const PACE_ABBREV: Record<PaceSetting, string> = {
  PUSH_HARD: "PH", PUSH: "P", NEUTRAL: "N", CONSERVE: "C", CONSERVE_HARD: "CH",
};
const F1_FONT = "'Chakra Petch', ui-monospace, monospace";
const DATA_FONT = "'Saira', ui-monospace, monospace";

const EV = {
  RIVAL_PITTED: "rival_pitted",
  TYRE_CLIFF_WARNING: "tyre_cliff_warning",
  SAFETY_CAR_DEPLOYED: "safety_car_deployed",
  SAFETY_CAR_CLEARED: "safety_car_cleared",
  RACE_FINISH: "race_finish",
} as const;

function formatEventLabel(
  event: SessionEventSchema,
  cars: RaceStateSchema["cars"],
): string {
  if (event.kind === EV.RIVAL_PITTED) {
    const compound = cars.find((c) => c.driver === event.driver)?.compound;
    const suffix = compound ? ` → ${compound}` : "";
    return `LAP ${event.lap} · ${event.driver} PITS${suffix}`;
  }
  if (event.kind === EV.TYRE_CLIFF_WARNING) {
    return `LAP ${event.lap} · TYRE CLIFF — BOX SOON`;
  }
  if (event.kind === EV.SAFETY_CAR_CLEARED) {
    return "SAFETY CAR ENDING";
  }
  return event.kind.replace(/_/g, " ").toUpperCase();
}

// ─── Track geometry ───────────────────────────────────────────────────────────

function buildSvgPath(pts: number[][]): string {
  if (pts.length < 2) return "";
  return pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0]},${p[1]}`).join(" ") + " Z";
}

function computeCumLengths(pts: number[][]): number[] {
  const out = [0];
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0], dy = pts[i][1] - pts[i - 1][1];
    out.push(out[i - 1] + Math.sqrt(dx * dx + dy * dy));
  }
  return out;
}

function ptAtFrac(pts: number[][], lens: number[], f: number): [number, number] {
  const total = lens[lens.length - 1];
  const tgt = (((f % 1) + 1) % 1) * total;
  let lo = 0, hi = lens.length - 1;
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1;
    if (lens[mid] <= tgt) lo = mid; else hi = mid;
  }
  const t = lens[hi] > lens[lo] ? (tgt - lens[lo]) / (lens[hi] - lens[lo]) : 0;
  return [
    pts[lo][0] + t * (pts[hi][0] - pts[lo][0]),
    pts[lo][1] + t * (pts[hi][1] - pts[lo][1]),
  ];
}

function carFraction(gap: number, lapTime: number, sc: boolean): number {
  // Under SC compress visual gap so dots bunch together
  const g = sc ? Math.min(gap * 0.12, lapTime * 0.3) : gap;
  return 1 - Math.min(g / Math.max(lapTime, 60), 0.98);
}

// ─── TyreChip ─────────────────────────────────────────────────────────────────

function TyreChip({ compound, age }: { compound: string; age: number }) {
  const color = COMPOUND_COLOR[compound] ?? "#52525b";
  const label = COMPOUND_LABEL[compound] ?? "?";
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className="w-[18px] h-[18px] rounded-full inline-flex items-center justify-center text-[8px] font-semibold shrink-0"
        style={{ backgroundColor: color, color: compound === "HARD" ? "#15151c" : "#fff" }}
      >
        {label}
      </span>
      <span className="text-[10px] tabular-nums" style={{ color: "#9ca3af", fontFamily: DATA_FONT }}>{Math.round(age)}</span>
    </span>
  );
}

// ─── StatusStrip ──────────────────────────────────────────────────────────────

function StatusStrip({
  lap,
  totalLaps,
  scActive,
  flDriver,
  flTime,
  onExit,
}: {
  lap: number;
  totalLaps: number;
  scActive: boolean;
  flDriver: string | null;
  flTime: number;
  onExit: () => void;
}) {
  return (
    <div className="shrink-0">
      {/* Header bar */}
      <div
        className="flex items-center px-4 py-2 gap-5"
        style={{ background: "#1d1d26", fontFamily: F1_FONT }}
      >
        {/* PITWALL logo lockup */}
        <div className="flex items-center gap-2 shrink-0">
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
          <span
            style={{
              fontStyle: "italic",
              fontWeight: 700,
              fontSize: 18,
              letterSpacing: "0.04em",
            }}
          >
            <span style={{ color: "#fff" }}>PIT</span>
            <span style={{ color: "#E10600" }}>WALL</span>
          </span>
        </div>

        <div className="flex-1" />

        {/* Lap counter */}
        <div className="flex items-baseline gap-1.5 shrink-0">
          <span
            style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.25em", color: "#6b7280" }}
          >
            LAP
          </span>
          <span
            className="tabular-nums"
            style={{ fontSize: 22, fontWeight: 600, color: "#ECE7DA", letterSpacing: "-0.02em" }}
          >
            {lap}
          </span>
          <span style={{ color: "#52525b", fontSize: 13 }}>/ {totalLaps}</span>
        </div>

        {/* Safety car badge */}
        {scActive && (
          <div
            className="flex items-center gap-1.5 px-3 py-0.5 animate-pulse shrink-0"
            style={{
              background: "#451a03",
              borderTop: "1px solid #92400e",
              borderBottom: "1px solid #92400e",
              clipPath: "polygon(8px 0, 100% 0, calc(100% - 8px) 100%, 0 100%)",
            }}
          >
            <span style={{ color: "#fbbf24", fontSize: 14 }}>⚠</span>
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.2em",
                color: "#fbbf24",
                textTransform: "uppercase",
              }}
            >
              Safety Car
            </span>
          </div>
        )}

        {/* Fastest lap */}
        {flDriver && (
          <div className="hidden sm:flex items-center gap-2 shrink-0">
            <span style={{ color: "#a855f7", fontSize: 12 }}>●</span>
            <span
              style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.25em", color: "#6b7280" }}
            >
              FL
            </span>
            <span style={{ fontSize: 11, fontWeight: 600, color: "#d8b4fe" }}>{flDriver}</span>
            <span
              className="tabular-nums"
              style={{ fontSize: 10, color: "#a855f7", fontFamily: DATA_FONT }}
            >
              {flTime.toFixed(3)}
            </span>
          </div>
        )}

        <button
          onClick={onExit}
          style={{
            fontSize: 9,
            textTransform: "uppercase",
            letterSpacing: "0.2em",
            color: "#3f3f46",
            fontFamily: F1_FONT,
            background: "none",
            border: "none",
            cursor: "pointer",
          }}
          className="hover:text-zinc-400 transition-colors shrink-0"
        >
          EXIT ✕
        </button>
      </div>

      {/* Kerb stripe */}
      <div
        style={{
          height: 3,
          background:
            "repeating-linear-gradient(135deg, #E10600 0px, #E10600 8px, #ffffff 8px, #ffffff 16px)",
        }}
      />
    </div>
  );
}

// ─── TimingTower ──────────────────────────────────────────────────────────────

function TimingRow({
  car,
  interval,
  isPlayer,
  colour,
  posChange,
  isFastest,
}: {
  car: CarStateSchema;
  interval: number | null;
  isPlayer: boolean;
  colour: string;
  posChange: number;
  isFastest: boolean;
}) {
  return (
    <div
      className="relative flex items-center gap-2 pl-[11px] pr-2 py-[5px] text-xs select-none"
      style={{
        fontFamily: F1_FONT,
        background: isPlayer ? "#252530" : isFastest ? "rgba(88,28,135,0.12)" : "#15151c",
      }}
    >
      {/* Team colour stripe — 5px for vivid readability */}
      <div
        className="absolute left-0 top-0 bottom-0"
        style={{ width: 5, backgroundColor: colour }}
      />

      {/* Position */}
      <span className="w-4 text-right text-[10px] shrink-0 tabular-nums" style={{ color: "#6b7280" }}>
        {car.position}
      </span>

      {/* Driver code — cream in Chakra Petch */}
      <span
        className="w-[30px] font-semibold tracking-wider text-[11px] shrink-0 uppercase"
        style={{ color: isPlayer ? "#ffffff" : isFastest ? "#c084fc" : "#ECE7DA" }}
      >
        {car.driver}
      </span>

      {/* Tyre chip */}
      <div className="shrink-0">
        <TyreChip compound={car.compound} age={car.tyre_age} />
      </div>

      {/* PIT badge */}
      {car.pitted_this_lap && (
        <span
          className="text-[8px] font-semibold tracking-wider shrink-0"
          style={{
            background: "#052e16",
            color: "#4ade80",
            padding: "1px 4px",
            clipPath: "polygon(3px 0, 100% 0, calc(100% - 3px) 100%, 0 100%)",
          }}
        >
          IN
        </span>
      )}

      {/* FL dot */}
      {isFastest && (
        <span className="shrink-0" style={{ color: "#a855f7", fontSize: 9 }}>●</span>
      )}

      {/* Interval */}
      <span className="ml-auto text-[10px] shrink-0 tabular-nums" style={{ fontFamily: DATA_FONT }}>
        {interval === null ? (
          <span style={{ color: "#ECE7DA", fontWeight: 600, letterSpacing: "0.1em" }}>LEAD</span>
        ) : (
          <span style={{ color: isPlayer ? "#ECE7DA" : "#71717a" }}>
            +{interval.toFixed(1)}
          </span>
        )}
      </span>

      {/* Position change arrow */}
      <span className="w-3 text-center text-[10px] shrink-0">
        {posChange > 0 ? (
          <span style={{ color: "#4ade80" }}>▲</span>
        ) : posChange < 0 ? (
          <span style={{ color: "#E10600" }}>▼</span>
        ) : null}
      </span>
    </div>
  );
}

function TimingTower({
  cars,
  playerId,
  teamColours,
  prevState,
  flDriver,
}: {
  cars: RaceStateSchema["cars"];
  playerId: string;
  teamColours: Map<string, string>;
  prevState: RaceStateSchema | null;
  flDriver: string | null;
}) {
  const sorted = useMemo(
    () => [...cars].sort((a, b) => a.position - b.position),
    [cars],
  );

  return (
    <div
      className="flex flex-col overflow-y-auto"
      style={{ width: 252, minWidth: 252, background: "#15151c", borderRight: "1px solid #2a2a38" }}
    >
      {/* Header */}
      <div
        className="px-4 py-1.5 shrink-0"
        style={{
          background: "#1d1d26",
          borderBottom: "1px solid #2a2a38",
          fontFamily: F1_FONT,
        }}
      >
        <span
          style={{
            fontSize: 9,
            textTransform: "uppercase",
            letterSpacing: "0.25em",
            color: "#6b7280",
            fontWeight: 600,
          }}
        >
          Timing Tower
        </span>
      </div>

      {/* Rows with 1px gap */}
      <div className="flex flex-col gap-px flex-1 overflow-y-auto">
        {sorted.map((car) => {
          const idx = sorted.indexOf(car);
          const ahead = idx > 0 ? sorted[idx - 1] : null;
          const interval = ahead
            ? car.gap_to_leader - ahead.gap_to_leader
            : null;
          const colour = teamColours.get(car.driver) ?? "#ffffff";
          const prevPos = prevState?.cars.find(
            (c) => c.driver === car.driver,
          )?.position;
          const posChange =
            prevPos !== undefined ? prevPos - car.position : 0;
          return (
            <TimingRow
              key={car.driver}
              car={car}
              interval={interval}
              isPlayer={car.driver === playerId}
              colour={colour}
              posChange={posChange}
              isFastest={car.driver === flDriver}
            />
          );
        })}
      </div>
    </div>
  );
}

// ─── TrackMap ─────────────────────────────────────────────────────────────────

function TrackMap({
  cars,
  trackPoints,
  teamColours,
  playerId,
  scActive,
}: {
  cars: RaceStateSchema["cars"];
  trackPoints: number[][];
  teamColours: Map<string, string>;
  playerId: string;
  scActive: boolean;
}) {
  const lens = useMemo(
    () => (trackPoints.length > 1 ? computeCumLengths(trackPoints) : []),
    [trackPoints],
  );
  const svgPath = useMemo(() => buildSvgPath(trackPoints), [trackPoints]);

  const bbox = useMemo(() => {
    if (trackPoints.length === 0)
      return { minX: 0, maxX: 1, minY: 0, maxY: 1 };
    const xs = trackPoints.map((p) => p[0]);
    const ys = trackPoints.map((p) => p[1]);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }, [trackPoints]);

  if (trackPoints.length < 3) {
    return (
      <div className="flex items-center justify-center h-full bg-zinc-950">
        <span
          className="text-zinc-700 text-[10px] uppercase tracking-[0.25em]"
          style={{ fontFamily: F1_FONT }}
        >
          No Track Data
        </span>
      </div>
    );
  }

  const span = Math.max(bbox.maxX - bbox.minX, bbox.maxY - bbox.minY);
  const pad = span * 0.09;
  const vbX = bbox.minX - pad;
  const vbY = bbox.minY - pad;
  const vbW = bbox.maxX - bbox.minX + pad * 2;
  const vbH = bbox.maxY - bbox.minY + pad * 2;
  const dotR = span * 0.022;

  const leader = cars.find((c) => c.position === 1);
  const leaderLT = leader?.current_lap_time ?? 90;

  // Render all cars, player last (on top)
  const sorted = useMemo(
    () =>
      [...cars].sort((a, b) =>
        a.driver === playerId ? 1 : b.driver === playerId ? -1 : 0,
      ),
    [cars, playerId],
  );

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-zinc-950 overflow-hidden">
      <span
        className="absolute top-2 left-3 text-[9px] uppercase tracking-[0.2em] text-zinc-700 z-10 pointer-events-none"
        style={{ fontFamily: F1_FONT }}
      >
        Live Track
      </span>

      <svg
        viewBox={`${vbX} ${vbY} ${vbW} ${vbH}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full h-full"
        style={{ maxWidth: "100%", maxHeight: "100%" }}
      >
        {/* Track kerb/border */}
        <path
          d={svgPath}
          fill="none"
          stroke="#3f3f46"
          strokeWidth={dotR * 3.2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* Track surface */}
        <path
          d={svgPath}
          fill="none"
          stroke="#18181b"
          strokeWidth={dotR * 1.8}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* Start/finish line marker */}
        {trackPoints.length > 0 && (
          <circle
            cx={trackPoints[0][0]}
            cy={trackPoints[0][1]}
            r={dotR * 1.1}
            fill="none"
            stroke="#52525b"
            strokeWidth={dotR * 0.5}
          />
        )}

        {/* Car dots */}
        {sorted.map((car) => {
          const frac = carFraction(car.gap_to_leader, leaderLT, scActive);
          const [x, y] = ptAtFrac(trackPoints, lens, frac);
          const colour = teamColours.get(car.driver) ?? "#ffffff";
          const isPlayer = car.driver === playerId;
          const r = isPlayer ? dotR * 1.6 : dotR;

          return (
            <g key={car.driver}>
              {/* Player glow ring */}
              {isPlayer && (
                <circle
                  cx={x}
                  cy={y}
                  r={r * 2.4}
                  fill={colour}
                  opacity={0.18}
                />
              )}
              <circle cx={x} cy={y} r={r} fill={colour} />
              {/* Player label */}
              {isPlayer && (
                <text
                  x={x}
                  y={y - r * 2.4}
                  textAnchor="middle"
                  fontSize={dotR * 1.6}
                  fill={colour}
                  fontFamily={F1_FONT}
                  fontWeight="900"
                >
                  {car.driver}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ─── RaceControlBanner ────────────────────────────────────────────────────────

function RaceControlBanner({
  scActive,
  events,
  pendingPit,
  onPitCompound,
  onCancelPit,
  cars,
}: {
  scActive: boolean;
  events: RaceStateSchema["events"];
  pendingPit: Compound | null;
  onPitCompound: (c: Compound) => void;
  onCancelPit: () => void;
  cars: RaceStateSchema["cars"];
}) {
  const [showCompoundPicker, setShowCompoundPicker] = useState(false);

  useEffect(() => {
    if (pendingPit === null) setShowCompoundPicker(false);
  }, [pendingPit]);

  const isSc = scActive;
  const relevantEvents = events.filter(
    (e) => e.kind !== EV.SAFETY_CAR_CLEARED && e.kind !== EV.RACE_FINISH,
  );
  const topEvent = relevantEvents[0] ?? null;
  const isTyreWarn = topEvent?.kind === EV.TYRE_CLIFF_WARNING;
  const isRivalPit = topEvent?.kind === EV.RIVAL_PITTED;

  const bannerBg = isSc
    ? "linear-gradient(90deg, #451a03 0%, #1c1917 100%)"
    : isTyreWarn
    ? "linear-gradient(90deg, #431407 0%, #1c1917 100%)"
    : isRivalPit
    ? "#101827"
    : "#0d0d0f";

  const borderColor = isSc
    ? "#92400e"
    : isTyreWarn
    ? "#9a3412"
    : isRivalPit
    ? "#1e3a5f"
    : "#27272a";

  const msgText = isSc
    ? "SAFETY CAR DEPLOYED"
    : topEvent
    ? formatEventLabel(topEvent, cars)
    : "RACE CONTROL";

  return (
    <div
      className="w-full flex items-center justify-between gap-4 px-5 py-2.5 shrink-0"
      style={{
        background: bannerBg,
        borderTop: `1px solid ${borderColor}`,
        borderBottom: `1px solid ${borderColor}`,
        fontFamily: F1_FONT,
      }}
    >
      {/* Left: race control message */}
      <div className="flex items-center gap-3 min-w-0">
        {isSc && (
          <span className="text-amber-400 text-lg shrink-0 animate-pulse">⚠</span>
        )}
        {isTyreWarn && !isSc && (
          <span className="text-orange-400 text-lg shrink-0 animate-pulse">⚠</span>
        )}
        <div className="min-w-0">
          <p
            className={[
              "text-[11px] font-semibold tracking-[0.12em] uppercase truncate",
              isSc
                ? "text-amber-300"
                : isTyreWarn
                ? "text-orange-300"
                : isRivalPit
                ? "text-sky-300"
                : "text-zinc-500",
            ].join(" ")}
          >
            {msgText}
          </p>
          {isSc && (
            <p className="hidden sm:block text-[9px] text-amber-800/80 uppercase tracking-widest mt-0.5">
              Pit window open — gaps compressing
            </p>
          )}
        </div>
      </div>

      {/* Right: pit controls — the single source of truth for BOX NOW */}
      <div className="flex items-center gap-2 shrink-0">
        {pendingPit ? (
          <>
            <span
              className="px-3 py-1.5 text-[10px] font-semibold tracking-wider text-emerald-300 border border-emerald-800"
              style={{
                background: "#052e16",
                clipPath: "polygon(6px 0, 100% 0, calc(100% - 6px) 100%, 0 100%)",
              }}
            >
              BOXING: {pendingPit}
            </span>
            <button
              onClick={onCancelPit}
              className="text-[9px] text-zinc-500 hover:text-zinc-300 px-2 py-1.5 border border-zinc-800 hover:border-zinc-600 transition-colors"
              style={{ clipPath: "polygon(3px 0, 100% 0, calc(100% - 3px) 100%, 0 100%)" }}
            >
              ✕ CANCEL
            </button>
          </>
        ) : showCompoundPicker ? (
          <div className="flex items-center gap-2">
            <span className="text-[9px] uppercase tracking-widest text-zinc-500 shrink-0">
              Box on:
            </span>
            {(["SOFT", "MEDIUM", "HARD"] as Compound[]).map((c) => (
              <button
                key={c}
                onClick={() => {
                  onPitCompound(c);
                  setShowCompoundPicker(false);
                }}
                className="w-7 h-7 rounded-full text-[9px] font-semibold transition-all hover:scale-110"
                style={{
                  backgroundColor: COMPOUND_COLOR[c],
                  color: c === "HARD" ? "#09090b" : "#fff",
                }}
              >
                {COMPOUND_LABEL[c]}
              </button>
            ))}
            <button
              onClick={() => setShowCompoundPicker(false)}
              className="text-[9px] text-zinc-600 hover:text-zinc-300 ml-1 transition-colors"
            >
              ✕
            </button>
          </div>
        ) : (
          <>
            <button
              onClick={() => setShowCompoundPicker(true)}
              className="px-4 py-1.5 text-[10px] font-semibold tracking-[0.12em] uppercase text-white transition-all hover:opacity-90 active:scale-95"
              style={{
                background: "linear-gradient(135deg, #15803d, #16a34a)",
                clipPath: "polygon(7px 0, 100% 0, calc(100% - 7px) 100%, 0 100%)",
              }}
            >
              BOX NOW ▼
            </button>
            <span
              className="px-4 py-1.5 text-[10px] font-semibold tracking-[0.12em] uppercase text-zinc-600 border border-zinc-800"
              style={{
                clipPath: "polygon(7px 0, 100% 0, calc(100% - 7px) 100%, 0 100%)",
              }}
            >
              STAY OUT
            </span>
          </>
        )}
      </div>
    </div>
  );
}

// ─── PaceDial + DriverLowerThird ─────────────────────────────────────────────

function PaceDial({
  pace,
  onChange,
}: {
  pace: PaceSetting;
  onChange: (p: PaceSetting) => void;
}) {
  const ACTIVE: Record<PaceSetting, string> = {
    PUSH_HARD: "text-red-300",
    PUSH: "text-orange-300",
    NEUTRAL: "text-zinc-200",
    CONSERVE: "text-sky-300",
    CONSERVE_HARD: "text-blue-300",
  };
  const ACTIVE_BG: Record<PaceSetting, string> = {
    PUSH_HARD: "#450a0a",
    PUSH: "#431407",
    NEUTRAL: "#3f3f46",
    CONSERVE: "#082f49",
    CONSERVE_HARD: "#0c1a6b",
  };
  return (
    <div className="flex gap-1">
      {PACE_OPTIONS.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          title={p.replace(/_/g, " ")}
          className={[
            "flex-1 py-2 text-[10px] font-semibold tracking-wider transition-all border",
            pace === p
              ? `${ACTIVE[p]} border-transparent`
              : "text-zinc-600 border-zinc-800 hover:text-zinc-400",
          ].join(" ")}
          style={{
            background: pace === p ? ACTIVE_BG[p] : "transparent",
            clipPath: "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)",
            fontFamily: F1_FONT,
          }}
        >
          {PACE_ABBREV[p]}
        </button>
      ))}
    </div>
  );
}

function DriverLowerThird({
  car,
  teamColour,
  fullName,
  team,
  pendingPace,
  onPaceChange,
  playing,
  advancing,
  speed,
  finished,
  onPlayPause,
  onSkip,
  onSpeedToggle,
}: {
  car: CarStateSchema;
  teamColour: string;
  fullName: string;
  team: string;
  pendingPace: PaceSetting;
  onPaceChange: (p: PaceSetting) => void;
  playing: boolean;
  advancing: boolean;
  speed: 1 | 4;
  finished: boolean;
  onPlayPause: () => void;
  onSkip: () => void;
  onSpeedToggle: () => void;
}) {
  const tyreLeft = Math.max(
    0,
    (MAX_TYRE_AGE[car.compound] ?? 30) - Math.round(car.tyre_age),
  );
  const gripPct = Math.max(
    0,
    100 * (1 - car.tyre_age / (MAX_TYRE_AGE[car.compound] ?? 30)),
  );

  return (
    <div
      className="bg-zinc-950 border-t border-zinc-800 shrink-0"
      style={{ fontFamily: F1_FONT }}
    >
      {/* Name bar */}
      <div className="flex items-stretch gap-0 overflow-hidden">
        {/* Team colour accent stripe */}
        <div className="w-1 shrink-0" style={{ backgroundColor: teamColour }} />

        {/* Driver identity block — slanted right edge */}
        <div
          className="flex items-center gap-3 px-4 py-2 shrink-0"
          style={{
            background: `linear-gradient(90deg, ${teamColour}22 0%, transparent 100%)`,
            clipPath: "polygon(0 0, calc(100% - 12px) 0, 100% 100%, 0 100%)",
            minWidth: 200,
          }}
        >
          {/* Position badge */}
          <div
            className="px-2 py-0.5 shrink-0"
            style={{
              backgroundColor: teamColour,
              clipPath: "polygon(5px 0, 100% 0, calc(100% - 5px) 100%, 0 100%)",
            }}
          >
            <span className="text-base font-semibold text-white tabular-nums">
              P{car.position}
            </span>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-white leading-none">
              {fullName || car.driver}
            </p>
            <p className="text-[9px] uppercase tracking-[0.2em] text-zinc-500 mt-0.5 leading-none">
              {team}
            </p>
          </div>
        </div>

        {/* Tyre info */}
        <div className="hidden sm:flex flex-col justify-center px-4 gap-1 border-l border-zinc-800">
          <div className="flex items-center gap-2">
            <TyreChip compound={car.compound} age={car.tyre_age} />
            <span className="text-[9px] text-zinc-600">{tyreLeft}L left</span>
          </div>
          {/* Grip bar */}
          <div className="w-24 h-1.5 bg-zinc-800 rounded overflow-hidden">
            <div
              className="h-full rounded transition-all duration-500"
              style={{
                width: `${gripPct}%`,
                backgroundColor: COMPOUND_COLOR[car.compound] ?? "#52525b",
              }}
            />
          </div>
        </div>
      </div>

      {/* Controls row — pace dial + transport */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-t border-zinc-900">
        {/* Pace dial */}
        <div className="flex-1" style={{ minWidth: 160, maxWidth: 260 }}>
          <PaceDial pace={pendingPace} onChange={onPaceChange} />
        </div>

        <div className="w-px h-5 bg-zinc-800 shrink-0" />

        {/* Transport */}
        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={onSkip}
            disabled={advancing || finished}
            className="px-2.5 py-2 text-[10px] text-zinc-600 border border-zinc-800 hover:border-zinc-600 hover:text-zinc-300 disabled:opacity-25 transition-all"
            style={{ clipPath: "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)" }}
          >
            ▶▶
          </button>
          <button
            onClick={onPlayPause}
            disabled={finished}
            className={[
              "px-5 py-2 text-[10px] font-semibold tracking-[0.12em] uppercase transition-all",
              advancing
                ? "text-zinc-600 cursor-wait"
                : playing
                  ? "text-zinc-200 border border-zinc-600 hover:border-zinc-400"
                  : "text-white bg-red-600 hover:bg-red-500",
            ].join(" ")}
            style={{
              background: advancing ? "#27272a" : playing ? "transparent" : undefined,
              clipPath: "polygon(7px 0, 100% 0, calc(100% - 7px) 100%, 0 100%)",
            }}
          >
            {advancing ? "···" : playing ? "⏸ PAUSE" : "▶ PLAY"}
          </button>
          <button
            onClick={onSpeedToggle}
            className="w-9 py-2 text-[10px] text-zinc-600 border border-zinc-800 hover:border-zinc-600 hover:text-zinc-300 text-center transition-all"
            style={{ clipPath: "polygon(4px 0, 100% 0, calc(100% - 4px) 100%, 0 100%)" }}
          >
            {speed}×
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Setup phase sub-components ───────────────────────────────────────────────

interface DriverPickerProps {
  strategies: BaselineResponse["strategies"];
  selectedDriver: string | null;
  difficulty: Difficulty;
  loading: boolean;
  onSelectDriver: (d: string) => void;
  onDifficulty: (d: Difficulty) => void;
  onStart: () => void;
}

function DriverPicker({
  strategies,
  selectedDriver,
  difficulty,
  loading,
  onSelectDriver,
  onDifficulty,
  onStart,
}: DriverPickerProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-3">
          Select Driver
        </h3>
        <div className="grid grid-cols-5 sm:grid-cols-8 md:grid-cols-10 gap-1.5">
          {strategies.map((s) => (
            <button
              key={s.driver}
              onClick={() => onSelectDriver(s.driver)}
              className={[
                "py-2 px-1 rounded text-xs font-semibold tracking-wider transition-all border",
                selectedDriver === s.driver
                  ? "bg-red-600 border-red-500 text-white shadow-lg shadow-red-900/30"
                  : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200",
              ].join(" ")}
            >
              {s.driver}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h3 className="text-[10px] uppercase tracking-widest text-zinc-500 mb-3">
          AI Difficulty
        </h3>
        <div className="flex gap-2">
          {(["easy", "medium", "hard"] as Difficulty[]).map((d) => (
            <button
              key={d}
              onClick={() => onDifficulty(d)}
              className={[
                "px-4 py-1.5 rounded text-xs font-semibold uppercase tracking-widest border transition-all",
                difficulty === d
                  ? "bg-zinc-100 text-zinc-900 border-zinc-100"
                  : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:border-zinc-500",
              ].join(" ")}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={onStart}
        disabled={!selectedDriver || loading}
        className={[
          "px-8 py-2.5 rounded font-semibold text-sm tracking-[0.2em] uppercase transition-all",
          !selectedDriver || loading
            ? "bg-zinc-800 text-zinc-600 cursor-not-allowed"
            : "bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/30",
        ].join(" ")}
      >
        {loading ? "STARTING…" : "▶  START RACE"}
      </button>
    </div>
  );
}

function FinishedScreen({
  state,
  playerId,
  onNewRace,
}: {
  state: RaceStateSchema;
  playerId: string;
  onNewRace: () => void;
}) {
  const sorted = [...state.cars].sort((a, b) => a.position - b.position);
  const playerCar = state.cars.find((c) => c.driver === playerId);

  return (
    <div className="space-y-6">
      <div className="text-center">
        <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-1">
          Race Complete
        </p>
        <p className="text-3xl font-semibold tracking-[0.2em] text-zinc-100">
          P{playerCar?.position ?? "?"}
        </p>
        <p className="text-sm text-zinc-400 mt-1">
          {playerCar?.gap_to_leader === 0
            ? "RACE WINNER"
            : `+${playerCar?.gap_to_leader.toFixed(1)}s to leader`}
        </p>
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-widest text-zinc-500 mb-2">
          Final Classification
        </p>
        <div className="space-y-[2px]">
          {sorted.map((car) => (
            <div
              key={car.driver}
              className={[
                "flex items-center gap-3 px-3 py-1.5 rounded text-xs",
                car.driver === playerId
                  ? "bg-red-950/30 border border-red-900/50"
                  : "bg-zinc-900",
              ].join(" ")}
            >
              <span className="w-5 text-zinc-600 text-[10px]">P{car.position}</span>
              <span
                className={[
                  "font-semibold tracking-wider w-9",
                  car.driver === playerId ? "text-red-400" : "text-zinc-300",
                ].join(" ")}
              >
                {car.driver}
              </span>
              <span className="text-zinc-500 ml-auto font-mono text-[10px]">
                {car.gap_to_leader === 0
                  ? "WINNER"
                  : `+${car.gap_to_leader.toFixed(1)}s`}
              </span>
            </div>
          ))}
        </div>
      </div>

      <button
        onClick={onNewRace}
        className="w-full px-6 py-2.5 rounded font-semibold text-sm tracking-[0.2em] uppercase bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-zinc-500 text-zinc-200 transition-all"
      >
        NEW RACE
      </button>
    </div>
  );
}

// ─── RaceEngineerScreen ───────────────────────────────────────────────────────

type Phase = "setup" | "racing" | "finished";
type Speed = 1 | 4;

interface Props {
  baseline: BaselineResponse;
  onBack: () => void;
}

export function RaceEngineerScreen({ baseline, onBack }: Props) {
  const [phase, setPhase] = useState<Phase>("setup");
  const [selectedDriver, setSelectedDriver] = useState<string | null>(null);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [starting, setStarting] = useState(false);
  const [startWaking, setStartWaking] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [sessionId, setSessionId] = useState("");
  const [history, setHistory] = useState<RaceStateSchema[]>([]);
  const [displayIdx, setDisplayIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const [pendingPace, setPendingPace] = useState<PaceSetting>("NEUTRAL");
  const [pendingPit, setPendingPit] = useState<Compound | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [raceError, setRaceError] = useState<string | null>(null);
  const [trackPoints, setTrackPoints] = useState<number[][]>([]);

  // Refs to avoid stale closures in async callbacks
  const advancingRef = useRef(false);
  const sessionIdRef = useRef("");
  const pendingPaceRef = useRef<PaceSetting>("NEUTRAL");
  const pendingPitRef = useRef<Compound | null>(null);
  advancingRef.current = advancing;
  sessionIdRef.current = sessionId;
  pendingPaceRef.current = pendingPace;
  pendingPitRef.current = pendingPit;

  // Build driver metadata maps from baseline
  const teamColours = useMemo(() => {
    const m = new Map<string, string>();
    for (const d of baseline.drivers) m.set(d.driver_code, d.team_colour);
    return m;
  }, [baseline.drivers]);

  const driverMeta = useMemo(() => {
    const m = new Map<string, { fullName: string; team: string }>();
    for (const d of baseline.drivers)
      m.set(d.driver_code, { fullName: d.full_name, team: d.team });
    return m;
  }, [baseline.drivers]);

  // Fetch track geometry once
  useEffect(() => {
    fetchTrack(baseline.race.id)
      .then((r) => setTrackPoints(r.points))
      .catch(() => {});
  }, [baseline.race.id]);

  // Track fastest lap across all history
  const fastestLap = useMemo(() => {
    let best: { driver: string; time: number } | null = null;
    for (const state of history) {
      for (const car of state.cars) {
        if (
          car.current_lap_time > 0 &&
          (!best || car.current_lap_time < best.time)
        ) {
          best = { driver: car.driver, time: car.current_lap_time };
        }
      }
    }
    return best;
  }, [history]);

  const handleStart = async () => {
    if (!selectedDriver) return;
    setStarting(true);
    setStartError(null);
    setStartWaking(false);

    let attempt = 0;
    const MAX_ATTEMPTS = 5;

    while (attempt < MAX_ATTEMPTS) {
      try {
        const resp = await startRace({
          race_id: baseline.race.id,
          driver_id: selectedDriver,
          difficulty,
          seed: 42,
        });
        setSessionId(resp.session_id);
        setHistory([resp.state]);
        setDisplayIdx(0);
        setPhase("racing");
        setStarting(false);
        setStartWaking(false);
        return;
      } catch (err) {
        attempt += 1;
        if (attempt < MAX_ATTEMPTS) {
          setStartWaking(true);
          await new Promise<void>((r) => setTimeout(r, 5000));
        } else {
          setStartError((err as Error).message);
        }
      }
    }

    setStarting(false);
    setStartWaking(false);
  };

  const doAdvance = useCallback(
    async (sid: string, pace: PaceSetting): Promise<RaceStateSchema | null> => {
      if (advancingRef.current) return null;
      advancingRef.current = true;
      setAdvancing(true);
      try {
        const state = await advanceRace(sid, {
          pace,
          pit_compound: pendingPitRef.current ?? undefined,
        });
        setPendingPit(null);
        pendingPitRef.current = null;
        setHistory((prev) => [...prev, state]);
        return state;
      } catch (err) {
        setRaceError((err as Error).message);
        setPlaying(false);
        return null;
      } finally {
        advancingRef.current = false;
        setAdvancing(false);
      }
    },
    [],
  );

  const skipToNext = useCallback(async () => {
    setPlaying(false);
    const state = await doAdvance(sessionIdRef.current, pendingPaceRef.current);
    if (state) {
      setDisplayIdx((d) => d + 1);
      if (state.finished) setPhase("finished");
    }
  }, [doAdvance]);

  // Animation loop
  useEffect(() => {
    if (!playing || phase !== "racing") return;
    const delay = speed === 4 ? 220 : 900;
    const id = setTimeout(async () => {
      if (displayIdx < history.length - 1) {
        setDisplayIdx((d) => d + 1);
      } else {
        const state = await doAdvance(
          sessionIdRef.current,
          pendingPaceRef.current,
        );
        if (state) {
          setDisplayIdx((d) => d + 1);
          if (state.finished) {
            setPhase("finished");
            setPlaying(false);
          } else if (state.events.length > 0) {
            setPlaying(false);
          }
        }
      }
    }, delay);
    return () => clearTimeout(id);
  }, [playing, phase, speed, displayIdx, history.length, doAdvance]);

  // ── Setup phase ─────────────────────────────────────────────────────────────

  if (phase === "setup") {
    return (
      <section className="bg-zinc-900 border border-zinc-700 rounded p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xs uppercase tracking-widest text-zinc-400">
              Race Engineer Mode
            </h2>
            <p className="text-[10px] text-zinc-600 mt-0.5">
              {baseline.race.gp_name} · {baseline.race.circuit} ·{" "}
              {baseline.race.total_laps} laps
            </p>
          </div>
          <button
            onClick={onBack}
            className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            ← Back
          </button>
        </div>

        {startError && (
          <div className="p-2 bg-red-950/40 border border-red-900 text-red-300 text-xs rounded">
            {startError}
          </div>
        )}

        {starting && startWaking && (
          <div className="flex items-center gap-2 text-zinc-400 text-xs">
            <span className="inline-block w-3 h-3 border-2 border-zinc-600 border-t-zinc-300 rounded-full animate-spin shrink-0" />
            Waking up the server… first load can take ~30s
          </div>
        )}

        <DriverPicker
          strategies={baseline.strategies}
          selectedDriver={selectedDriver}
          difficulty={difficulty}
          loading={starting}
          onSelectDriver={setSelectedDriver}
          onDifficulty={setDifficulty}
          onStart={handleStart}
        />
      </section>
    );
  }

  // ── Finished phase ───────────────────────────────────────────────────────────

  const lastState = history[history.length - 1];

  if (phase === "finished" && lastState) {
    return (
      <section className="bg-zinc-900 border border-zinc-700 rounded p-6">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-xs uppercase tracking-widest text-zinc-400">
            Race Engineer Mode
          </h2>
          <button
            onClick={onBack}
            className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            ← Back
          </button>
        </div>
        <FinishedScreen
          state={lastState}
          playerId={selectedDriver ?? ""}
          onNewRace={() => {
            setPhase("setup");
            setHistory([]);
            setDisplayIdx(0);
            setPlaying(false);
            setPendingPit(null);
            setRaceError(null);
          }}
        />
      </section>
    );
  }

  // ── Racing phase ─────────────────────────────────────────────────────────────

  const currentState = history[displayIdx];
  if (!currentState) return null;

  const playerId = selectedDriver ?? "";
  const playerCar = currentState.cars.find((c) => c.driver === playerId);
  const meta = driverMeta.get(playerId);
  const prevState = displayIdx > 0 ? history[displayIdx - 1] : null;

  const handlePitCompound = (c: Compound) => {
    setPendingPit(c);
    pendingPitRef.current = c;
  };

  return (
    <section
      className="flex flex-col rounded overflow-hidden"
      style={{ background: "#15151c", border: "1px solid #2a2a38", minHeight: 600 }}
    >
      {/* Status strip */}
      <StatusStrip
        lap={currentState.lap}
        totalLaps={currentState.total_laps}
        scActive={currentState.sc_active}
        flDriver={fastestLap?.driver ?? null}
        flTime={fastestLap?.time ?? 0}
        onExit={onBack}
      />

      {/* Main content: timing tower + track map */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 380 }}>
        <TimingTower
          cars={currentState.cars}
          playerId={playerId}
          teamColours={teamColours}
          prevState={prevState}
          flDriver={fastestLap?.driver ?? null}
        />
        <div className="flex-1 overflow-hidden">
          <TrackMap
            cars={currentState.cars}
            trackPoints={trackPoints}
            teamColours={teamColours}
            playerId={playerId}
            scActive={currentState.sc_active}
          />
        </div>
      </div>

      {/* Race control banner — always visible, single source of truth for pit decisions */}
      <RaceControlBanner
        scActive={currentState.sc_active}
        events={currentState.events}
        pendingPit={pendingPit}
        onPitCompound={handlePitCompound}
        onCancelPit={() => {
          setPendingPit(null);
          pendingPitRef.current = null;
        }}
        cars={currentState.cars}
      />

      {/* API error */}
      {raceError && (
        <div className="px-5 py-2 bg-red-950/40 border-t border-red-900 text-red-300 text-xs shrink-0">
          {raceError}
        </div>
      )}

      {/* Driver lower-third */}
      {playerCar && (
        <DriverLowerThird
          car={playerCar}
          teamColour={teamColours.get(playerId) ?? "#ef4444"}
          fullName={meta?.fullName ?? playerId}
          team={meta?.team ?? ""}
          pendingPace={pendingPace}
          onPaceChange={setPendingPace}
          playing={playing}
          advancing={advancing}
          speed={speed}
          finished={phase === "finished"}
          onPlayPause={() => setPlaying((p) => !p)}
          onSkip={skipToNext}
          onSpeedToggle={() => setSpeed((s) => (s === 1 ? 4 : 1))}
        />
      )}
    </section>
  );
}
