"use client";

import { useState } from "react";
import Link from "next/link";
import { useAnomaly, useAnomalyBatch } from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { AlertTriangle, Activity, ScanSearch, RefreshCw, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { fmtMoney, fmtDate } from "@/lib/format";
import type { AnomalyPoint, AnomalyBatchItem } from "@/lib/types";

// ── helpers ───────────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: "high" | "medium" }) {
  return (
    <Badge
      variant="outline"
      className={cn("text-xs", severity === "high"
        ? "border-red-300 bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-400"
        : "border-amber-300 bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400")}
    >
      {severity === "high" ? "高度" : "中度"}
    </Badge>
  );
}

function AnomalyBadge({ item }: { item: AnomalyBatchItem }) {
  return (
    <Badge
      variant="outline"
      className={cn("gap-1 text-xs font-medium", item.has_high_severity
        ? "border-red-300 bg-red-50 text-red-700"
        : "border-amber-300 bg-amber-50 text-amber-700")}
    >
      <AlertTriangle className="h-3 w-3" />
      {item.anomaly_count} 個異動
    </Badge>
  );
}

// ── Batch scan panel ──────────────────────────────────────────────────────────

function BatchScanPanel() {
  const { data, isLoading, refetch, isFetching } = useAnomalyBatch({ days: 120 });

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <ScanSearch className="h-4 w-4 text-purple-500" />
            持倉全局掃描
          </CardTitle>
          <Button
            variant="outline" size="sm" className="h-7 text-xs gap-1"
            onClick={() => refetch()} disabled={isFetching}
          >
            <RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} />
            重新掃描
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          自動偵測所有持倉中統計上不尋常的量價行為，提醒你在新聞前就注意市場變化。
        </p>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map(i => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : !data ? null : data.results.length === 0 ? (
          <div className="flex items-center gap-2 py-4 text-sm text-emerald-600">
            <Activity className="h-4 w-4" />
            掃描 {data.scanned} 支持倉股，近期無統計異動
          </div>
        ) : (
          <>
            <p className="text-xs text-muted-foreground mb-3">
              掃描 <b>{data.scanned}</b> 支持倉 — <b className="text-amber-600">{data.with_anomalies}</b> 支有異動
            </p>
            <div className="space-y-2">
              {data.results.map(item => (
                <div
                  key={item.symbol}
                  className={cn(
                    "flex items-start justify-between rounded-lg border px-3 py-2.5 gap-3",
                    item.has_high_severity
                      ? "border-red-200 bg-red-50/40"
                      : "border-amber-200 bg-amber-50/40"
                  )}
                >
                  <div className="flex items-start gap-3 min-w-0">
                    <Badge variant="secondary" className="font-mono shrink-0">{item.symbol}</Badge>
                    <div className="min-w-0">
                      <p className="text-xs text-muted-foreground mb-0.5">{fmtDate(item.latest_date)}</p>
                      <p className="text-sm font-medium leading-snug truncate max-w-xs" title={item.latest_reason}>
                        {item.latest_reason}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <AnomalyBadge item={item} />
                    <Link
                      href={`/positions`}
                      className="text-xs text-muted-foreground hover:text-foreground"
                      title="查看持倉"
                    >
                      <ExternalLink className="h-3 w-3" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Single symbol detail ──────────────────────────────────────────────────────

function SingleScanPanel() {
  const [inputSymbol, setInputSymbol] = useState("");
  const [symbol, setSymbol] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useAnomaly(symbol, {
    days: 120,
    method: "both",
    zscoreThreshold: 2.5,
    aeThreshold: 2.5,
  });

  function run() {
    const s = inputSymbol.trim().toUpperCase();
    if (!s) return;
    if (s === symbol) refetch();
    else setSymbol(s);
  }

  const allAnomalies: AnomalyPoint[] = data
    ? [...data.zscore_anomalies, ...data.ae_anomalies]
        .sort((a, b) => b.date.localeCompare(a.date))
    : [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-500" />
          個股異動查詢
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Input */}
        <div className="flex gap-2">
          <Input
            placeholder="輸入代號，如 AAPL"
            value={inputSymbol}
            onChange={e => setInputSymbol(e.target.value)}
            onKeyDown={e => e.key === "Enter" && run()}
            className="h-8 text-sm font-mono w-40"
          />
          <Button size="sm" className="h-8" onClick={run}>查詢</Button>
        </div>

        {/* Loading */}
        {isLoading && <Skeleton className="h-32 w-full" />}

        {/* Error */}
        {error && (
          <div className="flex items-center gap-2 text-sm text-destructive">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {(error as Error).message}
          </div>
        )}

        {/* Results */}
        {data && (
          <>
            <div className={cn(
              "rounded-lg border-l-4 px-3 py-2.5",
              allAnomalies.some(a => a.severity === "high")
                ? "border-l-red-500 bg-red-50/50"
                : allAnomalies.length > 0
                ? "border-l-amber-500 bg-amber-50/50"
                : "border-l-emerald-500 bg-emerald-50/50"
            )}>
              <p className="text-sm font-semibold flex items-center gap-2">
                {data.symbol}
                {data.volume_enriched && (
                  <span className="text-xs font-normal text-sky-600">（量來自 yfinance）</span>
                )}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">{data.summary}</p>
            </div>

            {allAnomalies.length > 0 && (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>日期</TableHead>
                      <TableHead className="text-right">收盤價</TableHead>
                      <TableHead className="text-right">當日漲跌</TableHead>
                      <TableHead>嚴重度</TableHead>
                      <TableHead>異動說明</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {allAnomalies.slice(0, 15).map((a, i) => (
                      <TableRow key={`${a.date}-${i}`}>
                        <TableCell className="font-mono text-sm">{a.date}</TableCell>
                        <TableCell className="text-right font-mono text-sm">
                          {fmtMoney(a.close, 2)}
                        </TableCell>
                        <TableCell className={cn("text-right text-sm font-mono",
                          a.price_change_pct > 0 ? "text-emerald-600" : "text-red-500"
                        )}>
                          {a.price_change_pct > 0 ? "+" : ""}{a.price_change_pct.toFixed(2)}%
                        </TableCell>
                        <TableCell><SeverityBadge severity={a.severity} /></TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-64 truncate" title={a.reason}>
                          {a.reason}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </>
        )}

        {!data && !isLoading && !error && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            輸入代號後點擊查詢，偵測近 120 天的量價異動
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AnomalyPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <ScanSearch className="h-6 w-6 text-purple-500" />
          市場異動掃描
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          自動偵測持倉中的異常量價行為 — 搭配催化劑日曆與價格警示，形成完整的市場監控閉環
        </p>
      </div>

      {/* Theory callout */}
      <div className="rounded-lg border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
        <b className="text-foreground">理論依據：</b>
        重要的市場事件往往先在價格和成交量留下痕跡，才有公開消息。
        統計異動可能是知情交易者行動的訊號，建議結合催化劑日曆判斷是否有基本面原因。
      </div>

      {/* Batch scan */}
      <BatchScanPanel />

      {/* Single symbol */}
      <SingleScanPanel />
    </div>
  );
}
