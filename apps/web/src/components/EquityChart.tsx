"use client";

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
import type { EquityCurvePoint } from "@/lib/types";
import { formatMoney, formatPct } from "@/lib/format";

interface EquityChartProps {
  data: EquityCurvePoint[];
}

function yFormatter(v: number) {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card border-slate-200 p-3 text-xs shadow-lg min-w-[180px]">
      <p className="mb-2 font-semibold text-slate-700">{label}</p>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      {payload.map((entry: any) => (
        <div key={entry.dataKey} className="flex justify-between gap-6">
          <span style={{ color: entry.color }}>{entry.name}</span>
          <span className="font-mono text-slate-900">
            {formatMoney(entry.value)}
          </span>
        </div>
      ))}
      {payload[0]?.payload?.returnPct !== null && (
        <p className="mt-1.5 border-t border-slate-100 pt-1.5 text-slate-400">
          Return: {formatPct(payload[0].payload.returnPct)}
        </p>
      )}
    </div>
  );
}

export function EquityChart({ data }: EquityChartProps) {
  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart
        data={data}
        margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#64748b" }}
          tickLine={false}
        />
        <YAxis
          tickFormatter={yFormatter}
          tick={{ fontSize: 11, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
          width={60}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          iconType="plainline"
        />
        <Line
          type="monotone"
          dataKey="totalEquity"
          name="Total Equity"
          stroke="#6366f1"
          strokeWidth={2.5}
          dot={false}
          activeDot={{ r: 4 }}
        />
        <Line
          type="monotone"
          dataKey="marketValue"
          name="Market Value"
          stroke="#f59e0b"
          strokeWidth={1.5}
          strokeDasharray="6 3"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="cash"
          name="Cash"
          stroke="#94a3b8"
          strokeWidth={1.5}
          strokeDasharray="3 3"
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
