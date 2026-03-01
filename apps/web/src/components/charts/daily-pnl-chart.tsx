"use client";

import {
  ComposedChart,
  Bar,
  Line,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { DailyPoint } from "@/lib/types";
import { fmtMoney, fmtPct } from "@/lib/format";

export type DailyMode = "pnl" | "delta";
export type DailyUnit = "twd" | "pct";

interface Props {
  data: DailyPoint[];
  mode: DailyMode;
  unit: DailyUnit;
  freq?: string;
}

// ── helpers ───────────────────────────────────────────────────────────────────

function xFmt(v: string): string {
  return v ? v.slice(5).replace("-", "/") : "";
}

function tickInterval(len: number): number {
  if (len <= 13) return 0;
  return Math.ceil(len / 6) - 1;
}

function getBarVal(d: DailyPoint, mode: DailyMode, unit: DailyUnit): number | null {
  if (unit === "pct") return d.dailyReturnPct;
  return mode === "pnl" ? d.dailyPnl : d.dailyChange;
}

// ── component ─────────────────────────────────────────────────────────────────

export function DailyPnlChart({ data, mode, unit, freq = "B" }: Props) {
  if (!data.length)
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">No data</p>
    );

  const isPct = unit === "pct";
  const barLabel = isPct
    ? "Daily Return %"
    : mode === "pnl"
    ? "Daily PnL"
    : "ΔEquity";

  const chartData = data.map((d) => ({
    ...d,
    barVal: getBarVal(d, mode, unit),
  }));

  const interval = tickInterval(data.length);

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart
        data={chartData}
        margin={{ top: 4, right: isPct ? 8 : 60, left: 0, bottom: 4 }}
      >
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />

        <XAxis
          dataKey="date"
          tick={{ fontSize: 11 }}
          tickFormatter={xFmt}
          interval={interval}
          className="text-muted-foreground"
        />

        {/* Left axis — bar values */}
        <YAxis
          yAxisId="left"
          tick={{ fontSize: 11 }}
          tickFormatter={
            isPct
              ? (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`
              : (v: number) => fmtMoney(v, 0)
          }
          className="text-muted-foreground"
          width={72}
        />

        {/* Right axis — total equity line (TWD mode only) */}
        {!isPct && (
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => fmtMoney(v, 0)}
            className="text-muted-foreground"
            width={60}
          />
        )}

        <Tooltip
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as DailyPoint & { barVal: number | null };
            const isStale = (d.priceStalenessDay ?? 0) > 2;
            return (
              <div className="rounded-lg border bg-background px-3 py-2 text-xs shadow-md space-y-0.5">
                <p className="font-semibold mb-1">{label}</p>
                {d.barVal != null ? (
                  <p className={d.barVal >= 0 ? "text-emerald-600" : "text-red-500"}>
                    {barLabel}:{" "}
                    <span className="font-medium">
                      {isPct ? fmtPct(d.barVal) : fmtMoney(d.barVal)}
                    </span>
                  </p>
                ) : (
                  <p className="text-muted-foreground">{barLabel}: —</p>
                )}
                {d.externalCashflow !== 0 && (
                  <p className="text-muted-foreground">
                    Cashflow:{" "}
                    <span className={d.externalCashflow > 0 ? "text-emerald-600" : "text-red-500"}>
                      {fmtMoney(d.externalCashflow)}
                    </span>
                  </p>
                )}
                <p className="text-muted-foreground">
                  Equity: <span className="text-foreground">{fmtMoney(d.totalEquity)}</span>
                </p>
                {isStale && (
                  <p className="text-amber-500 mt-1">
                    ⚠ Prices {d.priceStalenessDay}d stale
                  </p>
                )}
              </div>
            );
          }}
        />

        <Legend verticalAlign="top" height={24} iconSize={10} />

        <ReferenceLine yAxisId="left" y={0} stroke="#888" strokeDasharray="3 2" />

        <Bar
          yAxisId="left"
          dataKey="barVal"
          name={barLabel}
          maxBarSize={18}
          radius={[2, 2, 0, 0]}
        >
          {chartData.map((d, i) => {
            const val = d.barVal ?? 0;
            const stale = (d.priceStalenessDay ?? 0) > 2;
            return (
              <Cell
                key={i}
                fill={val >= 0 ? "#10b981" : "#ef4444"}
                opacity={stale ? 0.4 : 0.85}
              />
            );
          })}
        </Bar>

        {/* Total equity line on right axis (TWD mode only) */}
        {!isPct && (
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="totalEquity"
            name="Total Equity"
            stroke="hsl(var(--primary))"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
