"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { fmtMoney } from "@/lib/format";
import type { PositionDetail } from "@/lib/types";

interface Props {
  cash: number;
  positions?: Record<string, PositionDetail>;
}

const CASH_COLOR = "#3b82f6";
const STOCK_PALETTE = [
  "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#84cc16", "#f97316",
];

export function DonutChart({ cash, positions = {} }: Props) {
  // Build slices: cash first, then each symbol sorted by market value desc
  const stockSlices = Object.entries(positions)
    .filter(([, p]) => p.marketValue > 0)
    .sort(([, a], [, b]) => b.marketValue - a.marketValue)
    .map(([sym, p], i) => ({
      name: sym,
      value: p.marketValue,
      color: STOCK_PALETTE[i % STOCK_PALETTE.length],
    }));

  const data = [
    { name: "Cash", value: cash, color: CASH_COLOR },
    ...stockSlices,
  ];

  const total = data.reduce((s, d) => s + d.value, 0);
  if (total <= 0)
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">No data</p>
    );

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={58}
          outerRadius={88}
          paddingAngle={2}
          dataKey="value"
        >
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.color} />
          ))}
        </Pie>
        <Tooltip
          formatter={(v: number, name: string) => [
            `$${fmtMoney(v)} (${((v / total) * 100).toFixed(1)}%)`,
            name,
          ]}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          formatter={(value, entry) => {
            // @ts-expect-error recharts payload typing
            const pct = ((entry.payload.value / total) * 100).toFixed(1);
            return `${value} ${pct}%`;
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
