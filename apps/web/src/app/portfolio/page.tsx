"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState, useMemo } from "react";
import {
  useEquitySnapshot,
  useEquityCurve,
  usePositions,
  useEquityDaily,
  useQuotesTodo,
  usePerfSummary,
  useRiskMetrics,
  useRebalanceCheck,
  useAttribution,
  useDigestList,
  useBenchmarkCompare,
} from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { TimeRangePicker, toParams, type Range, type RangeParams } from "@/components/time-range-picker";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtMoney, fmtPct, pnlClass } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DailyMode, DailyUnit } from "@/components/charts/daily-pnl-chart";
import type { RebalanceAlert } from "@/lib/types";

const EquityLineChart = dynamic(
  () => import("@/components/charts/equity-line-chart").then((m) => m.EquityLineChart),
  { ssr: false, loading: () => <Skeleton className="h-[300px] w-full" /> },
);
const StackedAreaChart = dynamic(
  () => import("@/components/charts/stacked-area-chart").then((m) => m.StackedAreaChart),
  { ssr: false, loading: () => <Skeleton className="h-[260px] w-full" /> },
);
const DonutChart = dynamic(
  () => import("@/components/charts/donut-chart").then((m) => m.DonutChart),
  { ssr: false, loading: () => <Skeleton className="h-[240px] w-full" /> },
);
const DailyPnlChart = dynamic(
  () => import("@/components/charts/daily-pnl-chart").then((m) => m.DailyPnlChart),
  { ssr: false, loading: () => <Skeleton className="h-[280px] w-full" /> },
);
const BenchmarkCompareChart = dynamic(
  () => import("@/components/charts/benchmark-compare-chart").then((m) => m.BenchmarkCompareChart),
  { ssr: false, loading: () => <Skeleton className="h-[280px] w-full" /> },
);

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatCard({
  title,
  value,
  sub,
  valueClass,
}: {
  title: string;
  value: string;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold tabular-nums ${valueClass ?? ""}`}>{value}</div>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label?: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {label && <span className="text-muted-foreground">{label}</span>}
      <div className="inline-flex rounded-md border bg-background overflow-hidden">
        {options.map((opt, i) => (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={cn(
              "px-3 py-1.5 transition-colors",
              i > 0 && "border-l",
              value === opt.value
                ? "bg-primary text-primary-foreground"
                : "hover:bg-muted text-foreground",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ── To-Do Banner ──────────────────────────────────────────────────────────────

function TodoBanner() {
  const today = new Date().toISOString().slice(0, 10);
  const todo = useQuotesTodo({ asOf: today, staleDays: 2 });

  if (todo.isLoading || todo.isError || !todo.data?.length) return null;

  const items = todo.data;
  const visible = items.slice(0, 5);
  const extra = items.length - visible.length;

  return (
    <div className="flex flex-wrap items-center gap-2 p-3 rounded-lg border border-yellow-300 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-950/30 text-sm">
      <span className="font-medium text-yellow-800 dark:text-yellow-300 shrink-0">
        Missing/stale quotes:
      </span>
      {visible.map((item) => (
        <Link
          key={item.symbol}
          href={`/quotes?symbol=${item.symbol}`}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-yellow-200 dark:bg-yellow-800 text-yellow-900 dark:text-yellow-100 font-mono text-xs hover:bg-yellow-300 dark:hover:bg-yellow-700 transition-colors"
        >
          {item.symbol}
          {item.stalenessDays != null && (
            <span className="opacity-70">({item.stalenessDays}d)</span>
          )}
        </Link>
      ))}
      {extra > 0 && (
        <span className="text-yellow-700 dark:text-yellow-400 text-xs">+{extra} more</span>
      )}
      <Link
        href="/quotes"
        className="ml-auto shrink-0 px-3 py-1 rounded-md bg-yellow-600 text-white text-xs font-medium hover:bg-yellow-700 transition-colors"
      >
        Go to Quotes
      </Link>
    </div>
  );
}

// ── Rebalance Alerts ──────────────────────────────────────────────────────────

const SEVERITY_STYLES: Record<RebalanceAlert["severity"], string> = {
  warning: "border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300",
  info: "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300",
  error: "border-red-500 bg-red-100 text-red-900 dark:border-red-700 dark:bg-red-950/50 dark:text-red-200",
};

function RebalanceAlerts() {
  const today = new Date().toISOString().slice(0, 10);
  const check = useRebalanceCheck(today);

  if (check.isLoading || check.isError || !check.data?.alerts.length) return null;

  return (
    <div className="space-y-2">
      {check.data.alerts.map((alert, i) => (
        <div
          key={i}
          className={cn("flex items-start gap-2 p-3 rounded-lg border text-sm", SEVERITY_STYLES[alert.severity])}
        >
          <span className="font-medium shrink-0">
            {alert.severity === "warning" ? "⚠" : "ℹ"}
          </span>
          <span>{alert.message}</span>
          {(alert.type === "stale_quotes" || alert.type === "concentration") && (
            <Link
              href={alert.type === "stale_quotes" ? "/quotes" : "/positions"}
              className="ml-auto shrink-0 text-xs underline opacity-80 hover:opacity-100"
            >
              View →
            </Link>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Performance + Risk Section ────────────────────────────────────────────────

function PerfRiskSection({ start, end }: { start: string; end: string }) {
  const perf = usePerfSummary({ start, end });
  const risk = useRiskMetrics({ start, end });

  const isLoading = perf.isLoading || risk.isLoading;

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="pt-4">
              <Skeleton className="h-4 w-20 mb-2" />
              <Skeleton className="h-6 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const p = perf.data;
  const r = risk.data;
  const fmt = (v: number | null | undefined, decimals = 0) =>
    v == null ? "N/A" : `$${fmtMoney(v, decimals)}`;
  const fmtP = (v: number | null | undefined) =>
    v == null ? "N/A" : fmtPct(v);

  const perfCards = [
    { title: "P&L (ex-cashflow)", value: fmt(p?.pnlExCashflow), valueClass: pnlClass(p?.pnlExCashflow) },
    { title: "Realized P&L", value: fmt(p?.realizedPnl), valueClass: pnlClass(p?.realizedPnl) },
    { title: "Unrealized P&L", value: fmt(p?.unrealizedPnl), valueClass: pnlClass(p?.unrealizedPnl) },
    { title: "Fees (Commission)", value: fmt(p?.feesCommission), sub: `Tax: ${fmt(p?.feesTax)}` },
    { title: "Net Cashflow", value: fmt(p?.externalCashflowSum) },
  ];

  const riskCards = [
    { title: "Sharpe Ratio", value: r?.sharpeRatio != null ? r.sharpeRatio.toFixed(2) : "N/A", sub: "annualised, rf=0" },
    { title: "Win Rate", value: r?.positiveDayRatio != null ? `${r.positiveDayRatio.toFixed(1)}%` : "N/A", sub: "positive days" },
    { title: "Best Day", value: fmtP(r?.bestDayPct), valueClass: "text-green-600 dark:text-green-400" },
    { title: "Worst Day", value: fmtP(r?.worstDayPct), valueClass: "text-red-600 dark:text-red-400" },
    { title: "Daily Vol", value: r?.volatilityPct != null ? `${r.volatilityPct.toFixed(2)}%` : "N/A" },
    { title: "Trading Days", value: r?.tradingDays != null ? String(r.tradingDays) : "N/A" },
  ];

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Performance</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {perfCards.map((c) => (
          <Card key={c.title}>
            <CardHeader className="pb-1 pt-3 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground">{c.title}</CardTitle>
            </CardHeader>
            <CardContent className="pb-3 px-4">
              <div className={cn("text-lg font-bold tabular-nums", c.valueClass)}>{c.value}</div>
              {c.sub && <p className="text-xs text-muted-foreground mt-0.5">{c.sub}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
      <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">Risk</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {riskCards.map((c) => (
          <Card key={c.title}>
            <CardHeader className="pb-1 pt-3 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground">{c.title}</CardTitle>
            </CardHeader>
            <CardContent className="pb-3 px-4">
              <div className={cn("text-lg font-bold tabular-nums", c.valueClass)}>{c.value}</div>
              {c.sub && <p className="text-xs text-muted-foreground mt-0.5">{c.sub}</p>}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ── Top Contributors ──────────────────────────────────────────────────────────

function TopContributors({ start, end }: { start: string; end: string }) {
  const attr = useAttribution({ start, end, topN: 5 });

  if (attr.isLoading) return <Skeleton className="h-32 w-full" />;
  if (attr.isError || !attr.data) return null;

  const { topGainers, topLosers, totalPnl } = attr.data;
  const all = [...topGainers, ...topLosers.filter((l) => !topGainers.find((g) => g.symbol === l.symbol))];
  if (!all.length) return null;

  return (
    <div className="grid md:grid-cols-2 gap-4">
      {[
        { title: "Top Contributors", items: topGainers, positive: true },
        { title: "Top Detractors",   items: topLosers,  positive: false },
      ].map(({ title, items, positive }) => (
        <Card key={title}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex justify-between">
              <span>{title}</span>
              <span className="text-xs text-muted-foreground font-normal">
                Total P&L: <span className={pnlClass(totalPnl)}>${fmtMoney(totalPnl)}</span>
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {items.map((item) => (
                <li key={item.symbol} className="flex items-center justify-between px-4 py-2 text-sm hover:bg-muted/30 transition-colors">
                  <Link
                    href={`/positions?symbol=${item.symbol}`}
                    className="font-mono font-medium hover:underline"
                  >
                    {item.symbol}
                  </Link>
                  <div className="text-right">
                    <span className={`font-semibold tabular-nums ${pnlClass(item.contribution)}`}>
                      {item.contribution >= 0 ? "+" : ""}${fmtMoney(item.contribution)}
                    </span>
                    {item.contributionPct != null && (
                      <span className="ml-1.5 text-xs text-muted-foreground">
                        ({item.contributionPct.toFixed(1)}%)
                      </span>
                    )}
                  </div>
                </li>
              ))}
              {!items.length && (
                <li className="px-4 py-3 text-xs text-muted-foreground text-center">No data</li>
              )}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ── Latest Digest Banner ──────────────────────────────────────────────────────

function LatestDigestBanner() {
  const list = useDigestList({ limit: 1 });
  const latest = list.data?.[0];
  if (!latest) return null;

  return (
    <div className="flex items-center justify-between p-3 rounded-lg border border-border bg-muted/40 text-sm">
      <div className="flex items-center gap-3">
        <span className="font-medium">Latest Digest</span>
        <span className="text-muted-foreground">{latest.date}</span>
        {latest.dailyPnl != null && (
          <span className={`tabular-nums font-semibold ${pnlClass(latest.dailyPnl)}`}>
            {latest.dailyPnl >= 0 ? "+" : ""}${fmtMoney(latest.dailyPnl)}
            {latest.dailyReturnPct != null && (
              <span className="ml-1 text-xs font-normal opacity-80">
                ({latest.dailyReturnPct >= 0 ? "+" : ""}{latest.dailyReturnPct.toFixed(2)}%)
              </span>
            )}
          </span>
        )}
      </div>
      <Link
        href="/digest"
        className="px-3 py-1 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        View Digest →
      </Link>
    </div>
  );
}

// ── Benchmark Section ─────────────────────────────────────────────────────────

const BENCH_OPTIONS = ["0050", "SPY", "QQQ", "TAIEX"] as const;

function BenchmarkSection({ start, end, freq }: { start: string; end: string; freq: string }) {
  const [bench, setBench] = useState<string>("0050");
  const params = useMemo(
    () => ({ bench, start, end, freq }),
    [bench, start, end, freq],
  );
  const compare = useBenchmarkCompare(params);

  const hasData = (compare.data?.records?.length ?? 0) > 0;
  const metrics = compare.data?.metrics;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Benchmark</h2>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground">vs.</span>
          <div className="inline-flex rounded-md border bg-background overflow-hidden text-xs font-medium">
            {BENCH_OPTIONS.map((opt, i) => (
              <button
                key={opt}
                onClick={() => setBench(opt)}
                className={cn(
                  "px-3 py-1.5 transition-colors",
                  i > 0 && "border-l",
                  bench === opt
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-muted text-foreground",
                )}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>
      </div>

      {compare.isLoading && <Skeleton className="h-[280px] w-full rounded-lg" />}

      {!compare.isLoading && !hasData && (
        <Card>
          <CardContent className="py-10 text-center space-y-3">
            <p className="text-muted-foreground text-sm">
              No price data found for{" "}
              <span className="font-mono font-medium">{bench}</span> in this date range.
            </p>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              Bootstrap historical benchmark data (2016→today) in one click.
            </p>
            <Link
              href="/settings#benchmark"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              Bootstrap Benchmark Data →
            </Link>
          </CardContent>
        </Card>
      )}

      {hasData && (
        <>
          <Card>
            <CardContent className="pt-4">
              <BenchmarkCompareChart
                data={compare.data!.records}
                bench={bench}
                freq={freq}
              />
            </CardContent>
          </Card>

          {metrics && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                {
                  title: "Excess Return",
                  value: metrics.excessReturnPct != null ? fmtPct(metrics.excessReturnPct) : "N/A",
                  sub: "cumulative vs benchmark",
                  valueClass: pnlClass(metrics.excessReturnPct),
                },
                {
                  title: "Tracking Error",
                  value: metrics.trackingErrorAnnualized != null
                    ? `${metrics.trackingErrorAnnualized.toFixed(2)}%`
                    : "N/A",
                  sub: "annualised",
                },
                {
                  title: "Correlation",
                  value: metrics.correlation != null
                    ? metrics.correlation.toFixed(3)
                    : "N/A",
                  sub: "period returns",
                },
                {
                  title: "Info. Ratio",
                  value: metrics.informationRatio != null
                    ? metrics.informationRatio.toFixed(3)
                    : "N/A",
                  sub: "annualised excess / TE",
                  valueClass: pnlClass(metrics.informationRatio),
                },
              ].map((c) => (
                <Card key={c.title}>
                  <CardHeader className="pb-1 pt-3 px-4">
                    <CardTitle className="text-xs font-medium text-muted-foreground">
                      {c.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="pb-3 px-4">
                    <div className={cn("text-lg font-bold tabular-nums", c.valueClass)}>
                      {c.value}
                    </div>
                    {c.sub && (
                      <p className="text-xs text-muted-foreground mt-0.5">{c.sub}</p>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const [range, setRange] = useState<Range>("1Y");
  const [curveParams, setCurveParams] = useState<RangeParams>(() => toParams("1Y"));

  const [dailyMode, setDailyMode] = useState<DailyMode>("pnl");
  const [dailyUnit, setDailyUnit] = useState<DailyUnit>("twd");
  const [dailyFreq, setDailyFreq] = useState<"B" | "D">("B");

  const snapshot = useEquitySnapshot();
  const curve = useEquityCurve(curveParams);
  const positions = usePositions({ includeClosed: false });
  const daily = useEquityDaily({
    start: curveParams.start,
    end: curveParams.end,
    freq: dailyFreq,
  });

  const snap = snapshot.data;
  const lastPoint = curve.data?.at(-1);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Portfolio</h1>

      {/* Alerts row: To-Do + Rebalance + Digest Banner */}
      <div className="space-y-2">
        <TodoBanner />
        <RebalanceAlerts />
        <LatestDigestBanner />
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {snapshot.isLoading ? (
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <Skeleton className="h-4 w-24" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-8 w-32" />
              </CardContent>
            </Card>
          ))
        ) : snapshot.isError ? (
          <p className="col-span-4 text-destructive text-sm">Failed to load snapshot</p>
        ) : (
          <>
            <StatCard title="Total Equity" value={`$${fmtMoney(snap?.totalEquity)}`} />
            <StatCard title="Cash" value={`$${fmtMoney(snap?.cash)}`} />
            <StatCard title="Market Value" value={`$${fmtMoney(snap?.marketValue)}`} />
            <StatCard
              title="Cum. Return"
              value={lastPoint?.cumReturnPct != null ? fmtPct(lastPoint.cumReturnPct) : "N/A"}
              valueClass={pnlClass(lastPoint?.cumReturnPct)}
            />
          </>
        )}
      </div>

      {/* Daily P&L */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Daily P&L</h2>
          <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
            <ToggleGroup<DailyMode>
              options={[
                { value: "pnl",   label: "P&L (ex cashflow)" },
                { value: "delta", label: "ΔEquity" },
              ]}
              value={dailyMode}
              onChange={setDailyMode}
            />
            <ToggleGroup<DailyUnit>
              options={[
                { value: "twd", label: "TWD" },
                { value: "pct", label: "%"   },
              ]}
              value={dailyUnit}
              onChange={setDailyUnit}
            />
            <ToggleGroup<"B" | "D">
              options={[
                { value: "B", label: "Weekdays" },
                { value: "D", label: "All Days"  },
              ]}
              value={dailyFreq}
              onChange={setDailyFreq}
            />
          </div>
        </div>

        {daily.isLoading ? (
          <Skeleton className="h-[280px] w-full rounded-lg" />
        ) : daily.isError ? (
          <Card>
            <p className="p-6 text-center text-destructive text-sm">Failed to load daily data</p>
          </Card>
        ) : (
          <Card>
            <CardContent className="pt-6">
              <DailyPnlChart
                data={daily.data ?? []}
                mode={dailyMode}
                unit={dailyUnit}
                freq={dailyFreq}
              />
            </CardContent>
          </Card>
        )}
      </div>

      {/* Time range + Charts */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Equity Curve</h2>
          <TimeRangePicker
            value={range}
            onChange={(r, p) => {
              setRange(r);
              setCurveParams(p);
            }}
          />
        </div>

        {curve.isLoading ? (
          <Skeleton className="h-[300px] w-full rounded-lg" />
        ) : (
          <Card>
            <CardContent className="pt-6">
              <EquityLineChart data={curve.data ?? []} freq={curveParams.freq} />
            </CardContent>
          </Card>
        )}

        <div className="grid md:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Cash vs Market Value</CardTitle>
            </CardHeader>
            <CardContent>
              {curve.isLoading ? (
                <Skeleton className="h-[260px]" />
              ) : (
                <StackedAreaChart data={curve.data ?? []} freq={curveParams.freq} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Asset Allocation</CardTitle>
            </CardHeader>
            <CardContent>
              {snapshot.isLoading ? (
                <Skeleton className="h-[240px]" />
              ) : (
                <DonutChart
                  cash={snap?.cash ?? 0}
                  positions={snap?.positions ?? {}}
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Top Contributors */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Top Contributors</h2>
        <TopContributors start={curveParams.start} end={curveParams.end} />
      </div>

      {/* Performance & Risk */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Performance & Risk</h2>
          <span className="text-xs text-muted-foreground">{curveParams.start} → {curveParams.end}</span>
        </div>
        <PerfRiskSection start={curveParams.start} end={curveParams.end} />
      </div>

      {/* Benchmark Comparison */}
      <BenchmarkSection
        start={curveParams.start}
        end={curveParams.end}
        freq={curveParams.freq}
      />

      {/* Positions table */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold">Open Positions</h2>
        <Card>
          {positions.isLoading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : positions.isError ? (
            <p className="p-4 text-destructive text-sm">Failed to load positions</p>
          ) : !positions.data?.length ? (
            <p className="p-6 text-center text-muted-foreground text-sm">No open positions</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead className="text-right">Avg Cost</TableHead>
                  <TableHead className="text-right">Last Price</TableHead>
                  <TableHead className="text-right">Market Value</TableHead>
                  <TableHead className="text-right">Unrealized P&L</TableHead>
                  <TableHead className="text-right">Realized P&L</TableHead>
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.data.map((p) => {
                  const pnlPct =
                    p.avgCost && p.lastPrice
                      ? ((p.lastPrice - p.avgCost) / p.avgCost) * 100
                      : null;
                  return (
                    <TableRow key={p.symbol}>
                      <TableCell>
                        <Badge variant="secondary">{p.symbol}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{p.qty}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmtMoney(p.avgCost, 4)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmtMoney(p.lastPrice, 4)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {fmtMoney(p.marketValue)}
                      </TableCell>
                      <TableCell className={`text-right tabular-nums ${pnlClass(p.unrealizedPnl)}`}>
                        {fmtMoney(p.unrealizedPnl)}
                        {pnlPct != null && (
                          <span className="text-xs ml-1 opacity-70">({fmtPct(pnlPct)})</span>
                        )}
                      </TableCell>
                      <TableCell className={`text-right tabular-nums ${pnlClass(p.realizedPnl)}`}>
                        {fmtMoney(p.realizedPnl)}
                      </TableCell>
                      <TableCell>
                        {p.priceSource ? (
                          <span className="text-xs text-muted-foreground">{p.priceSource}</span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </Card>
      </div>
    </div>
  );
}
