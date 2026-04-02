"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import { cn } from "@/lib/utils";
import { useDeepDive, useDeepDiveAIMutation } from "@/hooks/use-queries";
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
import { ArrowLeft, TrendingUp, TrendingDown, Minus, Zap, AlertTriangle } from "lucide-react";

const RECENT_KEY = "deep_dive_recent";
const MAX_RECENT = 6;

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-zinc-800", className)} />;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-20 w-full" />
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Skeleton className="h-56" />
        <Skeleton className="h-56" />
      </div>
    </div>
  );
}

// ── Section card wrapper ───────────────────────────────────────────────────────

function SectionCard({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("bg-zinc-800/60 border border-zinc-700/80 rounded-xl p-4", className)}>
      <h2 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">{title}</h2>
      {children}
    </div>
  );
}

// ── StockHeader ───────────────────────────────────────────────────────────────

function StockHeader({ data }: { data: DeepDiveData }) {
  const { symbol, company, price, position } = data;

  const priceChange =
    price && price.ma20
      ? ((price.current - price.ma20) / price.ma20) * 100
      : null;

  return (
    <div className="bg-zinc-800/80 border border-zinc-700/80 rounded-xl p-5 mb-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-2xl font-bold font-mono text-zinc-100">{symbol}</span>
            {company?.name && (
              <span className="text-lg text-zinc-400 font-medium">{company.name}</span>
            )}
            {position && (
              <span className="text-xs bg-emerald-950 border border-emerald-700/60 text-emerald-400 px-2 py-0.5 rounded-full font-medium">
                持有中 {position.qty} 股
              </span>
            )}
          </div>
          {company && (
            <div className="mt-1 text-xs text-zinc-500">
              {[company.sector, company.industry].filter(Boolean).join(" · ")}
            </div>
          )}
        </div>

        {price && (
          <div className="text-right">
            <div className="text-2xl font-bold text-zinc-100">
              {price.current.toLocaleString()}
            </div>
            {priceChange !== null && (
              <div
                className={cn(
                  "text-sm font-medium",
                  priceChange >= 0 ? "text-emerald-400" : "text-red-400",
                )}
              >
                {priceChange >= 0 ? "+" : ""}
                {priceChange.toFixed(2)}% vs MA20
              </div>
            )}
            <div className="flex items-center gap-2 mt-2 justify-end flex-wrap">
              {price.ma20 !== null && (
                <span className="text-xs bg-zinc-700/60 border border-zinc-600 text-zinc-300 px-2 py-0.5 rounded">
                  MA20 {price.ma20.toFixed(1)}
                </span>
              )}
              {price.ma60 !== null && (
                <span className="text-xs bg-zinc-700/60 border border-zinc-600 text-zinc-300 px-2 py-0.5 rounded">
                  MA60 {price.ma60.toFixed(1)}
                </span>
              )}
              {price.rsi !== null && (
                <span
                  className={cn(
                    "text-xs border px-2 py-0.5 rounded",
                    price.rsi > 70
                      ? "bg-red-950/60 border-red-700/50 text-red-300"
                      : price.rsi < 30
                        ? "bg-emerald-950/60 border-emerald-700/50 text-emerald-300"
                        : "bg-zinc-700/60 border-zinc-600 text-zinc-300",
                  )}
                >
                  RSI {price.rsi.toFixed(1)}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── ThemeSection ──────────────────────────────────────────────────────────────

const THEME_COLORS: Record<string, string> = {
  "AI": "bg-purple-950 border-purple-700/60 text-purple-300",
  "半導體": "bg-blue-950 border-blue-700/60 text-blue-300",
  "電動車": "bg-emerald-950 border-emerald-700/60 text-emerald-300",
  "伺服器": "bg-cyan-950 border-cyan-700/60 text-cyan-300",
  "網通": "bg-teal-950 border-teal-700/60 text-teal-300",
};

const DEFAULT_THEME_COLOR = "bg-zinc-700/60 border-zinc-600 text-zinc-300";

function ThemeSection({ themes }: { themes: string[] }) {
  return (
    <SectionCard title="投資主題">
      {themes.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {themes.map((t) => {
            const colorClass = Object.keys(THEME_COLORS).find((k) => t.includes(k));
            return (
              <span
                key={t}
                className={cn(
                  "text-xs font-medium px-2.5 py-1 rounded-full border",
                  colorClass ? THEME_COLORS[colorClass] : DEFAULT_THEME_COLOR,
                )}
              >
                {t}
              </span>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-zinc-500">無主題標籤</p>
      )}
    </SectionCard>
  );
}

// ── SupplyChainSection ────────────────────────────────────────────────────────

function SupplyChainSection({ supplyChain }: { supplyChain: DeepDiveSupplyChain | null }) {
  if (!supplyChain || (supplyChain.upstream.length === 0 && supplyChain.downstream.length === 0)) {
    return (
      <SectionCard title="供應鏈">
        <p className="text-sm text-zinc-500">無供應鏈資料</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="供應鏈">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <div className="text-xs text-zinc-500 mb-2 font-medium">上游供應商</div>
          {supplyChain.upstream.length > 0 ? (
            <ul className="space-y-1.5">
              {supplyChain.upstream.slice(0, 6).map((n) => (
                <li key={n.ticker}>
                  <Link
                    href={`/stock/${n.ticker}`}
                    className="flex items-center gap-1.5 group"
                  >
                    <span className="text-xs font-mono text-blue-400 group-hover:text-blue-300 transition-colors">
                      {n.ticker}
                    </span>
                    <span className="text-xs text-zinc-400 group-hover:text-zinc-300 truncate transition-colors">
                      {n.name}
                    </span>
                  </Link>
                  {n.role_note && (
                    <span className="text-xs text-zinc-600 ml-0">{n.role_note}</span>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-zinc-600">無資料</p>
          )}
        </div>
        <div>
          <div className="text-xs text-zinc-500 mb-2 font-medium">下游客戶</div>
          {supplyChain.downstream.length > 0 ? (
            <ul className="space-y-1.5">
              {supplyChain.downstream.slice(0, 6).map((n) => (
                <li key={n.ticker}>
                  <Link
                    href={`/stock/${n.ticker}`}
                    className="flex items-center gap-1.5 group"
                  >
                    <span className="text-xs font-mono text-orange-400 group-hover:text-orange-300 transition-colors">
                      {n.ticker}
                    </span>
                    <span className="text-xs text-zinc-400 group-hover:text-zinc-300 truncate transition-colors">
                      {n.name}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-zinc-600">無資料</p>
          )}
        </div>
      </div>
    </SectionCard>
  );
}

// ── RevenueSection ────────────────────────────────────────────────────────────

const TOOLTIP_STYLE = {
  backgroundColor: "#1c1c1e",
  border: "1px solid #3f3f46",
  borderRadius: "8px",
  fontSize: "11px",
  color: "#e4e4e7",
};

function RevenueSection({ revenue }: { revenue: DeepDiveRevenue | null }) {
  if (!revenue || revenue.data.length === 0) {
    return (
      <SectionCard title="月營收">
        <p className="text-sm text-zinc-500">無月營收資料</p>
      </SectionCard>
    );
  }

  const trendColor =
    revenue.trend === "accelerating"
      ? "text-emerald-400 bg-emerald-950/60 border-emerald-700/50"
      : revenue.trend === "decelerating"
        ? "text-red-400 bg-red-950/60 border-red-700/50"
        : "text-zinc-400 bg-zinc-700/60 border-zinc-600";

  return (
    <SectionCard title="月營收">
      <div className="flex items-center gap-2 mb-3">
        <span className={cn("text-xs border px-2 py-0.5 rounded-full font-medium", trendColor)}>
          {revenue.trend === "accelerating"
            ? "加速成長"
            : revenue.trend === "decelerating"
              ? "成長趨緩"
              : "穩定"}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={revenue.data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="year_month"
            tick={{ fontSize: 9, fill: "#71717a" }}
            tickFormatter={(v: string) => v.slice(5)}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fontSize: 9, fill: "#71717a" }} tickFormatter={(v: number) => `${(v / 1e8).toFixed(0)}億`} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value: number, name: string) => [
              `${(value / 1e8).toFixed(2)} 億`,
              name === "revenue" ? "月營收" : name,
            ]}
          />
          <Bar dataKey="revenue" radius={[2, 2, 0, 0]}>
            {revenue.data.map((entry, idx) => (
              <Cell
                key={idx}
                fill={
                  entry.yoy_pct !== null && entry.yoy_pct >= 0
                    ? "#10b981"
                    : "#ef4444"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </SectionCard>
  );
}

// ── InstitutionalSection ──────────────────────────────────────────────────────

function InstitutionalSection({ institutional }: { institutional: DeepDiveInstitutional | null }) {
  if (!institutional || institutional.data.length === 0) {
    return (
      <SectionCard title="三大法人籌碼">
        <p className="text-sm text-zinc-500">無籌碼資料</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="三大法人籌碼">
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={institutional.data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: "#71717a" }}
            tickFormatter={(v: string) => v.slice(5)}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fontSize: 9, fill: "#71717a" }} tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}千`} />
          <ReferenceLine y={0} stroke="#52525b" strokeDasharray="3 3" />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value: number) => [`${value.toLocaleString()} 張`, "合計買賣超"]}
          />
          <Bar dataKey="total_net" radius={[2, 2, 0, 0]}>
            {institutional.data.map((entry, idx) => (
              <Cell key={idx} fill={entry.total_net >= 0 ? "#10b981" : "#ef4444"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </SectionCard>
  );
}

// ── MarginSection ─────────────────────────────────────────────────────────────

function MarginSection({ margin }: { margin: DeepDiveMargin | null }) {
  if (!margin || margin.data.length === 0) {
    return (
      <SectionCard title="融資融券">
        <p className="text-sm text-zinc-500">無融資融券資料</p>
      </SectionCard>
    );
  }

  return (
    <SectionCard title="融資融券">
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={margin.data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 9, fill: "#71717a" }}
            tickFormatter={(v: string) => v.slice(5)}
            interval="preserveStartEnd"
          />
          <YAxis tick={{ fontSize: 9, fill: "#71717a" }} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value: number, name: string) => [
              value.toLocaleString(),
              name === "margin_balance" ? "融資餘額" : "融券餘額",
            ]}
          />
          <Line
            type="monotone"
            dataKey="margin_balance"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={1.5}
          />
          <Line
            type="monotone"
            dataKey="short_balance"
            stroke="#f59e0b"
            dot={false}
            strokeWidth={1.5}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2">
        <span className="text-xs text-blue-400 flex items-center gap-1">
          <span className="w-4 h-0.5 bg-blue-400 inline-block" /> 融資餘額
        </span>
        <span className="text-xs text-amber-400 flex items-center gap-1">
          <span className="w-4 h-0.5 bg-amber-400 inline-block" /> 融券餘額
        </span>
      </div>
    </SectionCard>
  );
}

// ── AnomalySection ────────────────────────────────────────────────────────────

function AnomalySection({ anomalies }: { anomalies: Record<string, unknown>[] }) {
  return (
    <SectionCard title="異常訊號">
      {anomalies.length === 0 ? (
        <p className="text-sm text-zinc-500">無異常訊號</p>
      ) : (
        <ul className="space-y-2">
          {anomalies.slice(0, 5).map((a, i) => {
            const severity = a.severity as string;
            const date = a.date as string;
            const reason = a.reason as string;
            return (
              <li key={i} className="flex items-start gap-2">
                <AlertTriangle
                  className={cn(
                    "h-3.5 w-3.5 mt-0.5 flex-shrink-0",
                    severity === "high" ? "text-red-400" : "text-amber-400",
                  )}
                />
                <div>
                  <span className="text-xs text-zinc-400">{date} </span>
                  <span className="text-xs text-zinc-300">{reason}</span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

// ── CatalystSection ───────────────────────────────────────────────────────────

function CatalystSection({
  catalysts,
  symbol,
}: {
  catalysts: Record<string, unknown>[];
  symbol: string;
}) {
  return (
    <SectionCard title="催化劑事件">
      {catalysts.length === 0 ? (
        <div className="flex items-center justify-between">
          <p className="text-sm text-zinc-500">無催化劑事件</p>
          <Link
            href={`/catalyst?symbol=${symbol}`}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            新增催化劑 →
          </Link>
        </div>
      ) : (
        <ul className="space-y-2">
          {catalysts.slice(0, 6).map((c, i) => {
            const title = c.title as string;
            const eventDate = (c.event_date ?? c.eventDate) as string | null;
            const status = c.status as string;
            const eventType = (c.event_type ?? c.eventType) as string;
            return (
              <li key={i} className="flex items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={cn(
                      "flex-shrink-0 px-1.5 py-0.5 rounded text-xs font-medium border",
                      status === "pending"
                        ? "bg-blue-950/60 border-blue-700/50 text-blue-300"
                        : status === "passed"
                          ? "bg-zinc-700/60 border-zinc-600 text-zinc-400"
                          : "bg-red-950/60 border-red-700/50 text-red-400",
                    )}
                  >
                    {status === "pending" ? "待觀察" : status === "passed" ? "已過" : "取消"}
                  </span>
                  <span className="text-zinc-300 truncate">{title}</span>
                </div>
                <span className="text-zinc-500 flex-shrink-0">{eventDate ?? eventType}</span>
              </li>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}

// ── AIAnalysisSection ─────────────────────────────────────────────────────────

function AIAnalysisSection({ symbol }: { symbol: string }) {
  const mutation = useDeepDiveAIMutation();
  const result = mutation.data as DeepDiveAIAnalysis | undefined;

  return (
    <SectionCard title="J.A.R.V.I.S. 深度分析" className="border-blue-800/40 bg-gradient-to-b from-blue-950/20 to-zinc-800/60">
      {!result && !mutation.isPending && (
        <div className="flex flex-col items-center gap-3 py-4">
          <p className="text-sm text-zinc-400">AI 將整合所有數據，提供結構化投資分析</p>
          <button
            onClick={() => mutation.mutate(symbol)}
            className={cn(
              "flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold",
              "bg-gradient-to-r from-blue-600 to-cyan-600 text-white",
              "hover:from-blue-500 hover:to-cyan-500 transition-all duration-200",
              "shadow-lg shadow-blue-900/40",
            )}
          >
            <Zap className="h-4 w-4" />
            J.A.R.V.I.S. 深度分析
          </button>
        </div>
      )}

      {mutation.isPending && (
        <div className="flex flex-col items-center gap-3 py-6">
          <div className="h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-zinc-400">分析中...</p>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          {result.error ? (
            <p className="text-sm text-red-400">{result.error}</p>
          ) : (
            <>
              {/* Score + signal */}
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <div
                    className={cn(
                      "text-4xl font-bold",
                      result.overall_score >= 7
                        ? "text-emerald-400"
                        : result.overall_score >= 4
                          ? "text-amber-400"
                          : "text-red-400",
                    )}
                  >
                    {result.overall_score}
                  </div>
                  <div className="text-xs text-zinc-500">/ 10</div>
                </div>
                <div>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 text-sm font-semibold px-3 py-1 rounded-full border",
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
                </div>
              </div>

              {/* Summary */}
              <p className="text-sm text-zinc-200 leading-relaxed border-l-2 border-blue-500/60 pl-3">
                {result.summary}
              </p>

              {/* Analysis sections */}
              <div className="grid grid-cols-1 gap-3">
                {result.theme_analysis && (
                  <div>
                    <div className="text-xs text-zinc-500 font-medium mb-1">主題分析</div>
                    <p className="text-xs text-zinc-300 leading-relaxed">{result.theme_analysis}</p>
                  </div>
                )}
                {result.fundamental_analysis && (
                  <div>
                    <div className="text-xs text-zinc-500 font-medium mb-1">基本面</div>
                    <p className="text-xs text-zinc-300 leading-relaxed">{result.fundamental_analysis}</p>
                  </div>
                )}
                {result.timing_analysis && (
                  <div>
                    <div className="text-xs text-zinc-500 font-medium mb-1">時機分析</div>
                    <p className="text-xs text-zinc-300 leading-relaxed">{result.timing_analysis}</p>
                  </div>
                )}
              </div>

              {/* Risks */}
              {result.risks && result.risks.length > 0 && (
                <div>
                  <div className="text-xs text-zinc-500 font-medium mb-2">風險因素</div>
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

              {/* Re-analyze button */}
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
    </SectionCard>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function StockDeepDivePage() {
  const params = useParams();
  const router = useRouter();
  const symbol = typeof params.symbol === "string" ? params.symbol.toUpperCase() : null;

  // Save to recent
  useEffect(() => {
    if (!symbol) return;
    const prev = (() => {
      try {
        return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as string[];
      } catch {
        return [];
      }
    })();
    const next = [symbol, ...prev.filter((t) => t !== symbol)].slice(0, MAX_RECENT);
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  }, [symbol]);

  const { data, isLoading, error } = useDeepDive(symbol);

  return (
    <div className="min-h-screen bg-zinc-900 text-zinc-100">
      <div className="max-w-5xl mx-auto px-4 py-6">
        {/* Back button */}
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
            {/* Header */}
            <StockHeader data={data} />

            {/* Row 1: Themes + Supply Chain */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <ThemeSection themes={data.themes} />
              <SupplyChainSection supplyChain={data.supply_chain} />
            </div>

            {/* Row 2: Revenue + Institutional */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <RevenueSection revenue={data.revenue} />
              <InstitutionalSection institutional={data.institutional} />
            </div>

            {/* Row 3: Margin + Anomaly */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <MarginSection margin={data.margin} />
              <AnomalySection anomalies={data.anomalies} />
            </div>

            {/* Row 4: Catalysts - full width */}
            <CatalystSection catalysts={data.catalysts} symbol={data.symbol} />

            {/* Row 5: AI Analysis - full width */}
            <AIAnalysisSection symbol={data.symbol} />
          </div>
        )}
      </div>
    </div>
  );
}
