"use client";

import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { fmtPct } from "@/lib/format";
import type { BenchmarkComparePoint } from "@/lib/types";

interface Props {
  data: BenchmarkComparePoint[];
  bench: string;
  freq: string;
}

function xFmt(date: string, freq: string): string {
  if (!date) return "";
  const d = new Date(date + "T00:00:00");
  if (freq === "ME" || freq === "QE" || freq === "YE") {
    return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  }
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit" });
}

export function BenchmarkCompareChart({ data, bench, freq }: Props) {
  if (!data.length) return null;

  const tickInterval = Math.max(0, Math.ceil(data.length / 6) - 1);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          dataKey="date"
          tickFormatter={(v) => xFmt(v as string, freq)}
          tick={{ fontSize: 11 }}
          interval={tickInterval}
        />
        <YAxis
          tickFormatter={(v: number) => `${v.toFixed(1)}%`}
          tick={{ fontSize: 11 }}
          width={56}
        />
        <Tooltip
          formatter={(v: unknown, name: string) => [
            typeof v === "number" ? fmtPct(v) : "—",
            name,
          ]}
          labelFormatter={(label: string) => label}
        />
        <Legend />
        <ReferenceLine
          y={0}
          stroke="hsl(var(--muted-foreground))"
          strokeDasharray="3 2"
          strokeOpacity={0.4}
        />
        <Line
          type="monotone"
          dataKey="portfolioCumReturnPct"
          name="Portfolio"
          stroke="hsl(var(--primary))"
          dot={false}
          strokeWidth={2}
        />
        <Line
          type="monotone"
          dataKey="benchCumReturnPct"
          name={bench}
          stroke="#f59e0b"
          dot={false}
          strokeWidth={2}
        />
        <Line
          type="monotone"
          dataKey="excessCumReturnPct"
          name="Excess"
          stroke="#10b981"
          dot={false}
          strokeWidth={1.5}
          strokeDasharray="4 2"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
