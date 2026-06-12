import type {
  BaselineResponse,
  CompareRequest,
  CompareResponse,
  RaceResultSchema,
  RaceSummary,
  SimulateRequest,
} from "./types";

const BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`GET ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function fetchRaces(): Promise<RaceSummary[]> {
  return get<RaceSummary[]>("/races");
}

export function fetchBaseline(raceId: number): Promise<BaselineResponse> {
  return get<BaselineResponse>(`/races/${raceId}/baseline`);
}

export function simulate(body: SimulateRequest): Promise<RaceResultSchema> {
  return post<RaceResultSchema>("/simulate", body);
}

export function compare(body: CompareRequest): Promise<CompareResponse> {
  return post<CompareResponse>("/compare", body);
}
