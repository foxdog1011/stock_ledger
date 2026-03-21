"use client";

import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import { fmtMoney } from "@/lib/format";

export interface AllocSlice {
  name: string;
  value: number;
  fill: string;
}

export function AllocDonutChart({ data }: { data: AllocSlice[] }) {
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total <= 0)
    return <p className="text-muted-foreground text-sm py-8 text-center">No data</p>;

  return (
    <ResponsiveContainer width="100%" height={200}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={55}
          outerRadius={82}
          paddingAngle={2}
          dataKey="value"
        >
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.fill} />
          ))}
        </Pie>
        <Tooltip
          formatter={(v: number, name: string) => [
            `${fmtMoney(v)} (${((v / total) * 100).toFixed(1)}%)`,
            name,
          ]}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
