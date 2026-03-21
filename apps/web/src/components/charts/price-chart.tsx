"use client";

import { useState } from "react";
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { ChartPoint } from "@/lib/types";

type Indicator = "ma" | "rsi" | "kd";

interface Props {
  data: ChartPoint[];
  avgCost?: number | null;
}

export function PriceChart({ data, avgCost }: Props) {
  const [indicator, setIndicator] = useState<Indicator>("ma");

  if (!data.length)
    return <p className="text-sm text-muted-foreground py-4 text-center">No price data</p>;

  const lastPrice = data[data.length - 1]?.close;
  const priceMin = Math.min(...data.map((d) => d.close)) * 0.98;
  const priceMax = Math.max(...data.map((d) => d.close)) * 1.02;

  const fmtDate = (d: string) => d.slice(5); // MM-DD

  return (
    <div className="space-y-2">
      {/* Indicator toggle */}
      <div className="flex gap-1">
        {(["ma", "rsi", "kd"] as Indicator[]).map((ind) => (
          <button
            key={ind}
            onClick={() => setIndicator(ind)}
            className={[
              "px-2 py-0.5 rounded text-xs font-medium transition-colors",
              indicator === ind
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80",
            ].join(" ")}
          >
            {ind.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Price + MA chart */}
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtDate}
            tick={{ fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[priceMin, priceMax]}
            tick={{ fontSize: 10 }}
            width={48}
            tickFormatter={(v) => v.toFixed(1)}
          />
          <Tooltip
            labelFormatter={(l) => `Date: ${l}`}
            formatter={(v: number, name: string) => [v.toFixed(2), name]}
            contentStyle={{ fontSize: 11 }}
          />
          {/* Cost line */}
          {avgCost && (
            <ReferenceLine y={avgCost} stroke="#f59e0b" strokeDasharray="4 2"
              label={{ value: `成本 ${avgCost.toFixed(2)}`, position: "right", fontSize: 9, fill: "#f59e0b" }} />
          )}
          <Line dataKey="close" stroke="#3b82f6" dot={false} strokeWidth={1.5} name="Close" />
          {indicator === "ma" && (
            <>
              <Line dataKey="ma20" stroke="#10b981" dot={false} strokeWidth={1} name="MA20" connectNulls />
              <Line dataKey="ma60" stroke="#f97316" dot={false} strokeWidth={1} name="MA60" connectNulls />
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Sub-chart: RSI or KD */}
      {indicator === "rsi" && (
        <ResponsiveContainer width="100%" height={100}>
          <ComposedChart data={data} margin={{ top: 0, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
            <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fontSize: 9 }} interval="preserveStartEnd" />
            <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} width={28} />
            <Tooltip contentStyle={{ fontSize: 10 }} formatter={(v: number) => [v?.toFixed(1)]} />
            <ReferenceLine y={70} stroke="#ef4444" strokeDasharray="3 2" />
            <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 2" />
            <Line dataKey="rsi" stroke="#8b5cf6" dot={false} strokeWidth={1.5} name="RSI(14)" connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {indicator === "kd" && (
        <ResponsiveContainer width="100%" height={100}>
          <ComposedChart data={data} margin={{ top: 0, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
            <XAxis dataKey="date" tickFormatter={fmtDate} tick={{ fontSize: 9 }} interval="preserveStartEnd" />
            <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} width={28} />
            <Tooltip contentStyle={{ fontSize: 10 }} formatter={(v: number) => [v?.toFixed(1)]} />
            <ReferenceLine y={80} stroke="#ef4444" strokeDasharray="3 2" />
            <ReferenceLine y={20} stroke="#10b981" strokeDasharray="3 2" />
            <Line dataKey="k" stroke="#3b82f6" dot={false} strokeWidth={1.5} name="K" connectNulls />
            <Line dataKey="d" stroke="#f97316" dot={false} strokeWidth={1.5} name="D" connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* RSI/KD current value badges */}
      {data.length > 0 && (
        <div className="flex gap-3 text-xs">
          {data[data.length-1].rsi != null && (
            <span className={[
              "px-1.5 py-0.5 rounded font-mono",
              (data[data.length-1].rsi ?? 50) > 70 ? "bg-red-100 text-red-600" :
              (data[data.length-1].rsi ?? 50) < 30 ? "bg-green-100 text-green-600" :
              "bg-muted text-muted-foreground",
            ].join(" ")}>
              RSI {data[data.length-1].rsi?.toFixed(1)}
            </span>
          )}
          {data[data.length-1].k != null && (
            <span className={[
              "px-1.5 py-0.5 rounded font-mono",
              (data[data.length-1].k ?? 50) > 80 ? "bg-red-100 text-red-600" :
              (data[data.length-1].k ?? 50) < 20 ? "bg-green-100 text-green-600" :
              "bg-muted text-muted-foreground",
            ].join(" ")}>
              K {data[data.length-1].k?.toFixed(1)}
            </span>
          )}
          {lastPrice && (
            <span className="px-1.5 py-0.5 rounded font-mono bg-blue-50 text-blue-700">
              ${lastPrice.toFixed(2)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
