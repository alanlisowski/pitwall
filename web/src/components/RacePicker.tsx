import type { RaceSummary } from "../api/types";

interface Props {
  races: RaceSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

export function RacePicker({ races, selectedId, onSelect }: Props) {
  return (
    <div className="flex items-center gap-3">
      <label className="text-xs uppercase tracking-widest text-zinc-500">
        Race
      </label>
      <select
        className="bg-zinc-800 border border-zinc-700 text-zinc-100 text-sm rounded px-3 py-1.5 focus:outline-none focus:border-zinc-500 cursor-pointer"
        value={selectedId ?? ""}
        onChange={(e) => {
          const v = e.target.value;
          if (v) onSelect(parseInt(v, 10));
        }}
      >
        <option value="">— select a race —</option>
        {races.map((r) => (
          <option key={r.id} value={r.id}>
            {r.year} · {r.gp_name}
          </option>
        ))}
      </select>
      {races.length === 0 && (
        <span className="text-xs text-zinc-600">
          (start the API server to load races)
        </span>
      )}
    </div>
  );
}
