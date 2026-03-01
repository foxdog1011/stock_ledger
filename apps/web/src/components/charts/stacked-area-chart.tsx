"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { EquityCurvePoint } from "@/lib/types";
import { fmtMoney } from "@/lib/format";

interface Props {
  data: EquityCurvePoint[];
  freq?: string;
}

function xFmt(v: string, freq: string): string {
  if (!v) return "";
  if (freq === "D" || freq === "W") return v.slice(5).replace("-", "/");
  const [year, month] = v.split("-");
  const mon = new Date(+year, +month - 1).toLocaleString("en-US", { month: "short" });
  return `${mon} '${year.slice(2)}`;
}

function tickInterval(len: number): number {
  if (len <= 13) return 0;
  return Math.ceil(len / 6) - 1;
}

export function StackedAreaChart({ data, freq = "ME" }: Props) {
  if (!data.length)
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">No data</p>
    );

  const interval = tickInterval(data.length);

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
        <defs>
          <linearGradient id="gradCash" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.05} />
          </linearGradient>
          <linearGradient id="gradMv" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#10b981" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#10b981" stopOpacity={0.05} />
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
        <YAxis
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => fmtMoney(v, 0)}
          className="text-muted-foreground"
          width={72}
        />

        <Tooltip
          formatter={(v: number, name: string) => [`$${fmtMoney(v)}`, name]}
          labelFormatter={(l: string) => l}
        />
        <Legend iconSize={10} />

        <Area
          type="monotone"
          dataKey="cash"
          name="Cash"
          stackId="1"
          stroke="#3b82f6"
          fill="url(#gradCash)"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="marketValue"
          name="Market Value"
          stackId="1"
          stroke="#10b981"
          fill="url(#gradMv)"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
