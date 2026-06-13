/** Mirrors the Pydantic schemas in engine/api/models.py exactly. */

export type Compound = "SOFT" | "MEDIUM" | "HARD";

export interface PitStopSchema {
  lap: number;
  compound: Compound;
}

export interface CarStrategySchema {
  driver: string;
  base_pace: number;
  start_compound: Compound;
  pit_stops: PitStopSchema[];
}

export interface SimConfigSchema {
  deg_soft: number;
  deg_medium: number;
  deg_hard: number;
  offset_soft: number;
  offset_medium: number;
  offset_hard: number;
  pit_loss: number;
  fuel_effect: number;
}

export interface RaceSummary {
  id: number;
  year: number;
  gp_name: string;
  gp_key: string;
  circuit: string;
  total_laps: number;
  session_type: string;
}

export interface LapSnapshotSchema {
  lap: number;
  driver: string;
  position: number;
  gap_to_leader: number;
  compound: string;
  tyre_age: number;
  lap_time: number;
  total_time: number;
  pitted: boolean;
}

export interface RaceResultSchema {
  snapshots: LapSnapshotSchema[];
  finishing_order: string[];
  total_times: Record<string, number>;
}

export interface BaselineResponse {
  race: RaceSummary;
  config: SimConfigSchema;
  strategies: CarStrategySchema[];
  result: RaceResultSchema;
}

export interface SimulateRequest {
  race_id: number;
  strategies: CarStrategySchema[];
  config?: SimConfigSchema;
}

export interface DriverDelta {
  driver: string;
  position_a: number;
  position_b: number;
  position_delta: number;
  time_a: number;
  time_b: number;
  time_delta: number;
}

export interface CompareRequest {
  race_id: number;
  strategy_a: CarStrategySchema[];
  strategy_b: CarStrategySchema[];
  config?: SimConfigSchema;
}

export interface CompareResponse {
  result_a: RaceResultSchema;
  result_b: RaceResultSchema;
  deltas: DriverDelta[];
}

// ---------------------------------------------------------------------------
// Race Engineer Mode
// ---------------------------------------------------------------------------

export type PaceSetting =
  | "PUSH_HARD"
  | "PUSH"
  | "NEUTRAL"
  | "CONSERVE"
  | "CONSERVE_HARD";

export type Difficulty = "easy" | "medium" | "hard";

export interface CarStateSchema {
  driver: string;
  position: number;
  gap_to_leader: number;
  compound: Compound;
  tyre_age: number;
  total_time: number;
  pace_setting: PaceSetting;
  pitted_this_lap: boolean;
}

export interface SessionEventSchema {
  lap: number;
  kind: string;
  driver: string;
}

export interface RaceStateSchema {
  lap: number;
  total_laps: number;
  cars: CarStateSchema[];
  events: SessionEventSchema[];
  finished: boolean;
  sc_active: boolean;
}

export interface StartRaceRequest {
  race_id: number;
  driver_id: string;
  difficulty: Difficulty;
  seed?: number;
}

export interface StartRaceResponse {
  session_id: string;
  state: RaceStateSchema;
}

export interface AdvanceRequest {
  pit_compound?: Compound | null;
  pace: PaceSetting;
}
