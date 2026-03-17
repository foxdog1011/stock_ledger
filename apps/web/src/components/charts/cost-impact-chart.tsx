"use client";

import {
  ComposedChart,
  Bar,
  ReferenceLine,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { fmtMoney, fmtPct } from "@/lib/format";
import type { CostImpact } from "@/lib/types";

interface Props {
  impact: CostImpact;
  lastPrice?: number | null;
}

export function CostImpactChart({ impact, lastPrice }: Props) {
  const hasPrev = impact.prevQty > 0 && impact.prevAvgCost != null;

  const data = [
    ...(hasPrev
      ? [{ name: "Prev Avg", value: impact.prevAvgCost as number, isPrev: true }]
      : []),
    { name: "New Avg", value: impact.newAvgCost, isPrev: false },
  ];

  const yMin = Math.min(
    ...data.map((d) => d.value),
    ...(lastPrice != null ? [lastPrice] : []),
  ) * 0.98;

  const yMax = Math.max(
    ...data.map((d) => d.value),
    ...(lastPrice != null ? [lastPrice] : []),
  ) * 1.02;

  return (
    <ResponsiveContainer width="100%" height={100}>
      <ComposedChart
        data={data}
        margin={{ top: 4, right: 12, left: 0, bottom: 0 }}
        barCategoryGap="30%"
      >
        <XAxis dataKey="name" tick={{ fontSize: 10 }} />
        <YAxis
          tick={{ fontSize: 10 }}
          tickFormatter={(v: number) => fmtMoney(v, 2)}
          domain={[yMin, yMax]}
          width={64}
        />
        <Tooltip
          formatter={(v: number) => [fmtMoney(v, 4), "Avg Cost"]}
        />
        {lastPrice != null && (
          <ReferenceLine
            y={lastPrice}
            stroke="#10b981"
            strokeDasharray="3 2"
            label={{ value: `Price ${fmtMoney(lastPrice, 2)}`, position: "insideTopRight", fontSize: 9 }}
          />
        )}
        <Bar dataKey="value" maxBarSize={28} radius={[3, 3, 0, 0]}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={
                lastPrice != null
                  ? d.value <= lastPrice
                    ? "#10b981"
                    : "#ef4444"
                  : d.isPrev
                  ? "hsl(var(--muted-foreground))"
                  : "hsl(var(--primary))"
              }
              opacity={d.isPrev ? 0.6 : 0.85}
            />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}
