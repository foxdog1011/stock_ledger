"use client";

import {
  ComposedChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { fmtMoney, fmtPct } from "@/lib/format";
import type { LotRecord } from "@/lib/types";

interface Props {
  lots: LotRecord[];
  avgCostWac: number | null;
}

export function LotsBubbleChart({ lots, avgCostWac }: Props) {
  if (!lots.length)
    return <p className="text-xs text-muted-foreground py-4 text-center">No open lots</p>;

  const marketPrice = lots[0].marketPrice;

  const chartData = lots.map((lot) => ({
    name: `#${lot.lotId}  ${lot.buyDate.slice(5)}`,
    costPerShare: lot.costPerShare,
    qtyRemaining: lot.qtyRemaining,
    unrealizedPct: lot.unrealizedPct,
    underwaterPct: lot.underwaterPct,
    lotId: lot.lotId,
    profitable: marketPrice != null ? lot.costPerShare <= marketPrice : true,
  }));

  const allPrices = [
    ...chartData.map((d) => d.costPerShare),
    ...(avgCostWac != null ? [avgCostWac] : []),
    ...(marketPrice != null ? [marketPrice] : []),
  ];
  const yMin = Math.min(...allPrices) * 0.985;
  const yMax = Math.max(...allPrices) * 1.015;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="name" tick={{ fontSize: 10 }} />
        <YAxis
          tick={{ fontSize: 11 }}
          tickFormatter={(v: number) => fmtMoney(v, 2)}
          domain={[yMin, yMax]}
          width={72}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as typeof chartData[number];
            return (
              <div className="rounded-lg border bg-background px-3 py-2 text-xs shadow-md space-y-0.5">
                <p className="font-semibold mb-1">Lot #{d.lotId}</p>
                <p>Cost/Share: <span className="tabular-nums font-medium">{fmtMoney(d.costPerShare, 4)}</span></p>
                <p>Qty Remaining: <span className="tabular-nums">{d.qtyRemaining}</span></p>
                {d.unrealizedPct != null && (
                  <p className={d.unrealizedPct >= 0 ? "text-emerald-600" : "text-red-500"}>
                    Return: <span className="font-medium">{fmtPct(d.unrealizedPct)}</span>
                  </p>
                )}
                {d.underwaterPct != null && d.underwaterPct > 0 && (
                  <p className="text-red-500">
                    Underwater: <span className="font-medium">{d.underwaterPct.toFixed(2)}%</span>
                  </p>
                )}
              </div>
            );
          }}
        />
        <Legend verticalAlign="top" height={20} iconSize={10} />

        {avgCostWac != null && (
          <ReferenceLine
            y={avgCostWac}
            stroke="hsl(var(--primary))"
            strokeDasharray="5 3"
            strokeWidth={1.5}
            label={{ value: `WAC ${fmtMoney(avgCostWac, 2)}`, position: "insideTopLeft", fontSize: 10, fill: "hsl(var(--primary))" }}
          />
        )}
        {marketPrice != null && (
          <ReferenceLine
            y={marketPrice}
            stroke="#10b981"
            strokeWidth={1.5}
            label={{ value: `Price ${fmtMoney(marketPrice, 2)}`, position: "insideTopRight", fontSize: 10, fill: "#10b981" }}
          />
        )}

        <Bar dataKey="costPerShare" name="Cost / Share" maxBarSize={36} radius={[3, 3, 0, 0]}>
          {chartData.map((d, i) => (
            <Cell
              key={i}
              fill={d.profitable ? "#10b981" : "#ef4444"}
              opacity={0.8}
            />
          ))}
        </Bar>
      </ComposedChart>
    </ResponsiveContainer>
  );
}
