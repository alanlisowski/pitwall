import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LapSnapshotSchema } from "../api/types";

const PALETTE = [
  "#3b82f6",
  "#22c55e",
  "#f97316",
  "#a855f7",
  "#06b6d4",
  "#ec4899",
  "#14b8a6",
  "#f43f5e",
  "#8b5cf6",
  "#84cc16",
  "#0ea5e9",
  "#fb923c",
  "#c084fc",
  "#67e8f9",
  "#fde047",
  "#f9a8d4",
  "#6ee7b7",
  "#fca5a5",
  "#93c5fd",
  "#86efac",
];

type ChartRow = Record<string, number>;

interface Props {
  title: string;
  snapshots: LapSnapshotSchema[];
  highlightDriver?: string;
}

export function GapChart({ title, snapshots, highlightDriver }: Props) {
  const drivers = [...new Set(snapshots.map((s) => s.driver))];
  const totalLaps = Math.max(...snapshots.map((s) => s.lap));

  const byLap = new Map<number, ChartRow>();
  for (const s of snapshots) {
    let row = byLap.get(s.lap);
    if (!row) {
      row = { lap: s.lap };
      byLap.set(s.lap, row);
    }
    row[s.driver] = parseFloat(s.gap_to_leader.toFixed(3));
  }

  const data: ChartRow[] = Array.from({ length: totalLaps }, (_, i) => {
    return byLap.get(i + 1) ?? { lap: i + 1 };
  });

  return (
    <section className="bg-zinc-900 border border-zinc-700 rounded p-4">
      <h2 className="text-xs uppercase tracking-widest text-zinc-400 mb-4">
        {title}
      </h2>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 4, right: 16, bottom: 24, left: 48 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c1c1f" />
          <XAxis
            dataKey="lap"
            stroke="#3f3f46"
            tick={{ fill: "#71717a", fontSize: 10 }}
            label={{
              value: "Lap",
              position: "insideBottom",
              offset: -14,
              fill: "#71717a",
              fontSize: 11,
            }}
          />
          <YAxis
            stroke="#3f3f46"
            tick={{ fill: "#71717a", fontSize: 10 }}
            tickFormatter={(v: number) => `${v.toFixed(0)}s`}
            label={{
              value: "Gap (s)",
              angle: -90,
              position: "insideLeft",
              offset: 12,
              fill: "#71717a",
              fontSize: 11,
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0c0c0f",
              border: "1px solid #27272a",
              borderRadius: 4,
              fontSize: 11,
              fontFamily: "monospace",
            }}
            labelStyle={{ color: "#a1a1aa", marginBottom: 4 }}
            labelFormatter={(lap) => `Lap ${lap}`}
            formatter={(val, name) => [
              `${Number(val).toFixed(2)} s`,
              String(name),
            ]}
            itemSorter={(item) => Number(item.value)}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, color: "#52525b", paddingTop: 8 }}
          />
          {drivers.map((driver, i) => {
            const isHighlight = driver === highlightDriver;
            return (
              <Line
                key={driver}
                type="monotone"
                dataKey={driver}
                stroke={
                  isHighlight
                    ? "#ef4444"
                    : PALETTE[i % PALETTE.length]
                }
                dot={false}
                strokeWidth={isHighlight ? 2.5 : 1}
                opacity={highlightDriver && !isHighlight ? 0.35 : 1}
                isAnimationActive={false}
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}
