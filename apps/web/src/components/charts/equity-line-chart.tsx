"use client";

import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { EquityCurvePoint } from "@/lib/types";
import { fmtMoney } from "@/lib/format";

interface Props {
  data: EquityCurvePoint[];
  /** Pandas freq alias: "D" | "W" | "ME" | "QE" | "YE"  (default "ME") */
  freq?: string;
}

// ── helpers ─────────────────────────────────────────────────────────────────

function xFmt(v: string, freq: string): string {
  if (!v) return "";
  if (freq === "D" || freq === "W") {
    // "2024-01-15" → "01/15"
    return v.slice(5).replace("-", "/");
  }
  // "2024-01" → "Jan '24"
  const [year, month] = v.split("-");
  const mon = new Date(+year, +month - 1).toLocaleString("en-US", { month: "short" });
  return `${mon} '${year.slice(2)}`;
}

function tickInterval(len: number): number {
  if (len <= 13) return 0;            // show every tick
  return Math.ceil(len / 6) - 1;     // ~6 visible ticks
}

function pctFmt(v: number): string {
  if (v === null || v === undefined) return "";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

// ── component ────────────────────────────────────────────────────────────────

export function EquityLineChart({ data, freq = "ME" }: Props) {
  if (!data.length)
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">No data</p>
    );

  const interval = tickInterval(data.length);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 4, right: 56, left: 0, bottom: 4 }}>
        <defs>
          <linearGradient id="gradEquity" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="hsl(var(--primary))" stopOpacity={0.18} />
            <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
          </linearGradient>
        </defs>

        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />

        <XAxis
          dataKey="date"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: string) => xFmt(v, freq)}
          interval={interval}
          className="text-muted-foreground"
        />

        {/* Left axis — portfolio value */}
        <YAxis
          yAxisId="left"
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => fmtMoney(v, 0)}
          className="text-muted-foreground"
          width={72}
        />

        {/* Right axis — cumulative return % */}
        <YAxis
          yAxisId="right"
          orientation="right"
          tick={{ fontSize: 11 }}
          tickFormatter={pctFmt}
          className="text-muted-foreground"
          width={52}
        />

        <Tooltip
          formatter={(v: number, name: string) => {
            if (name === "Cum. Return")
              return [`${v >= 0 ? "+" : ""}${v?.toFixed(2)}%`, name];
            return [`$${fmtMoney(v)}`, name];
          }}
          labelFormatter={(l: string) => l}
        />
        <Legend verticalAlign="top" height={28} iconSize={10} />

        {/* Gradient area under total equity line */}
        <Area
          yAxisId="left"
          type="monotone"
          dataKey="totalEquity"
          name="Total Equity"
          stroke="hsl(var(--primary))"
          strokeWidth={2}
          fill="url(#gradEquity)"
          dot={false}
          activeDot={{ r: 4 }}
        />

        {/* Zero reference for return axis */}
        <ReferenceLine yAxisId="right" y={0} stroke="#888" strokeDasharray="4 2" />

        {/* Cumulative return % — dashed, on right axis */}
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="cumReturnPct"
          name="Cum. Return"
          stroke="#10b981"
          strokeWidth={1.5}
          strokeDasharray="5 3"
          dot={false}
          activeDot={{ r: 3 }}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
