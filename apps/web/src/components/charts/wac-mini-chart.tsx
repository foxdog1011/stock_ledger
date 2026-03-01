"use client";

import { LineChart, Line, Tooltip, ResponsiveContainer } from "recharts";
import { fmtMoney } from "@/lib/format";

interface Props {
  data: { date: string; avgCost: number }[];
}

export function WacMiniChart({ data }: Props) {
  if (data.length < 2)
    return <p className="text-xs text-muted-foreground">N/A</p>;
  return (
    <ResponsiveContainer width="100%" height={80}>
      <LineChart data={data}>
        <Tooltip
          formatter={(v: number) => [fmtMoney(v, 2), "Avg Cost"]}
          labelFormatter={(l: string) => l}
        />
        <Line
          type="monotone"
          dataKey="avgCost"
          stroke="hsl(var(--primary))"
          dot={false}
          strokeWidth={1.5}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
