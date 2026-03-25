"use client";

export const dynamic = "force-dynamic";

import { useState } from "react";
import Link from "next/link";
import { RefreshCw, AlertTriangle, CheckCircle2, XCircle, RotateCcw, PieChart } from "lucide-react";
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
import { useOverview, useRollingLogSummary, useSectorCheck } from "@/hooks/use-queries";
import { fmtMoney, fmtPct, pnlClass } from "@/lib/format";
import { cn } from "@/lib/utils";
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
    { label: "總資產",    value: fmtMoney(p.totalEquity),    cls: "" },
    { label: "現金",            value: fmtMoney(p.cash),            cls: "" },
    { label: "市值",    value: fmtMoney(p.marketValue),     cls: "" },
    { label: "總成本",      value: fmtMoney(p.totalCost),       cls: "" },
    { label: "未實現損益",  value: p.unrealizedPnl != null
        ? `${fmtMoney(p.unrealizedPnl)} (${fmtPct(p.unrealizedPct)})`
        : "—",
      cls: pnlClass(p.unrealizedPnl) },
    { label: "已實現損益",    value: fmtMoney(p.realizedPnl),    cls: pnlClass(p.realizedPnl) },
    { label: "持倉數量",  value: String(p.positionCount),    cls: "" },
  ];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {rows.map(({ label, value, cls }) => (
          <div key={label} className="rounded-lg border bg-card p-3">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={`text-sm font-semibold mt-0.5 ${cls}`}>{value}</p>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        ※ 組合含台股（TWD）與美股（USD）混合幣別，數字未做匯率換算。
      </p>
    </div>
  );
}

// ── B. Risk summary ───────────────────────────────────────────────────────────

function RiskSection({ data }: { data: ReturnType<typeof useOverview>["data"] }) {
  if (!data) return <SectionSkeleton />;
  const r = data.risk;
  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        「風險中」= 持倉尚未透過已實現獲利回收成本；「已無風險」= 已實現獲利 ≥ 淨投入成本。
      </p>
      <div className="flex flex-wrap gap-3">
        <div className="rounded-lg border bg-card p-3 min-w-[120px]">
          <p className="text-xs text-muted-foreground">風險中</p>
          <p className="text-sm font-semibold text-red-500">{r.atRiskCount}</p>
        </div>
        <div className="rounded-lg border bg-card p-3 min-w-[120px]">
          <p className="text-xs text-muted-foreground">已無風險</p>
          <p className="text-sm font-semibold text-emerald-600">{r.riskFreeCount}</p>
        </div>
        <div className="rounded-lg border bg-card p-3 min-w-[140px]">
          <p className="text-xs text-muted-foreground">淨風險金額</p>
          <p className={`text-sm font-semibold ${pnlClass(r.totalNetAtRisk)}`}>
            {r.totalNetAtRisk != null ? fmtMoney(r.totalNetAtRisk) : "—"}
          </p>
        </div>
      </div>

      {r.positions.length === 0 ? (
        <EmptyState message="目前無持倉。" />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>代號</TableHead>
              <TableHead>狀態</TableHead>
              <TableHead className="text-right">淨風險金額</TableHead>
              <TableHead className="text-right">已回收 %</TableHead>
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
                      <CheckCircle2 className="h-3 w-3 mr-1" /> 無風險
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-red-500 border-red-300">
                      <XCircle className="h-3 w-3 mr-1" /> 風險中
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
    return <EmptyState message="尚無觀察清單，請先建立一個。" />;
  }

  return (
    <div className="space-y-3">
      {wc.anyInsufficient && (
        <div className="flex items-center gap-2 text-sm text-amber-600 bg-amber-50 rounded-md px-3 py-2">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          一個或多個觀察清單的涵蓋率不足（需達持倉數量 3 倍）。
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>觀察清單</TableHead>
            <TableHead className="text-right">項目數</TableHead>
            <TableHead className="text-right">需求數</TableHead>
            <TableHead className="text-right">缺口</TableHead>
            <TableHead>狀態</TableHead>
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
                  <Badge variant="outline" className="text-emerald-600 border-emerald-300">充足</Badge>
                ) : (
                  <Badge variant="outline" className="text-red-500 border-red-300">不足</Badge>
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
    return <EmptyState message={`未來 ${uc.daysWindow} 天內無待處理催化劑。`} />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>日期</TableHead>
          <TableHead>類型</TableHead>
          <TableHead>代號</TableHead>
          <TableHead>標題</TableHead>
          <TableHead>情境</TableHead>
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
                <Badge variant="outline" className="text-emerald-600 border-emerald-300 text-xs">有</Badge>
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
    { label: "虧損部位",      value: String(o.losingCount),                      cls: o.losingCount > 0 ? "text-red-500" : "" },
    { label: "未實現虧損合計",  value: fmtMoney(o.totalUnrealizedLoss),            cls: pnlClass(o.totalUnrealizedLoss) },
    { label: "可用獲利",       value: fmtMoney(o.profitAvailable),                cls: pnlClass(o.profitAvailable) },
    { label: "淨對沖空間",    value: fmtMoney(o.netOffsetCapacity),              cls: pnlClass(o.netOffsetCapacity) },
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

// ── F. Rolling + Sector summary (Jimmy methodology) ──────────────────────────

function JimmySection() {
  const { data: rolling, isLoading: rollingLoading } = useRollingLogSummary();
  const { data: sector, isLoading: sectorLoading } = useSectorCheck();

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Rolling cumulative P&L */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <RotateCcw className="h-4 w-4 text-blue-500" />
            Rolling 累積獲利
          </CardTitle>
        </CardHeader>
        <CardContent>
          {rollingLoading ? (
            <Skeleton className="h-10 w-32" />
          ) : (
            <div className="flex items-end gap-4">
              <div>
                <p className={cn("text-2xl font-bold font-mono",
                  (rolling?.grandTotalProfit ?? 0) >= 0 ? "text-emerald-600" : "text-red-500"
                )}>
                  {rolling?.grandTotalProfit != null
                    ? `${rolling.grandTotalProfit >= 0 ? "+" : ""}${fmtMoney(rolling.grandTotalProfit)}`
                    : "—"}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {rolling?.totalRolls ?? 0} 次 rolling
                </p>
              </div>
              {rolling?.bySymbol && rolling.bySymbol.length > 0 && (
                <div className="flex flex-wrap gap-1.5 ml-auto">
                  {rolling.bySymbol.slice(0, 5).map((s) => (
                    <span key={s.symbol} className="text-xs px-2 py-0.5 rounded-full bg-muted font-mono">
                      {s.symbol} {s.totalProfit >= 0 ? "+" : ""}{fmtMoney(s.totalProfit)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Sector rotation */}
      <Card className={sector?.alert ? "border-amber-400" : ""}>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <PieChart className="h-4 w-4 text-blue-500" />
            產業分布
            {sector?.alert && (
              <Badge variant="outline" className="border-amber-400 text-amber-600 bg-amber-50 text-xs">
                <AlertTriangle className="h-3 w-3 mr-1" /> 集中警示
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {sectorLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : !sector ? null : (
            <div className="space-y-2">
              {sector.alerts.length > 0 && (
                <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                  {sector.alerts[0]}
                </p>
              )}
              <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                {sector.sectors.map((s) => (
                  <div key={s.sector} className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground truncate">{s.sector}</span>
                    <span className={cn("font-mono font-semibold ml-2",
                      s.pctOfPortfolio > 50 ? "text-red-500" : "text-foreground"
                    )}>
                      {s.pctOfPortfolio}%
                    </span>
                  </div>
                ))}
              </div>
              {sector.sectors.length === 0 && (
                <p className="text-sm text-muted-foreground">尚無持倉資料</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
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
          <h1 className="text-xl font-semibold">總覽</h1>
          {data && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Generated {data.generatedAt.replace("T", " ")}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 ml-auto flex-wrap">
          <label className="text-sm text-muted-foreground whitespace-nowrap">截至日期</label>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="text-sm border rounded-md px-2 py-1 bg-background"
          />
          <label className="text-sm text-muted-foreground whitespace-nowrap">催化劑天數</label>
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
            重新整理
          </Button>
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-md px-4 py-3">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          載入失敗：{" "}
          {error instanceof Error ? error.message : "Unknown error"}
        </div>
      )}

      {/* A. Portfolio */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">投資組合摘要</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <PortfolioSection data={data} />}
        </CardContent>
      </Card>

      {/* B. Jimmy methodology — Rolling + Sector */}
      <JimmySection />

      {/* D. Risk */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">風險摘要</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <RiskSection data={data} />}
        </CardContent>
      </Card>

      {/* E. Watchlist Coverage */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">觀察清單涵蓋率</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <WatchlistSection data={data} />}
        </CardContent>
      </Card>

      {/* F. Upcoming Catalysts */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">即將到來的催化劑</CardTitle>
            {data && (
              <span className="text-xs text-muted-foreground">
                未來 {data.upcomingCatalysts.daysWindow} 天內共 {data.upcomingCatalysts.count} 筆
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
          <CardTitle className="text-base">對沖試算摘要</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? <SectionSkeleton /> : <OffsettingSection data={data} />}
        </CardContent>
      </Card>

    </div>
  );
}
