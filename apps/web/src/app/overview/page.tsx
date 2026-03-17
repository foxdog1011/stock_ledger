"use client";

import { useState } from "react";
import Link from "next/link";
import { RefreshCw, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useOverview } from "@/hooks/use-queries";
import { fmtMoney, fmtPct, pnlClass } from "@/lib/format";
import type {
  OverviewRiskPosition,
  OverviewWatchlistItem,
  OverviewCatalystItem,
} from "@/lib/types";

// ── helpers ──────────────────────────────────────────────────────────────────

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function SectionSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <p className="text-sm text-muted-foreground italic py-2">{message}</p>
  );
}

// ── A. Portfolio summary ──────────────────────────────────────────────────────

function PortfolioSection({ data }: { data: ReturnType<typeof useOverview>["data"] }) {
  if (!data) return <SectionSkeleton />;
  const p = data.portfolio;
  const rows = [
    { label: "Total Equity",    value: fmtMoney(p.totalEquity),    cls: "" },
    { label: "Cash",            value: fmtMoney(p.cash),            cls: "" },
    { label: "Market Value",    value: fmtMoney(p.marketValue),     cls: "" },
    { label: "Total Cost",      value: fmtMoney(p.totalCost),       cls: "" },
    { label: "Unrealized P&L",  value: p.unrealizedPnl != null
        ? `${fmtMoney(p.unrealizedPnl)} (${fmtPct(p.unrealizedPct)})`
        : "—",
      cls: pnlClass(p.unrealizedPnl) },
    { label: "Realized P&L",    value: fmtMoney(p.realizedPnl),    cls: pnlClass(p.realizedPnl) },
    { label: "Open Positions",  value: String(p.positionCount),    cls: "" },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {rows.map(({ label, value, cls }) => (
        <div key={label} className="rounded-lg border bg-card p-3">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={`text-sm font-semibold mt-0.5 ${cls}`}>{value}</p>
        </div>
      ))}
    </div>
  );
}

// ── B. Risk summary ───────────────────────────────────────────────────────────

function RiskSection({ data }: { data: ReturnType<typeof useOverview>["data"] }) {
  if (!data) return <SectionSkeleton />;
  const r = data.risk;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <div className="rounded-lg border bg-card p-3 min-w-[120px]">
          <p className="text-xs text-muted-foreground">At Risk</p>
          <p className="text-sm font-semibold text-red-500">{r.atRiskCount}</p>
        </div>
        <div className="rounded-lg border bg-card p-3 min-w-[120px]">
          <p className="text-xs text-muted-foreground">Risk Free</p>
          <p className="text-sm font-semibold text-emerald-600">{r.riskFreeCount}</p>
        </div>
        <div className="rounded-lg border bg-card p-3 min-w-[140px]">
          <p className="text-xs text-muted-foreground">Total Net At Risk</p>
          <p className={`text-sm font-semibold ${pnlClass(r.totalNetAtRisk)}`}>
            {r.totalNetAtRisk != null ? fmtMoney(r.totalNetAtRisk) : "—"}
          </p>
        </div>
      </div>

      {r.positions.length === 0 ? (
        <EmptyState message="No open positions." />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Symbol</TableHead>
              <TableHead>State</TableHead>
              <TableHead className="text-right">Net At Risk</TableHead>
              <TableHead className="text-right">% Recovered</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {r.positions.map((pos: OverviewRiskPosition) => (
              <TableRow key={pos.symbol}>
                <TableCell className="font-mono font-medium">
                  <Link href={`/lots/${pos.symbol}`} className="hover:underline text-primary">
                    {pos.symbol}
                  </Link>
                </TableCell>
                <TableCell>
                  {pos.positionState === "risk_free" ? (
                    <Badge variant="outline" className="text-emerald-600 border-emerald-300">
                      <CheckCircle2 className="h-3 w-3 mr-1" /> Risk Free
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-red-500 border-red-300">
                      <XCircle className="h-3 w-3 mr-1" /> At Risk
                    </Badge>
                  )}
                </TableCell>
                <TableCell className={`text-right ${pnlClass(pos.netAtRisk)}`}>
                  {pos.netAtRisk != null ? fmtMoney(pos.netAtRisk) : "—"}
                </TableCell>
                <TableCell className="text-right text-muted-foreground">
                  {pos.pctRecovered != null ? fmtPct(pos.pctRecovered) : "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

// ── C. Watchlist coverage ─────────────────────────────────────────────────────

function WatchlistSection({ data }: { data: ReturnType<typeof useOverview>["data"] }) {
  if (!data) return <SectionSkeleton />;
  const wc = data.watchlistCoverage;

  if (wc.watchlists.length === 0) {
    return <EmptyState message="No watchlists found. Create one to track coverage." />;
  }

  return (
    <div className="space-y-3">
      {wc.anyInsufficient && (
        <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 rounded-md px-3 py-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          One or more watchlists have insufficient coverage (requires 3× open positions).
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Watchlist</TableHead>
            <TableHead className="text-right">Items</TableHead>
            <TableHead className="text-right">Required</TableHead>
            <TableHead className="text-right">Gap</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {wc.watchlists.map((w: OverviewWatchlistItem) => (
            <TableRow key={w.watchlistId}>
              <TableCell className="font-medium">{w.watchlistName}</TableCell>
              <TableCell className="text-right">{w.currentActiveItemCount}</TableCell>
              <TableCell className="text-right text-muted-foreground">{w.requiredWatchlistCount}</TableCell>
              <TableCell className={`text-right ${w.gap > 0 ? "text-red-500 font-semibold" : "text-muted-foreground"}`}>
                {w.gap > 0 ? `−${w.gap}` : "—"}
              </TableCell>
              <TableCell>
                {w.coverageSufficient ? (
                  <Badge variant="outline" className="text-emerald-600 border-emerald-300">OK</Badge>
                ) : (
                  <Badge variant="outline" className="text-red-500 border-red-300">Insufficient</Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ── D. Upcoming catalysts ─────────────────────────────────────────────────────

const EVENT_TYPE_COLORS: Record<string, string> = {
  company: "bg-blue-100 text-blue-800",
  macro:   "bg-purple-100 text-purple-800",
  sector:  "bg-orange-100 text-orange-800",
};

function CatalystsSection({ data }: { data: ReturnType<typeof useOverview>["data"] }) {
  if (!data) return <SectionSkeleton />;
  const uc = data.upcomingCatalysts;

  if (uc.count === 0) {
    return <EmptyState message={`No pending catalysts in the next ${uc.daysWindow} days.`} />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Date</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Symbol</TableHead>
          <TableHead>Title</TableHead>
          <TableHead>Scenario</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {uc.items.map((item: OverviewCatalystItem) => (
          <TableRow key={item.id}>
            <TableCell className="font-mono text-sm whitespace-nowrap">{item.eventDate}</TableCell>
            <TableCell>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${EVENT_TYPE_COLORS[item.eventType] ?? "bg-gray-100 text-gray-700"}`}>
                {item.eventType}
              </span>
            </TableCell>
            <TableCell className="font-mono">{item.symbol ?? "—"}</TableCell>
            <TableCell className="max-w-[200px] truncate">{item.title}</TableCell>
            <TableCell>
              {item.hasScenario ? (
                <Badge variant="outline" className="text-emerald-600 border-emerald-300 text-xs">Yes</Badge>
              ) : (
                <span className="text-xs text-muted-foreground">—</span>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

// ── E. Offsetting summary ─────────────────────────────────────────────────────

function OffsettingSection({ data }: { data: ReturnType<typeof useOverview>["data"] }) {
  if (!data) return <SectionSkeleton />;
  const o = data.offsetting;
  const rows = [
    { label: "Losing Positions",      value: String(o.losingCount),                      cls: o.losingCount > 0 ? "text-red-500" : "" },
    { label: "Total Unrealized Loss",  value: fmtMoney(o.totalUnrealizedLoss),            cls: pnlClass(o.totalUnrealizedLoss) },
    { label: "Profit Available",       value: fmtMoney(o.profitAvailable),                cls: pnlClass(o.profitAvailable) },
    { label: "Net Offset Capacity",    value: fmtMoney(o.netOffsetCapacity),              cls: pnlClass(o.netOffsetCapacity) },
  ];
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {rows.map(({ label, value, cls }) => (
        <div key={label} className="rounded-lg border bg-card p-3">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={`text-sm font-semibold mt-0.5 ${cls}`}>{value}</p>
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const [asOf, setAsOf]               = useState<string>(today());
  const [catalystDays, setCatalystDays] = useState<number>(30);

  const { data, isLoading, isError, error, refetch, isFetching } = useOverview({
    asOf,
    catalystDays,
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

      {/* Header + controls */}
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <h1 className="text-xl font-semibold">Overview</h1>
          {data && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Generated {data.generatedAt.replace("T", " ")}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <label className="text-sm text-muted-foreground whitespace-nowrap">As of</label>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="text-sm border rounded-md px-2 py-1 bg-background"
          />
          <label className="text-sm text-muted-foreground whitespace-nowrap">Catalyst days</label>
          <input
            type="number"
            min={0}
            max={365}
            value={catalystDays}
            onChange={(e) => setCatalystDays(Number(e.target.value))}
            className="text-sm border rounded-md px-2 py-1 bg-background w-16"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-md px-4 py-3">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          Failed to load overview:{" "}
          {error instanceof Error ? error.message : "Unknown error"}
        </div>
      )}

      {/* A. Portfolio */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Portfolio Summary</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <PortfolioSection data={data} />}
        </CardContent>
      </Card>

      {/* B. Risk */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Risk Summary</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <RiskSection data={data} />}
        </CardContent>
      </Card>

      {/* C. Watchlist Coverage */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Watchlist Coverage</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <WatchlistSection data={data} />}
        </CardContent>
      </Card>

      {/* D. Upcoming Catalysts */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Upcoming Catalysts</CardTitle>
            {data && (
              <span className="text-xs text-muted-foreground">
                {data.upcomingCatalysts.count} in next {data.upcomingCatalysts.daysWindow} days
              </span>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <CatalystsSection data={data} />}
        </CardContent>
      </Card>

      {/* E. Offsetting */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Offsetting Summary</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <OffsettingSection data={data} />}
        </CardContent>
      </Card>

    </div>
  );
}
