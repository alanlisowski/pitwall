import { useCallback, useEffect, useRef, useState } from "react";
import { advanceRace, startRace } from "../api/client";
import type {
  BaselineResponse,
  Difficulty,
  PaceSetting,
  RaceStateSchema,
} from "../api/types";

// ─── Constants ────────────────────────────────────────────────────────────────

const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#ef4444",
  MEDIUM: "#eab308",
  HARD: "#f4f4f5",
};
const COMPOUND_LABEL: Record<string, string> = { SOFT: "S", MEDIUM: "M", HARD: "H" };
const MAX_TYRE_AGE: Record<string, number> = { SOFT: 22, MEDIUM: 35, HARD: 55 };

const PACE_OPTIONS: PaceSetting[] = [
  "PUSH_HARD",
  "PUSH",
  "NEUTRAL",
  "CONSERVE",
  "CONSERVE_HARD",
];
const PACE_ABBREV: Record<PaceSetting, string> = {
  PUSH_HARD: "PH",
  PUSH: "P",
  NEUTRAL: "N",
  CONSERVE: "C",
  CONSERVE_HARD: "CH",
};
const PACE_ACTIVE: Record<PaceSetting, string> = {
  PUSH_HARD: "bg-red-950 border-red-700 text-red-300",
  PUSH: "bg-orange-950 border-orange-700 text-orange-300",
  NEUTRAL: "bg-zinc-700 border-zinc-500 text-zinc-200",
  CONSERVE: "bg-sky-950 border-sky-700 text-sky-300",
  CONSERVE_HARD: "bg-blue-950 border-blue-700 text-blue-300",
};
const PACE_IDLE = "bg-zinc-800 border-zinc-700 text-zinc-600 hover:text-zinc-400";

type Phase = "setup" | "racing" | "finished";
type Speed = 1 | 4;

// ─── DriverPicker ─────────────────────────────────────────────────────────────

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
                "py-2 px-1 rounded text-xs font-bold tracking-wider transition-all border",
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
                "px-4 py-1.5 rounded text-xs font-bold uppercase tracking-widest border transition-all",
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
          "px-8 py-2.5 rounded font-bold text-sm tracking-[0.2em] uppercase transition-all",
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

// ─── TyreBar ──────────────────────────────────────────────────────────────────

function TyreBar({ compound, tyreAge }: { compound: string; tyreAge: number }) {
  const max = MAX_TYRE_AGE[compound] ?? 30;
  const grip = Math.max(0, 1 - tyreAge / max);
  const color = COMPOUND_COLOR[compound] ?? "#52525b";
  const label = COMPOUND_LABEL[compound] ?? "?";
  const critical = grip < 0.25;

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          Tyre Life
        </span>
        <span className="text-[10px] text-zinc-500">
          <span style={{ color }} className="font-bold">
            {label}
          </span>{" "}
          · {Math.round(tyreAge)} laps
        </span>
      </div>
      <div className="relative h-3 bg-zinc-800 rounded overflow-hidden">
        <div
          className="absolute left-0 top-0 h-full rounded transition-all duration-300"
          style={{ width: `${grip * 100}%`, backgroundColor: color }}
        />
        {critical && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="text-[9px] text-red-200 font-bold tracking-widest animate-pulse">
              CLIFF
            </span>
          </div>
        )}
      </div>
      <div className="flex justify-between text-[9px] text-zinc-700">
        <span>WORN</span>
        <span>FRESH</span>
      </div>
    </div>
  );
}

// ─── PaceDial ─────────────────────────────────────────────────────────────────

function PaceDial({
  pace,
  onChange,
}: {
  pace: PaceSetting;
  onChange: (p: PaceSetting) => void;
}) {
  return (
    <div className="space-y-1.5">
      <span className="text-[10px] uppercase tracking-widest text-zinc-500">
        Pace Dial
      </span>
      <div className="flex gap-1">
        {PACE_OPTIONS.map((p) => (
          <button
            key={p}
            onClick={() => onChange(p)}
            title={p.replace(/_/g, " ")}
            className={[
              "flex-1 py-1.5 rounded text-[10px] font-bold tracking-wider transition-all border",
              pace === p ? PACE_ACTIVE[p] : PACE_IDLE,
            ].join(" ")}
          >
            {PACE_ABBREV[p]}
          </button>
        ))}
      </div>
      <p className="text-[9px] text-zinc-700 text-center">
        {pace.replace(/_/g, " ")}
      </p>
    </div>
  );
}

// ─── EventBanner ──────────────────────────────────────────────────────────────

function EventBanner({ events }: { events: RaceStateSchema["events"] }) {
  if (events.length === 0) return null;
  return (
    <div className="space-y-1">
      {events.map((e, i) => (
        <div
          key={i}
          className={[
            "px-3 py-1.5 rounded text-[11px] font-bold tracking-wider flex items-center gap-2",
            e.kind === "SAFETY_CAR"
              ? "bg-yellow-950 border border-yellow-700 text-yellow-300"
              : e.kind === "SC_END"
                ? "bg-zinc-900 border border-zinc-700 text-zinc-400"
                : "bg-zinc-900 border border-zinc-700 text-zinc-300",
          ].join(" ")}
        >
          {e.kind === "SAFETY_CAR" && (
            <span className="text-yellow-400">⚠</span>
          )}
          LAP {e.lap} · {e.kind.replace(/_/g, " ")} · {e.driver}
        </div>
      ))}
    </div>
  );
}

// ─── LiveGrid ─────────────────────────────────────────────────────────────────

function LiveGrid({
  cars,
  playerId,
}: {
  cars: RaceStateSchema["cars"];
  playerId: string;
}) {
  const sorted = [...cars].sort((a, b) => a.position - b.position);

  return (
    <div className="space-y-[2px]">
      {sorted.map((car) => {
        const isPlayer = car.driver === playerId;
        return (
          <div
            key={car.driver}
            className={[
              "flex items-center gap-2 px-2 py-[5px] rounded text-xs",
              isPlayer
                ? "bg-red-950/30 border border-red-900/50 text-zinc-100"
                : "bg-zinc-900/60 text-zinc-500",
            ].join(" ")}
          >
            <span className="w-6 text-right shrink-0 text-zinc-700 text-[10px]">
              P{car.position}
            </span>
            <span
              className={[
                "w-9 font-bold tracking-wider shrink-0 text-[11px]",
                isPlayer ? "text-red-400" : "text-zinc-400",
              ].join(" ")}
            >
              {car.driver}
            </span>
            <span className="w-16 text-right shrink-0 font-mono text-[10px]">
              {car.gap_to_leader === 0
                ? "LEADER"
                : `+${car.gap_to_leader.toFixed(1)}s`}
            </span>
            <span
              className="w-4 text-center text-[10px] font-bold shrink-0"
              style={{ color: COMPOUND_COLOR[car.compound] ?? "#fff" }}
            >
              {COMPOUND_LABEL[car.compound] ?? "?"}
            </span>
            <span className="text-[10px] text-zinc-700 shrink-0">
              {Math.round(car.tyre_age)}L
            </span>
            {isPlayer && car.pace_setting !== "NEUTRAL" && (
              <span
                className={[
                  "text-[9px] font-bold ml-auto tracking-wider",
                  car.pace_setting === "PUSH_HARD" ||
                  car.pace_setting === "PUSH"
                    ? "text-red-400"
                    : "text-sky-400",
                ].join(" ")}
              >
                {PACE_ABBREV[car.pace_setting]}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── PlayerStintBar ───────────────────────────────────────────────────────────

interface Stint {
  startLap: number;
  endLap: number;
  compound: string;
}

function buildPlayerStints(
  history: RaceStateSchema[],
  playerId: string,
  displayIdx: number,
): Stint[] {
  if (history.length === 0) return [];
  const stints: Stint[] = [];
  let stintStart = 1;
  let stintCompound =
    history[0].cars.find((c) => c.driver === playerId)?.compound ?? "SOFT";

  for (let i = 0; i <= displayIdx && i < history.length; i++) {
    const car = history[i].cars.find((c) => c.driver === playerId);
    if (!car) continue;
    if (car.pitted_this_lap && history[i].lap > stintStart) {
      stints.push({
        startLap: stintStart,
        endLap: history[i].lap - 1,
        compound: stintCompound,
      });
      stintStart = history[i].lap;
      stintCompound = car.compound;
    }
  }
  const currentLap = history[Math.min(displayIdx, history.length - 1)]?.lap ?? 1;
  stints.push({ startLap: stintStart, endLap: currentLap, compound: stintCompound });
  return stints;
}

function PlayerStintBar({
  history,
  playerId,
  displayIdx,
  totalLaps,
}: {
  history: RaceStateSchema[];
  playerId: string;
  displayIdx: number;
  totalLaps: number;
}) {
  const stints = buildPlayerStints(history, playerId, displayIdx);
  const currentLap = history[Math.min(displayIdx, history.length - 1)]?.lap ?? 0;
  const cursorPct = (currentLap / totalLaps) * 100;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-zinc-500">
          Stints
        </span>
        <span className="text-[10px] text-zinc-600">
          Lap {currentLap} / {totalLaps}
        </span>
      </div>
      <div className="relative h-5 bg-zinc-800 rounded overflow-hidden">
        {stints.map((stint, i) => {
          const leftPct = ((stint.startLap - 1) / totalLaps) * 100;
          const widthPct = ((stint.endLap - stint.startLap + 1) / totalLaps) * 100;
          return (
            <div
              key={i}
              className="absolute top-0 h-full"
              style={{
                left: `${leftPct}%`,
                width: `${widthPct}%`,
                backgroundColor: COMPOUND_COLOR[stint.compound] ?? "#52525b",
                opacity: 0.85,
              }}
              title={`${stint.compound}: Laps ${stint.startLap}–${stint.endLap}`}
            />
          );
        })}
        {/* Future laps overlay */}
        <div
          className="absolute top-0 h-full bg-zinc-900/70 pointer-events-none"
          style={{ left: `${cursorPct}%`, right: 0 }}
        />
        {/* Current lap cursor */}
        <div
          className="absolute top-0 h-full w-px bg-white/70 z-10 pointer-events-none"
          style={{ left: `${cursorPct}%` }}
        />
      </div>
    </div>
  );
}

// ─── GapPanel ─────────────────────────────────────────────────────────────────

function GapPanel({
  cars,
  playerId,
}: {
  cars: RaceStateSchema["cars"];
  playerId: string;
}) {
  const sorted = [...cars].sort((a, b) => a.position - b.position);
  const playerCar = sorted.find((c) => c.driver === playerId);
  const playerIdx = sorted.findIndex((c) => c.driver === playerId);
  const carAhead = playerIdx > 0 ? sorted[playerIdx - 1] : null;
  const carBehind =
    playerIdx < sorted.length - 1 ? sorted[playerIdx + 1] : null;

  if (!playerCar) return null;

  const gapAhead = carAhead
    ? playerCar.gap_to_leader - carAhead.gap_to_leader
    : null;
  const gapBehind = carBehind
    ? carBehind.gap_to_leader - playerCar.gap_to_leader
    : null;

  return (
    <div className="space-y-1">
      <span className="text-[10px] uppercase tracking-widest text-zinc-500">
        Gaps
      </span>
      <div className="grid grid-cols-2 gap-2 text-center">
        <div className="bg-zinc-800/60 rounded px-2 py-2">
          <p className="text-[9px] text-zinc-600 uppercase tracking-widest mb-0.5">
            Ahead
          </p>
          <p className="text-sm font-bold text-zinc-200 font-mono">
            {gapAhead !== null
              ? `+${gapAhead.toFixed(1)}s`
              : <span className="text-yellow-400 text-xs">LEAD</span>}
          </p>
          {carAhead && (
            <p className="text-[9px] text-zinc-600 mt-0.5">{carAhead.driver}</p>
          )}
        </div>
        <div className="bg-zinc-800/60 rounded px-2 py-2">
          <p className="text-[9px] text-zinc-600 uppercase tracking-widest mb-0.5">
            Behind
          </p>
          <p className="text-sm font-bold text-zinc-200 font-mono">
            {gapBehind !== null ? `+${gapBehind.toFixed(1)}s` : "—"}
          </p>
          {carBehind && (
            <p className="text-[9px] text-zinc-600 mt-0.5">{carBehind.driver}</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── TransportControls ────────────────────────────────────────────────────────

interface TransportProps {
  playing: boolean;
  advancing: boolean;
  speed: Speed;
  finished: boolean;
  onPlayPause: () => void;
  onSkip: () => void;
  onSpeedToggle: () => void;
}

function TransportControls({
  playing,
  advancing,
  speed,
  finished,
  onPlayPause,
  onSkip,
  onSpeedToggle,
}: TransportProps) {
  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onSkip}
        disabled={advancing || finished}
        className="px-3 py-1.5 rounded text-[11px] font-bold tracking-wider border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
      >
        SKIP ▶▶
      </button>
      <button
        onClick={onPlayPause}
        disabled={finished}
        className={[
          "px-5 py-1.5 rounded text-[11px] font-bold tracking-wider transition-all",
          advancing
            ? "bg-zinc-800 text-zinc-500 cursor-wait"
            : playing
              ? "bg-zinc-700 border border-zinc-600 text-zinc-200 hover:bg-zinc-600"
              : "bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/30",
        ].join(" ")}
      >
        {advancing ? "···" : playing ? "⏸  PAUSE" : "▶  PLAY"}
      </button>
      <button
        onClick={onSpeedToggle}
        className="px-3 py-1.5 rounded text-[11px] font-bold tracking-wider border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200 transition-all w-10 text-center"
      >
        {speed}x
      </button>
    </div>
  );
}

// ─── FinishedScreen ───────────────────────────────────────────────────────────

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
        <p className="text-3xl font-bold tracking-[0.2em] text-zinc-100">
          P{playerCar?.position ?? "?"}
        </p>
        <p className="text-sm text-zinc-400 mt-1">
          {playerCar?.gap_to_leader === 0
            ? "RACE WINNER 🏆"
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
              <span className="w-5 text-zinc-600 text-[10px]">
                P{car.position}
              </span>
              <span
                className={[
                  "font-bold tracking-wider w-9",
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
        className="w-full px-6 py-2.5 rounded font-bold text-sm tracking-[0.2em] uppercase bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-zinc-500 text-zinc-200 transition-all"
      >
        NEW RACE
      </button>
    </div>
  );
}

// ─── RaceEngineerScreen ───────────────────────────────────────────────────────

interface Props {
  baseline: BaselineResponse;
  onBack: () => void;
}

export function RaceEngineerScreen({ baseline, onBack }: Props) {
  const [phase, setPhase] = useState<Phase>("setup");
  const [selectedDriver, setSelectedDriver] = useState<string | null>(null);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [sessionId, setSessionId] = useState("");
  const [history, setHistory] = useState<RaceStateSchema[]>([]);
  const [displayIdx, setDisplayIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(1);
  const [pendingPace, setPendingPace] = useState<PaceSetting>("NEUTRAL");
  const [advancing, setAdvancing] = useState(false);
  const [raceError, setRaceError] = useState<string | null>(null);

  // Refs for use inside async callbacks / animation loop without stale closures
  const advancingRef = useRef(false);
  const sessionIdRef = useRef("");
  const pendingPaceRef = useRef<PaceSetting>("NEUTRAL");
  advancingRef.current = advancing;
  sessionIdRef.current = sessionId;
  pendingPaceRef.current = pendingPace;

  const handleStart = async () => {
    if (!selectedDriver) return;
    setStarting(true);
    setStartError(null);
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
    } catch (err) {
      setStartError((err as Error).message);
    } finally {
      setStarting(false);
    }
  };

  const doAdvance = useCallback(
    async (
      sid: string,
      pace: PaceSetting,
    ): Promise<RaceStateSchema | null> => {
      if (advancingRef.current) return null;
      advancingRef.current = true;
      setAdvancing(true);
      try {
        const state = await advanceRace(sid, { pace });
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
    const state = await doAdvance(
      sessionIdRef.current,
      pendingPaceRef.current,
    );
    if (state) {
      setDisplayIdx((d) => d + 1);
      if (state.finished) setPhase("finished");
    }
  }, [doAdvance]);

  // Animation loop — runs a single tick after `delay` ms whenever deps change
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

  // ── Setup phase ───────────────────────────────────────────────────────────

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

  // ── Finished phase ────────────────────────────────────────────────────────

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
            setRaceError(null);
          }}
        />
      </section>
    );
  }

  // ── Racing phase ──────────────────────────────────────────────────────────

  const currentState = history[displayIdx];
  if (!currentState) return null;

  const totalLaps = currentState.total_laps;
  const playerId = selectedDriver ?? "";

  return (
    <section className="bg-zinc-900 border border-zinc-700 rounded p-4 space-y-3">
      {/* Header bar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <div>
            <span className="text-[9px] text-zinc-600 uppercase tracking-widest">
              Lap
            </span>
            <p className="text-xl font-bold text-zinc-100 leading-none">
              {currentState.lap}
              <span className="text-zinc-600 text-sm font-normal">
                {" "}
                / {totalLaps}
              </span>
            </p>
          </div>

          <span className="px-2 py-0.5 bg-zinc-800 border border-zinc-700 text-red-400 text-[11px] font-bold tracking-wider rounded">
            {playerId}
          </span>

          {currentState.sc_active && (
            <span className="px-2 py-0.5 bg-yellow-900/60 border border-yellow-700 text-yellow-300 text-[10px] font-bold uppercase tracking-widest rounded animate-pulse">
              SC
            </span>
          )}
        </div>

        <button
          onClick={onBack}
          className="text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          ← Exit
        </button>
      </div>

      {/* Events */}
      {currentState.events.length > 0 && (
        <EventBanner events={currentState.events} />
      )}

      {raceError && (
        <div className="p-2 bg-red-950/40 border border-red-900 text-red-300 text-xs rounded">
          {raceError}
        </div>
      )}

      {/* Main layout: race order + player status panel */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_220px] gap-3">
        {/* Race order */}
        <div className="space-y-2">
          <h3 className="text-[10px] uppercase tracking-widest text-zinc-600">
            Race Order
          </h3>
          <LiveGrid cars={currentState.cars} playerId={playerId} />
        </div>

        {/* Player status panel */}
        <div className="space-y-3">
          <GapPanel cars={currentState.cars} playerId={playerId} />

          <div className="bg-zinc-800/40 rounded p-3">
            {(() => {
              const pc = currentState.cars.find((c) => c.driver === playerId);
              return pc ? (
                <TyreBar compound={pc.compound} tyreAge={pc.tyre_age} />
              ) : null;
            })()}
          </div>

          <div className="bg-zinc-800/40 rounded p-3">
            <PaceDial pace={pendingPace} onChange={setPendingPace} />
          </div>
        </div>
      </div>

      {/* Player stint bar */}
      <div className="bg-zinc-800/40 rounded p-3">
        <PlayerStintBar
          history={history}
          playerId={playerId}
          displayIdx={displayIdx}
          totalLaps={totalLaps}
        />
      </div>

      {/* Transport controls */}
      <div className="flex items-center justify-between flex-wrap gap-2 border-t border-zinc-800 pt-3">
        <TransportControls
          playing={playing}
          advancing={advancing}
          speed={speed}
          finished={phase === "finished"}
          onPlayPause={() => setPlaying((p) => !p)}
          onSkip={skipToNext}
          onSpeedToggle={() => setSpeed((s) => (s === 1 ? 4 : 1))}
        />
        <span className="text-[10px] text-zinc-700 font-mono">
          {history.length} states buffered
        </span>
      </div>
    </section>
  );
}
