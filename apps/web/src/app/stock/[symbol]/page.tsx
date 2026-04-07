"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  AreaChart, Area, BarChart, Bar, ComposedChart, Line,
  LineChart, XAxis, YAxis, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell, Legend,
} from "recharts";
import { cn } from "@/lib/utils";
import {
  useDeepDive, useDeepDiveAIMutation,
  useRating, useScenarioEV, useFinancials, useValuation, useDCF, usePEBand,
} from "@/hooks/use-queries";
import type {
  DeepDiveData,
  DeepDiveCompany,
  DeepDiveSupplyChain,
  DeepDivePosition,
  DeepDivePrice,
  DeepDiveRevenue,
  DeepDiveInstitutional,
  DeepDiveMargin,
  DeepDiveAIAnalysis,
} from "@/lib/types";
import {
  ArrowLeft, TrendingUp, TrendingDown, Minus, Zap,
  AlertTriangle, Building2, BarChart3, Activity,
  Target, DollarSign, Star,
} from "lucide-react";

const RECENT_KEY = "deep_dive_recent";
const MAX_RECENT = 6;

// ── Tooltip style ─────────────────────────────────────────────────────────────

const TT = {
  backgroundColor: "#18181b",
  border: "1px solid #3f3f46",
  borderRadius: "8px",
  fontSize: "11px",
  color: "#e4e4e7",
};

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-zinc-800", className)} />;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-64 w-full" />
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-52" />
        <Skeleton className="h-52" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-52" />
        <Skeleton className="h-52" />
      </div>
    </div>
  );
}

// ── Card wrapper ──────────────────────────────────────────────────────────────

function Card({
  title,
  subtitle,
  icon,
  children,
  className,
}: {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("bg-zinc-800/60 border border-zinc-700/80 rounded-xl overflow-hidden", className)}>
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <div className="flex items-center gap-2">
          {icon && <span className="text-zinc-500">{icon}</span>}
          <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">{title}</span>
        </div>
        {subtitle && <span className="text-xs text-zinc-600">{subtitle}</span>}
      </div>
      <div className="px-4 pb-4">{children}</div>
    </div>
  );
}

// ── StockHeader ───────────────────────────────────────────────────────────────

function StockHeader({ data }: { data: DeepDiveData }) {
  const { symbol, company, price, position } = data;

  const vsMA20 =
    price && price.ma20
      ? ((price.current - price.ma20) / price.ma20) * 100
      : null;

  const rsiColor =
    price?.rsi != null
      ? price.rsi > 70
        ? "text-red-400 bg-red-950/60 border-red-700/50"
        : price.rsi < 30
          ? "text-emerald-400 bg-emerald-950/60 border-emerald-700/50"
          : "text-zinc-300 bg-zinc-700/60 border-zinc-600"
      : "";

  return (
    <div className="bg-zinc-800/80 border border-zinc-700/80 rounded-xl p-5 mb-4">
      {/* Top row: symbol + price */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        {/* Left: identity */}
        <div>
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-3xl font-bold font-mono text-zinc-100">{symbol}</span>
            {company?.name && (
              <span className="text-xl text-zinc-300 font-semibold">{company.name}</span>
            )}
            {position && (
              <span className="text-xs bg-emerald-950 border border-emerald-700/60 text-emerald-400 px-2 py-0.5 rounded-full font-medium">
                持有 {position.qty.toLocaleString()} 股
              </span>
            )}
          </div>
          <div className="mt-1 text-sm text-zinc-500">
            {[company?.sector, company?.industry].filter(Boolean).join(" · ")}
          </div>
        </div>

        {/* Right: price */}
        {price && (
          <div className="text-right">
            <div className="text-3xl font-bold text-zinc-100 tabular-nums">
              {price.current.toLocaleString()}
            </div>
            {vsMA20 !== null && (
              <div className={cn("text-sm font-medium mt-0.5", vsMA20 >= 0 ? "text-emerald-400" : "text-red-400")}>
                {vsMA20 >= 0 ? "▲" : "▼"} {Math.abs(vsMA20).toFixed(2)}% vs MA20
              </div>
            )}
          </div>
        )}
      </div>

      {/* Stat pills */}
      {price && (
        <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-zinc-700/60">
          <StatPill label="MA20" value={price.ma20?.toFixed(1) ?? "—"} />
          <StatPill label="MA60" value={price.ma60?.toFixed(1) ?? "—"} />
          {price.rsi != null && (
            <span className={cn("text-xs border px-2.5 py-1 rounded-lg font-medium", rsiColor)}>
              RSI {price.rsi.toFixed(1)}
            </span>
          )}
          {company?.market_cap && (
            <StatPill label="市值" value={`${(company.market_cap / 1e4).toFixed(0)} 億`} />
          )}
          {position && position.unrealized_pnl_pct != null && (
            <span
              className={cn(
                "text-xs border px-2.5 py-1 rounded-lg font-medium",
                position.unrealized_pnl_pct >= 0
                  ? "text-emerald-400 bg-emerald-950/60 border-emerald-700/50"
                  : "text-red-400 bg-red-950/60 border-red-700/50",
              )}
            >
              未實現 {position.unrealized_pnl_pct >= 0 ? "+" : ""}
              {position.unrealized_pnl_pct.toFixed(2)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-xs bg-zinc-700/60 border border-zinc-600 text-zinc-300 px-2.5 py-1 rounded-lg font-medium">
      {label} <span className="text-zinc-400">{value}</span>
    </span>
  );
}

// ── PriceChartSection ─────────────────────────────────────────────────────────

function PriceChartSection({ price }: { price: DeepDivePrice | null }) {
  if (!price || !price.dates.length) return null;

  const chartData = price.dates.map((d, i) => ({
    date: d.slice(5), // MM-DD
    close: price.closes[i],
  }));

  // Compute MA lines for chart overlay
  const ma20 = price.ma20;
  const ma60 = price.ma60;

  const minClose = Math.min(...price.closes);
  const maxClose = Math.max(...price.closes);
  const padding = (maxClose - minClose) * 0.05;
  const domain: [number, number] = [minClose - padding, maxClose + padding];

  return (
    <Card title="價格走勢" subtitle="近30交易日" icon={<Activity className="h-4 w-4" />}>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.18} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#71717a" }}
            interval="preserveStartEnd"
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#71717a" }}
            domain={domain}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => v.toLocaleString()}
          />
          <Tooltip
            contentStyle={TT}
            formatter={(v: number, name: string) => [
              v.toLocaleString(),
              name === "close" ? "收盤價" : name === "ma20" ? "MA20" : "MA60",
            ]}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="url(#priceGrad)"
            dot={false}
          />
          {/* MA20 reference line */}
          {ma20 !== null && (
            <ReferenceLine y={ma20} stroke="#f59e0b" strokeDasharray="4 3" strokeWidth={1.5}>
            </ReferenceLine>
          )}
          {/* MA60 reference line */}
          {ma60 !== null && (
            <ReferenceLine y={ma60} stroke="#a855f7" strokeDasharray="4 3" strokeWidth={1.5}>
            </ReferenceLine>
          )}
        </ComposedChart>
      </ResponsiveContainer>
      {/* Legend */}
      <div className="flex gap-4 mt-1 justify-end">
        <span className="text-xs text-blue-400 flex items-center gap-1.5">
          <span className="w-5 h-0.5 bg-blue-400 inline-block rounded" /> 收盤
        </span>
        <span className="text-xs text-amber-400 flex items-center gap-1.5">
          <span className="w-5 h-0.5 bg-amber-400 inline-block rounded border-dashed" /> MA20
        </span>
        <span className="text-xs text-purple-400 flex items-center gap-1.5">
          <span className="w-5 h-0.5 bg-purple-400 inline-block rounded" /> MA60
        </span>
      </div>
    </Card>
  );
}

// ── CompanyBio ────────────────────────────────────────────────────────────────

function CompanyBio({ company, themes }: { company: DeepDiveCompany | null; themes: string[] }) {
  if (!company && themes.length === 0) return null;

  const THEME_COLORS: Record<string, string> = {
    AI: "bg-purple-950 border-purple-700/60 text-purple-300",
    半導體: "bg-blue-950 border-blue-700/60 text-blue-300",
    電動車: "bg-emerald-950 border-emerald-700/60 text-emerald-300",
    伺服器: "bg-cyan-950 border-cyan-700/60 text-cyan-300",
    網通: "bg-teal-950 border-teal-700/60 text-teal-300",
    EUV: "bg-blue-950 border-blue-700/60 text-blue-300",
    NVIDIA: "bg-green-950 border-green-700/60 text-green-300",
  };

  return (
    <Card title="公司簡介" icon={<Building2 className="h-4 w-4" />}>
      {/* Themes */}
      {themes.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {themes.map((t) => {
            const key = Object.keys(THEME_COLORS).find((k) => t.includes(k));
            return (
              <span
                key={t}
                className={cn(
                  "text-xs font-medium px-2.5 py-0.5 rounded-full border",
                  key ? THEME_COLORS[key] : "bg-zinc-700/60 border-zinc-600 text-zinc-300",
                )}
              >
                {t}
              </span>
            );
          })}
        </div>
      )}
      {/* Description */}
      {company?.description && (
        <p className="text-sm text-zinc-300 leading-relaxed line-clamp-5">
          {company.description}
        </p>
      )}
    </Card>
  );
}

// ── SupplyChainSection ────────────────────────────────────────────────────────

function SupplyChainSection({ supplyChain }: { supplyChain: DeepDiveSupplyChain | null }) {
  if (!supplyChain || (supplyChain.upstream.length === 0 && supplyChain.downstream.length === 0)) {
    return null;
  }

  return (
    <Card title="供應鏈" icon={<BarChart3 className="h-4 w-4" />}>
      <div className="grid grid-cols-2 gap-4">
        {/* Upstream */}
        <div>
          <div className="text-xs text-zinc-500 font-semibold mb-2 uppercase tracking-wide">↑ 上游供應商</div>
          <ul className="space-y-1.5">
            {supplyChain.upstream.slice(0, 7).map((n) => (
              <li key={n.ticker} className="flex items-center gap-2">
                <Link href={`/stock/${n.ticker}`} className="group flex items-center gap-1.5 min-w-0">
                  <span className="text-xs font-mono font-semibold text-blue-400 group-hover:text-blue-300 transition-colors flex-shrink-0">
                    {n.ticker.length <= 6 ? n.ticker : n.ticker.slice(0, 6)}
                  </span>
                  <span className="text-xs text-zinc-400 group-hover:text-zinc-200 truncate transition-colors">
                    {n.name !== n.ticker ? n.name : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
        {/* Downstream */}
        <div>
          <div className="text-xs text-zinc-500 font-semibold mb-2 uppercase tracking-wide">↓ 下游客戶</div>
          <ul className="space-y-1.5">
            {supplyChain.downstream.slice(0, 7).map((n) => (
              <li key={n.ticker} className="flex items-center gap-2">
                <Link href={`/stock/${n.ticker}`} className="group flex items-center gap-1.5 min-w-0">
                  <span className="text-xs font-mono font-semibold text-orange-400 group-hover:text-orange-300 transition-colors flex-shrink-0">
                    {n.ticker.length <= 6 ? n.ticker : n.ticker.slice(0, 6)}
                  </span>
                  <span className="text-xs text-zinc-400 group-hover:text-zinc-200 truncate transition-colors">
                    {n.name !== n.ticker ? n.name : ""}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

// ── RevenueSection ────────────────────────────────────────────────────────────

function RevenueSection({ revenue }: { revenue: DeepDiveRevenue | null }) {
  if (!revenue || revenue.data.length === 0) return null;

  const chartData = revenue.data.map((d) => ({
    month: d.year_month.slice(2, 7).replace("-", "/"),
    revenue: +(d.revenue / 1e8).toFixed(2),
    yoy: d.yoy_pct,
  }));

  const latest = revenue.data[revenue.data.length - 1];
  const trendLabel =
    revenue.trend === "accelerating" ? "加速成長" : revenue.trend === "decelerating" ? "趨緩" : "穩定";
  const trendColor =
    revenue.trend === "accelerating"
      ? "text-emerald-400 bg-emerald-950/60 border-emerald-700/50"
      : revenue.trend === "decelerating"
        ? "text-amber-400 bg-amber-950/60 border-amber-700/50"
        : "text-zinc-400 bg-zinc-700/60 border-zinc-600";

  return (
    <Card title="月營收" subtitle="近12個月">
      <div className="flex items-center gap-2 mb-3">
        <span className={cn("text-xs border px-2 py-0.5 rounded-full font-medium", trendColor)}>
          {trendLabel}
        </span>
        {latest && (
          <span className="text-xs text-zinc-500">
            最新月 {(latest.revenue / 1e8).toFixed(0)} 億
            {latest.yoy_pct !== null && (
              <span className={cn("ml-1 font-medium", (latest.yoy_pct ?? 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                YoY {(latest.yoy_pct ?? 0) >= 0 ? "+" : ""}{latest.yoy_pct?.toFixed(1)}%
              </span>
            )}
          </span>
        )}
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 28, left: -16, bottom: 0 }}>
          <XAxis
            dataKey="month"
            tick={{ fontSize: 9, fill: "#71717a" }}
            interval="preserveStartEnd"
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="rev"
            tick={{ fontSize: 9, fill: "#71717a" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${v.toFixed(0)}億`}
          />
          <YAxis
            yAxisId="yoy"
            orientation="right"
            tick={{ fontSize: 9, fill: "#71717a" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          />
          <Tooltip
            contentStyle={TT}
            formatter={(value: number, name: string) => [
              name === "revenue" ? `${value.toFixed(2)} 億` : `${value?.toFixed(1)}%`,
              name === "revenue" ? "月營收" : "YoY",
            ]}
          />
          <ReferenceLine yAxisId="yoy" y={0} stroke="#52525b" strokeDasharray="3 3" />
          <Bar yAxisId="rev" dataKey="revenue" radius={[3, 3, 0, 0]}>
            {chartData.map((entry, idx) => (
              <Cell
                key={idx}
                fill={(entry.yoy ?? 0) >= 0 ? "#10b981" : "#ef4444"}
                fillOpacity={0.7}
              />
            ))}
          </Bar>
          <Line
            yAxisId="yoy"
            type="monotone"
            dataKey="yoy"
            stroke="#f59e0b"
            strokeWidth={1.5}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="flex gap-4 mt-1 justify-end">
        <span className="text-xs text-emerald-400 flex items-center gap-1">
          <span className="w-3 h-3 bg-emerald-500/70 inline-block rounded-sm" /> 月營收
        </span>
        <span className="text-xs text-amber-400 flex items-center gap-1">
          <span className="w-5 h-0.5 bg-amber-400 inline-block" /> YoY%
        </span>
      </div>
    </Card>
  );
}

// ── InstitutionalSection ──────────────────────────────────────────────────────

function InstitutionalSection({ institutional }: { institutional: DeepDiveInstitutional | null }) {
  if (!institutional || institutional.data.length === 0) return null;

  // Convert shares → 張 (÷1000), show last 20 days
  const chartData = institutional.data.slice(-20).map((d) => ({
    date: d.date.slice(5),
    foreign: Math.round(d.foreign_net / 1000),
    trust: Math.round(d.trust_net / 1000),
    dealer: Math.round(d.dealer_net / 1000),
    total: Math.round(d.total_net / 1000),
  }));

  // Cumulative sum of last 5d for summary
  const last5 = chartData.slice(-5);
  const sum5 = {
    foreign: last5.reduce((a, b) => a + b.foreign, 0),
    trust: last5.reduce((a, b) => a + b.trust, 0),
    dealer: last5.reduce((a, b) => a + b.dealer, 0),
  };

  return (
    <Card title="三大法人" subtitle="近20日 (張)">
      {/* 5-day summary */}
      <div className="grid grid-cols-3 gap-2 mb-3">
        {[
          { label: "外資", value: sum5.foreign, color: "text-blue-400" },
          { label: "投信", value: sum5.trust, color: "text-emerald-400" },
          { label: "自營商", value: sum5.dealer, color: "text-orange-400" },
        ].map((item) => (
          <div key={item.label} className="bg-zinc-900/60 rounded-lg p-2 text-center border border-zinc-700/40">
            <div className="text-xs text-zinc-500 mb-1">{item.label} 5日</div>
            <div
              className={cn("text-sm font-bold tabular-nums", item.color)}
            >
              {item.value >= 0 ? "+" : ""}{item.value.toLocaleString()}
            </div>
          </div>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: "#71717a" }}
            interval="preserveStartEnd"
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 9, fill: "#71717a" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${v >= 0 ? "" : ""}${(v / 1000).toFixed(0)}k`}
          />
          <ReferenceLine y={0} stroke="#52525b" strokeDasharray="3 3" />
          <Tooltip
            contentStyle={TT}
            formatter={(v: number, name: string) => [
              `${v.toLocaleString()} 張`,
              name === "foreign" ? "外資" : name === "trust" ? "投信" : "自營商",
            ]}
          />
          <Bar dataKey="foreign" stackId="a" fill="#3b82f6" fillOpacity={0.75} radius={[0, 0, 0, 0]} />
          <Bar dataKey="trust" stackId="a" fill="#10b981" fillOpacity={0.75} />
          <Bar dataKey="dealer" stackId="a" fill="#f97316" fillOpacity={0.75} radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>

      <div className="flex gap-3 mt-1 justify-end">
        {[{ c: "#3b82f6", l: "外資" }, { c: "#10b981", l: "投信" }, { c: "#f97316", l: "自營商" }].map((x) => (
          <span key={x.l} className="text-xs flex items-center gap-1" style={{ color: x.c }}>
            <span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ backgroundColor: x.c, opacity: 0.75 }} />
            {x.l}
          </span>
        ))}
      </div>
    </Card>
  );
}

// ── MarginSection ─────────────────────────────────────────────────────────────

function MarginSection({ margin }: { margin: DeepDiveMargin | null }) {
  if (!margin || margin.data.length === 0) return null;

  const chartData = margin.data.map((d) => ({
    date: d.date.slice(5),
    margin: d.margin_balance,
    short: d.short_balance,
  }));

  const latest = margin.data[margin.data.length - 1];
  const prev = margin.data[margin.data.length - 6] ?? margin.data[0];
  const marginChange = prev ? latest.margin_balance - prev.margin_balance : null;

  return (
    <Card title="融資融券" subtitle="近30日">
      <div className="flex gap-4 mb-3">
        <div className="bg-zinc-900/60 rounded-lg p-2 border border-zinc-700/40">
          <div className="text-xs text-zinc-500 mb-0.5">融資餘額</div>
          <div className="text-sm font-bold text-blue-400 tabular-nums">
            {latest.margin_balance.toLocaleString()}
          </div>
          {marginChange !== null && (
            <div className={cn("text-xs", marginChange >= 0 ? "text-emerald-400" : "text-red-400")}>
              {marginChange >= 0 ? "+" : ""}{marginChange.toLocaleString()} (5d)
            </div>
          )}
        </div>
        <div className="bg-zinc-900/60 rounded-lg p-2 border border-zinc-700/40">
          <div className="text-xs text-zinc-500 mb-0.5">融券餘額</div>
          <div className="text-sm font-bold text-amber-400 tabular-nums">
            {latest.short_balance.toLocaleString()}
          </div>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: "#71717a" }}
            interval="preserveStartEnd"
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 9, fill: "#71717a" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={TT}
            formatter={(v: number, name: string) => [
              v.toLocaleString(),
              name === "margin" ? "融資餘額" : "融券餘額",
            ]}
          />
          <Line type="monotone" dataKey="margin" stroke="#3b82f6" dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="short" stroke="#f59e0b" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}

// ── AnomalySection ────────────────────────────────────────────────────────────

function AnomalySection({ anomalies }: { anomalies: Record<string, unknown>[] }) {
  if (anomalies.length === 0) return null;
  return (
    <Card title="異常訊號偵測">
      <ul className="space-y-2.5">
        {anomalies.slice(0, 6).map((a, i) => {
          const severity = a.severity as string;
          const date = a.date as string;
          const reason = a.reason as string;
          const method = a.method as string;
          return (
            <li key={i} className="flex items-start gap-2.5 p-2.5 rounded-lg bg-zinc-900/50 border border-zinc-700/40">
              <AlertTriangle
                className={cn(
                  "h-3.5 w-3.5 mt-0.5 flex-shrink-0",
                  severity === "high" ? "text-red-400" : "text-amber-400",
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-zinc-300">{date}</span>
                  <span className="text-xs text-zinc-600 bg-zinc-800 px-1.5 py-0.5 rounded">
                    {method === "zscore" ? "Z-Score" : "Autoencoder"}
                  </span>
                </div>
                <p className="text-xs text-zinc-400 mt-0.5 leading-relaxed">{reason}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

// ── CatalystSection ───────────────────────────────────────────────────────────

function CatalystSection({ catalysts, symbol }: { catalysts: Record<string, unknown>[]; symbol: string }) {
  return (
    <Card title="催化劑事件">
      {catalysts.length === 0 ? (
        <div className="flex items-center justify-between py-1">
          <p className="text-sm text-zinc-500">尚無催化劑紀錄</p>
          <Link
            href={`/catalyst?symbol=${symbol}`}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors font-medium"
          >
            + 新增催化劑
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {catalysts.slice(0, 6).map((c, i) => {
            const title = c.title as string;
            const eventDate = (c.event_date ?? c.eventDate) as string | null;
            const status = c.status as string;
            return (
              <li key={i} className="flex items-center justify-between gap-2 text-xs p-2 rounded-lg bg-zinc-900/50 border border-zinc-700/40">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={cn(
                      "flex-shrink-0 px-1.5 py-0.5 rounded text-xs font-medium border",
                      status === "pending"
                        ? "bg-blue-950/60 border-blue-700/50 text-blue-300"
                        : "bg-zinc-700/60 border-zinc-600 text-zinc-400",
                    )}
                  >
                    {status === "pending" ? "待觀察" : "已過"}
                  </span>
                  <span className="text-zinc-300 truncate">{title}</span>
                </div>
                <span className="text-zinc-500 flex-shrink-0">{eventDate ?? "—"}</span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

// ── AIAnalysisSection ─────────────────────────────────────────────────────────

function AIAnalysisSection({ symbol }: { symbol: string }) {
  const mutation = useDeepDiveAIMutation();
  const result = mutation.data as DeepDiveAIAnalysis | undefined;

  return (
    <Card
      title="J.A.R.V.I.S. 深度分析"
      className="border-blue-800/40 bg-gradient-to-br from-blue-950/20 via-zinc-800/60 to-zinc-800/60"
    >
      {!result && !mutation.isPending && (
        <div className="flex flex-col items-center gap-3 py-5">
          <p className="text-sm text-zinc-400 text-center">整合所有數據，提供結構化的投資分析報告</p>
          <button
            onClick={() => mutation.mutate(symbol)}
            className={cn(
              "flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold",
              "bg-gradient-to-r from-blue-600 to-cyan-600 text-white",
              "hover:from-blue-500 hover:to-cyan-500 transition-all duration-200",
              "shadow-lg shadow-blue-900/40",
            )}
          >
            <Zap className="h-4 w-4" />
            啟動 J.A.R.V.I.S. 分析
          </button>
        </div>
      )}

      {mutation.isPending && (
        <div className="flex flex-col items-center gap-3 py-8">
          <div className="h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-zinc-400">AI 分析中，請稍候...</p>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          {result.error ? (
            <p className="text-sm text-red-400">{result.error}</p>
          ) : (
            <>
              {/* Score + signal */}
              <div className="flex items-center gap-6 p-3 bg-zinc-900/60 rounded-xl border border-zinc-700/40">
                <div className="text-center">
                  <div
                    className={cn(
                      "text-5xl font-bold tabular-nums",
                      (result.overall_score ?? 0) >= 7
                        ? "text-emerald-400"
                        : (result.overall_score ?? 0) >= 4
                          ? "text-amber-400"
                          : "text-red-400",
                    )}
                  >
                    {result.overall_score}
                  </div>
                  <div className="text-xs text-zinc-500 mt-0.5">/ 10 分</div>
                </div>
                <div className="flex-1">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-full border mb-2",
                      result.buy_signal
                        ? "bg-emerald-950/60 border-emerald-700/50 text-emerald-400"
                        : "bg-red-950/60 border-red-700/50 text-red-400",
                    )}
                  >
                    {result.buy_signal ? (
                      <><TrendingUp className="h-3.5 w-3.5" /> 建議買入</>
                    ) : (
                      <><TrendingDown className="h-3.5 w-3.5" /> 暫不建議</>
                    )}
                  </span>
                  <p className="text-sm text-zinc-200 leading-relaxed">{result.summary}</p>
                </div>
              </div>

              {/* Analysis sections */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {[
                  { key: "theme_analysis", label: "主題分析" },
                  { key: "fundamental_analysis", label: "基本面" },
                  { key: "timing_analysis", label: "時機分析" },
                ].map(({ key, label }) => (
                  result[key as keyof typeof result] && (
                    <div key={key} className="p-3 bg-zinc-900/60 rounded-lg border border-zinc-700/40">
                      <div className="text-xs text-zinc-500 font-semibold mb-1.5 uppercase tracking-wide">{label}</div>
                      <p className="text-xs text-zinc-300 leading-relaxed">
                        {result[key as keyof typeof result] as string}
                      </p>
                    </div>
                  )
                ))}
              </div>

              {/* Risks */}
              {result.risks && result.risks.length > 0 && (
                <div className="p-3 bg-red-950/20 rounded-lg border border-red-900/40">
                  <div className="text-xs text-red-400 font-semibold mb-2">⚠ 風險因素</div>
                  <ul className="space-y-1">
                    {result.risks.map((r, i) => (
                      <li key={i} className="flex items-start gap-1.5 text-xs text-zinc-400">
                        <Minus className="h-3 w-3 mt-0.5 flex-shrink-0 text-red-500" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <button
                onClick={() => mutation.mutate(symbol)}
                className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
              >
                重新分析 →
              </button>
            </>
          )}
        </div>
      )}
    </Card>
  );
}

// ── Rating & Scenario ────────────────────────────────────────────────────────

const RATING_COLORS: Record<string, string> = {
  strong_buy:  "text-emerald-400 bg-emerald-950/60 border-emerald-700/50",
  buy:         "text-emerald-300 bg-emerald-950/40 border-emerald-700/40",
  hold:        "text-zinc-300 bg-zinc-700/60 border-zinc-600",
  sell:        "text-red-300 bg-red-950/40 border-red-700/40",
  strong_sell: "text-red-400 bg-red-950/60 border-red-700/50",
};

const RATING_LABELS: Record<string, string> = {
  strong_buy: "Strong Buy", buy: "Buy", hold: "Hold",
  sell: "Sell", strong_sell: "Strong Sell",
};

function RatingSection({ symbol }: { symbol: string }) {
  const { data: rating } = useRating(symbol);
  const { data: ev } = useScenarioEV(symbol);

  if (!rating && !ev) return null;

  return (
    <Card title="投資評等" icon={<Star className="h-4 w-4" />}>
      <div className="space-y-4">
        {rating && (
          <div className="flex items-center gap-4 flex-wrap">
            <span className={cn(
              "text-sm font-bold px-3 py-1.5 rounded-lg border",
              RATING_COLORS[rating.rating] ?? "text-zinc-300 bg-zinc-700/60 border-zinc-600",
            )}>
              {RATING_LABELS[rating.rating] ?? rating.rating}
            </span>
            {rating.target_price && (
              <div className="text-sm">
                <span className="text-zinc-500">目標價</span>{" "}
                <span className="font-mono font-semibold text-emerald-400">
                  {rating.target_price.toLocaleString()}
                </span>
              </div>
            )}
            {rating.stop_loss && (
              <div className="text-sm">
                <span className="text-zinc-500">停損價</span>{" "}
                <span className="font-mono font-semibold text-red-400">
                  {rating.stop_loss.toLocaleString()}
                </span>
              </div>
            )}
            {rating.current_price && rating.target_price && (
              <div className="text-sm">
                <span className="text-zinc-500">潛在漲幅</span>{" "}
                <span className={cn(
                  "font-mono font-semibold",
                  rating.target_price > rating.current_price ? "text-emerald-400" : "text-red-400",
                )}>
                  {((rating.target_price - rating.current_price) / rating.current_price * 100).toFixed(1)}%
                </span>
              </div>
            )}
          </div>
        )}
        {rating?.thesis && (
          <p className="text-xs text-zinc-400">{rating.thesis}</p>
        )}

        {/* Scenario expected value */}
        {ev && ev.scenarios && (
          <div className="space-y-2 pt-2 border-t border-zinc-700/60">
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider">情境分析</p>
            <div className="grid grid-cols-3 gap-2">
              {ev.scenarios.map((s: { label: string; target: number; probability: number }) => (
                <div key={s.label} className="rounded-lg border border-zinc-700/60 p-2.5 text-center">
                  <p className="text-xs text-zinc-500">{s.label}</p>
                  <p className="font-mono font-bold text-sm mt-1">{s.target.toLocaleString()}</p>
                  <p className="text-xs text-zinc-600 mt-0.5">{(s.probability * 100).toFixed(0)}%</p>
                </div>
              ))}
            </div>
            {ev.expected_value != null && (
              <div className="flex items-center gap-2 text-sm">
                <span className="text-zinc-500">期望值</span>
                <span className="font-mono font-bold text-amber-400">
                  {ev.expected_value.toLocaleString()}
                </span>
                {ev.upside_pct != null && (
                  <span className={cn(
                    "text-xs font-mono",
                    ev.upside_pct >= 0 ? "text-emerald-400" : "text-red-400",
                  )}>
                    ({ev.upside_pct >= 0 ? "+" : ""}{ev.upside_pct.toFixed(1)}%)
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

// ── Financials & Valuation ───────────────────────────────────────────────────

function FinancialsSection({ symbol }: { symbol: string }) {
  const { data: fin } = useFinancials(symbol);
  const { data: val } = useValuation(symbol);

  if (!fin && !val) return null;

  const quarters = fin?.quarters ?? [];
  const latestQ = quarters[0];

  return (
    <Card title="財務數據" icon={<DollarSign className="h-4 w-4" />}>
      <div className="space-y-3">
        {/* Valuation metrics */}
        {val && (
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "PER", value: val.per?.toFixed(1) },
              { label: "PBR", value: val.pbr?.toFixed(2) },
              { label: "殖利率", value: val.dividend_yield ? `${val.dividend_yield.toFixed(2)}%` : null },
              { label: "EPS(TTM)", value: val.eps_ttm?.toFixed(2) },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg border border-zinc-700/60 p-2 text-center">
                <p className="text-xs text-zinc-500">{label}</p>
                <p className="font-mono font-semibold text-sm mt-1">{value ?? "—"}</p>
              </div>
            ))}
          </div>
        )}

        {/* Quarterly EPS trend */}
        {quarters.length > 0 && (
          <div className="space-y-1.5">
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider">季度 EPS</p>
            <div className="flex gap-1.5">
              {quarters.slice(0, 8).reverse().map((q: { quarter: string; eps: number }) => (
                <div key={q.quarter} className="flex-1 rounded-md border border-zinc-700/60 p-1.5 text-center">
                  <p className="text-[10px] text-zinc-600">{q.quarter}</p>
                  <p className={cn(
                    "font-mono text-xs font-semibold mt-0.5",
                    q.eps >= 0 ? "text-emerald-400" : "text-red-400",
                  )}>
                    {q.eps.toFixed(2)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Margin trend */}
        {quarters.length > 0 && latestQ?.gross_margin != null && (
          <div className="grid grid-cols-3 gap-2 pt-2 border-t border-zinc-700/60">
            {[
              { label: "毛利率", value: latestQ.gross_margin },
              { label: "營益率", value: latestQ.operating_margin },
              { label: "淨利率", value: latestQ.net_margin },
            ].map(({ label, value }) => (
              <div key={label} className="text-center">
                <p className="text-xs text-zinc-500">{label}</p>
                <p className="font-mono text-sm font-semibold mt-0.5">
                  {value != null ? `${(value * 100).toFixed(1)}%` : "—"}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

// ── Valuation Models ─────────────────────────────────────────────────────────

function ValuationSection({ symbol }: { symbol: string }) {
  const { data: dcf } = useDCF(symbol);
  const { data: pe } = usePEBand(symbol);

  if (!dcf && !pe) return null;

  return (
    <Card title="估值模型" icon={<Target className="h-4 w-4" />}>
      <div className="space-y-4">
        {/* DCF */}
        {dcf && dcf.fair_value != null && (
          <div className="space-y-1.5">
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider">DCF 估值</p>
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg border border-zinc-700/60 p-2 text-center">
                <p className="text-xs text-zinc-500">合理價</p>
                <p className="font-mono font-bold text-amber-400 mt-1">
                  {dcf.fair_value.toLocaleString()}
                </p>
              </div>
              {dcf.wacc != null && (
                <div className="rounded-lg border border-zinc-700/60 p-2 text-center">
                  <p className="text-xs text-zinc-500">WACC</p>
                  <p className="font-mono text-sm mt-1">{(dcf.wacc * 100).toFixed(1)}%</p>
                </div>
              )}
              {dcf.terminal_growth != null && (
                <div className="rounded-lg border border-zinc-700/60 p-2 text-center">
                  <p className="text-xs text-zinc-500">終值成長率</p>
                  <p className="font-mono text-sm mt-1">{(dcf.terminal_growth * 100).toFixed(1)}%</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* PE Band */}
        {pe && pe.per_bands && (
          <div className="space-y-1.5 pt-2 border-t border-zinc-700/60">
            <p className="text-xs text-zinc-500 font-semibold uppercase tracking-wider">PE Band (河流圖)</p>
            <div className="grid grid-cols-5 gap-1.5">
              {pe.per_bands.map((b: { multiple: number; price: number }, i: number) => {
                const labels = ["極便宜", "便宜", "合理", "昂貴", "極昂貴"];
                const colors = [
                  "text-emerald-400", "text-emerald-300", "text-zinc-300", "text-red-300", "text-red-400",
                ];
                return (
                  <div key={i} className="rounded-md border border-zinc-700/60 p-1.5 text-center">
                    <p className="text-[10px] text-zinc-600">{labels[i] ?? `${b.multiple}x`}</p>
                    <p className={cn("font-mono text-xs font-semibold mt-0.5", colors[i])}>
                      {b.price.toLocaleString()}
                    </p>
                    <p className="text-[10px] text-zinc-600">{b.multiple.toFixed(0)}x</p>
                  </div>
                );
              })}
            </div>
            {pe.per_stats && (
              <div className="flex gap-3 text-xs text-zinc-500 mt-1">
                <span>現在 PER: <span className="text-zinc-300 font-mono">{pe.per_stats.current?.toFixed(1) ?? "—"}</span></span>
                <span>百分位: <span className="text-zinc-300 font-mono">{pe.per_stats.percentile?.toFixed(0) ?? "—"}%</span></span>
              </div>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function StockDeepDivePage() {
  const params = useParams();
  const router = useRouter();
  const symbol = typeof params.symbol === "string" ? params.symbol.toUpperCase() : null;

  useEffect(() => {
    if (!symbol) return;
    try {
      const prev = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as string[];
      const next = [symbol, ...prev.filter((t) => t !== symbol)].slice(0, MAX_RECENT);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
    } catch {}
  }, [symbol]);

  const { data, isLoading, error } = useDeepDive(symbol);

  return (
    <div className="min-h-screen bg-zinc-900 text-zinc-100">
      <div className="max-w-5xl mx-auto px-4 py-6">
        <button
          onClick={() => router.push("/stock")}
          className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          個股深度研究
        </button>

        {isLoading && <LoadingSkeleton />}

        {error && (
          <div className="bg-red-950/40 border border-red-700/50 rounded-xl p-4 text-sm text-red-300">
            載入失敗，請稍後再試。
          </div>
        )}

        {data && !isLoading && (
          <div className="space-y-4">
            {/* Header bar */}
            <StockHeader data={data} />

            {/* Row 1: Price chart (full width) */}
            <PriceChartSection price={data.price} />

            {/* Row 2: Company bio + Supply chain */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <CompanyBio company={data.company} themes={data.themes} />
              <SupplyChainSection supplyChain={data.supply_chain} />
            </div>

            {/* Row 3: Revenue (wider) + Institutional */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <RevenueSection revenue={data.revenue} />
              <InstitutionalSection institutional={data.institutional} />
            </div>

            {/* Row 4: Margin + Anomaly */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MarginSection margin={data.margin} />
              <AnomalySection anomalies={data.anomalies} />
            </div>

            {/* Row 5: Rating + Valuation */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <RatingSection symbol={data.symbol} />
              <ValuationSection symbol={data.symbol} />
            </div>

            {/* Row 6: Financials (full width) */}
            <FinancialsSection symbol={data.symbol} />

            {/* Row 7: Catalysts */}
            <CatalystSection catalysts={data.catalysts} symbol={data.symbol} />

            {/* Row 6: AI Analysis */}
            <AIAnalysisSection symbol={data.symbol} />
          </div>
        )}
      </div>
    </div>
  );
}
