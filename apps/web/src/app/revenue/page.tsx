"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { toast } from "sonner";
import { useRevenue, useFetchRevenue, useChart, usePositions } from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { BarChart3, RefreshCw, TrendingUp } from "lucide-react";
import { cn } from "@/lib/utils";

const PriceChart = dynamic(
  () => import("@/components/charts/price-chart").then((m) => m.PriceChart),
  { ssr: false, loading: () => <Skeleton className="h-[330px] w-full" /> },
);

function YoyBar({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-muted-foreground">—</span>;
  const abs = Math.abs(pct);
  const isPos = pct >= 0;
  return (
    <div className="flex items-center gap-2">
      <span className={cn("font-mono font-semibold text-sm w-16 text-right",
        isPos ? "text-emerald-600" : "text-red-500")}>
        {isPos ? "+" : ""}{pct.toFixed(1)}%
      </span>
      <div className="w-20 h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full", isPos ? "bg-emerald-500" : "bg-red-400")}
          style={{ width: `${Math.min(abs * 2, 100)}%` }}
        />
      </div>
    </div>
  );
}

function RevenuePanel({ symbol }: { symbol: string }) {
  const { data: rev, isLoading: revLoading } = useRevenue(symbol, 24);
  const { data: chart, isLoading: chartLoading } = useChart(symbol, 120);
  const fetchRev = useFetchRevenue();

  const handleFetch = async () => {
    try {
      await fetchRev.mutateAsync(symbol);
      toast.success(`${symbol} 月營收已更新`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  };

  return (
    <div className="space-y-4">
      {/* Price chart */}
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <TrendingUp className="h-4 w-4 text-blue-500" />
            {symbol} — 技術指標
          </CardTitle>
        </CardHeader>
        <CardContent>
          {chartLoading ? (
            <Skeleton className="h-[330px]" />
          ) : chart?.data && chart.data.length > 0 ? (
            <PriceChart data={chart.data} />
          ) : (
            <p className="text-sm text-muted-foreground py-4 text-center">
              無價格資料 — 請先在 Settings 執行 Refresh Quotes
            </p>
          )}
        </CardContent>
      </Card>

      {/* Revenue table */}
      <Card>
        <CardHeader className="pb-2 flex flex-row items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <BarChart3 className="h-4 w-4 text-blue-500" />
            月營收資料
          </CardTitle>
          <Button
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={handleFetch}
            disabled={fetchRev.isPending}
          >
            <RefreshCw className={cn("h-3 w-3 mr-1", fetchRev.isPending && "animate-spin")} />
            {fetchRev.isPending ? "抓取中…" : "抓取 MOPS"}
          </Button>
        </CardHeader>
        <CardContent>
          {revLoading ? (
            <div className="space-y-2">{[0,1,2].map((i) => <Skeleton key={i} className="h-8" />)}</div>
          ) : !rev || rev.data.length === 0 ? (
            <div className="text-center py-6 space-y-2">
              <p className="text-sm text-muted-foreground">尚無月營收資料</p>
              <Button size="sm" onClick={handleFetch} disabled={fetchRev.isPending}>
                從 MOPS 抓取
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>年月</TableHead>
                  <TableHead className="text-right">月營收 (千元)</TableHead>
                  <TableHead>YoY</TableHead>
                  <TableHead>MoM</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rev.data.map((r) => (
                  <TableRow key={r.yearMonth}>
                    <TableCell className="font-mono">{r.yearMonth}</TableCell>
                    <TableCell className="text-right font-mono">
                      {r.revenue.toLocaleString()}
                    </TableCell>
                    <TableCell><YoyBar pct={r.yoyPct} /></TableCell>
                    <TableCell>
                      {r.momPct != null ? (
                        <span className={cn("text-xs font-mono",
                          r.momPct >= 0 ? "text-emerald-600" : "text-red-500")}>
                          {r.momPct >= 0 ? "+" : ""}{r.momPct.toFixed(1)}%
                        </span>
                      ) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function RevenuePage() {
  const [symbol, setSymbol] = useState("");
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const { data: positions } = usePositions({});

  const openSymbols = (positions ?? []).filter((p) => p.qty > 0).map((p) => p.symbol);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 className="h-6 w-6 text-blue-500" />
          月營收 + 技術指標
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          台股月營收（MOPS）+ 技術指標（MA / RSI / KD）
        </p>
      </div>

      {/* Symbol selector */}
      <Card>
        <CardContent className="pt-4">
          <div className="flex gap-2 flex-wrap items-center">
            <Input
              placeholder="輸入代號 e.g. 2330"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === "Enter" && symbol && setActiveSymbol(symbol)}
              className="w-36 h-8 text-sm"
            />
            <Button size="sm" className="h-8" onClick={() => symbol && setActiveSymbol(symbol)}>
              查詢
            </Button>
            {openSymbols.length > 0 && (
              <>
                <span className="text-xs text-muted-foreground">持倉：</span>
                {openSymbols.slice(0, 8).map((s) => (
                  <Badge
                    key={s}
                    variant={activeSymbol === s ? "default" : "outline"}
                    className="cursor-pointer"
                    onClick={() => setActiveSymbol(s)}
                  >
                    {s}
                  </Badge>
                ))}
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {activeSymbol ? (
        <RevenuePanel symbol={activeSymbol} />
      ) : (
        <div className="text-center py-12 text-muted-foreground">
          <BarChart3 className="h-12 w-12 mx-auto mb-2 opacity-20" />
          <p className="text-sm">輸入股票代號查詢月營收與技術指標</p>
        </div>
      )}
    </div>
  );
}
