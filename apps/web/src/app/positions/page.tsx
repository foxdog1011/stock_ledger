"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePositions, usePositionsDetail, useChart } from "@/hooks/use-queries";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtMoney, fmtPct, pnlClass, fmtDate } from "@/lib/format";
import { WacMiniChart } from "@/components/charts/wac-mini-chart";
import { CostImpactChart } from "@/components/charts/cost-impact-chart";
import { ExternalLink, ChevronRight } from "lucide-react";
import type { PositionDetailItem } from "@/lib/types";

const PriceChart = dynamic(
  () => import("@/components/charts/price-chart").then((m) => m.PriceChart),
  { ssr: false, loading: () => <Skeleton className="h-[330px] w-full" /> },
);

function TechnicalBlock({ symbol, avgCost }: { symbol: string; avgCost: number | null }) {
  const { data: chart, isLoading } = useChart(symbol, 120);
  return (
    <div>
      <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
        技術指標（MA / RSI / KD）
      </p>
      {isLoading ? (
        <Skeleton className="h-[330px]" />
      ) : chart?.data && chart.data.length > 0 ? (
        <PriceChart data={chart.data} avgCost={avgCost} />
      ) : (
        <p className="text-xs text-muted-foreground">暫無價格歷史資料。</p>
      )}
    </div>
  );
}

export default function PositionsPage() {
  const [includeClosed, setIncludeClosed] = useState(false);
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  const query = usePositions({ includeClosed });
  const detailQuery = usePositionsDetail();
  const rows = query.data ?? [];
  const detailMap: Record<string, PositionDetailItem> = {};
  for (const d of detailQuery.data ?? []) {
    detailMap[d.symbol] = d;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">持倉</h1>
        <Button
          variant={includeClosed ? "default" : "outline"}
          size="sm"
          onClick={() => setIncludeClosed((v) => !v)}
        >
          {includeClosed ? "只顯示未平倉" : "顯示已平倉"}
        </Button>
      </div>

      <Card>
        {query.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : query.isError ? (
          <p className="p-6 text-center text-destructive text-sm">持倉資料載入失敗</p>
        ) : !rows.length ? (
          <p className="p-6 text-center text-muted-foreground text-sm">
            {includeClosed ? "找不到持倉紀錄" : "目前無持倉"}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>代號</TableHead>
                <TableHead className="text-right">數量</TableHead>
                <TableHead className="text-right">均成本</TableHead>
                <TableHead className="text-right">現價</TableHead>
                <TableHead className="text-right">市值</TableHead>
                <TableHead className="text-right">未實現損益</TableHead>
                <TableHead className="text-right">已實現損益</TableHead>
                <TableHead>來源</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => {
                const pnlPct =
                  p.avgCost && p.lastPrice
                    ? ((p.lastPrice - p.avgCost) / p.avgCost) * 100
                    : null;
                const isExpanded = expandedSymbol === p.symbol;
                const detail = detailMap[p.symbol];

                return (
                  <>
                    <TableRow
                      key={p.symbol}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() =>
                        setExpandedSymbol(isExpanded ? null : p.symbol)
                      }
                    >
                      <TableCell className="pr-0">
                        <ChevronRight
                          className={`h-4 w-4 text-muted-foreground transition-transform ${isExpanded ? "rotate-90" : ""}`}
                        />
                      </TableCell>
                      <TableCell>
                        <Badge variant={p.qty > 0 ? "secondary" : "outline"}>
                          {p.symbol}
                        </Badge>
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
                        <span>{fmtMoney(p.unrealizedPnl)}</span>
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
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Link
                          href={`/lots/${p.symbol}`}
                          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                        >
                          <ExternalLink className="h-3 w-3" />
                          股份
                        </Link>
                      </TableCell>
                    </TableRow>

                    {isExpanded && detail && (
                      <TableRow key={`${p.symbol}-detail`}>
                        <TableCell colSpan={10} className="bg-muted/30 p-4">
                          <div className="space-y-4">
                            {/* Block 1: Cost Summary */}
                            {detail.costSummary && (
                              <div>
                                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                                  成本摘要
                                </p>
                                <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 text-sm">
                                  <div>
                                    <p className="text-xs text-muted-foreground">買進次數</p>
                                    <p className="font-medium">{detail.costSummary.buyCount}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">總數量</p>
                                    <p className="font-medium tabular-nums">{detail.costSummary.buyQtyTotal}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">總成本</p>
                                    <p className="font-medium tabular-nums">{fmtMoney(detail.costSummary.buyCostTotalIncludingFees)}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">最低買價</p>
                                    <p className="font-medium tabular-nums">{fmtMoney(detail.costSummary.minBuyPrice, 4)}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">最高買價</p>
                                    <p className="font-medium tabular-nums">{fmtMoney(detail.costSummary.maxBuyPrice, 4)}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">買進期間</p>
                                    <p className="font-medium text-xs">
                                      {fmtDate(detail.costSummary.firstBuyDate)} –{" "}
                                      {fmtDate(detail.costSummary.lastBuyDate)}
                                    </p>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Block 2: Running WAC table */}
                            {detail.runningWac.length > 0 && (
                              <div>
                                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                                  滾動加權均成本
                                </p>
                                <div className="overflow-x-auto">
                                  <table className="w-full text-xs">
                                    <thead>
                                      <tr className="border-b">
                                        <th className="text-left py-1 pr-3 text-muted-foreground">日期</th>
                                        <th className="text-left py-1 pr-3 text-muted-foreground">方向</th>
                                        <th className="text-right py-1 pr-3 text-muted-foreground">數量</th>
                                        <th className="text-right py-1 pr-3 text-muted-foreground">價格</th>
                                        <th className="text-right py-1 text-muted-foreground">交易後均成本</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {detail.runningWac.map((entry) => (
                                        <tr key={entry.tradeId} className="border-b border-border/40">
                                          <td className="py-1 pr-3 tabular-nums">{fmtDate(entry.date)}</td>
                                          <td className="py-1 pr-3">
                                            <span className={entry.side === "buy" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
                                              {entry.side === "buy" ? "買進" : "賣出"}
                                            </span>
                                          </td>
                                          <td className="py-1 pr-3 text-right tabular-nums">{entry.qty}</td>
                                          <td className="py-1 pr-3 text-right tabular-nums">{fmtMoney(entry.price, 4)}</td>
                                          <td className="py-1 text-right tabular-nums">
                                            {entry.avgCostAfter != null ? fmtMoney(entry.avgCostAfter, 4) : "—"}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            )}

                            {/* Block 3: WAC mini chart */}
                            {detail.wacSeries.length > 0 && (
                              <div>
                                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                                  均成本歷史
                                </p>
                                <WacMiniChart data={detail.wacSeries} />
                              </div>
                            )}

                            {/* Block 4: Technical Indicators */}
                            <TechnicalBlock symbol={p.symbol} avgCost={p.avgCost} />

                            {/* Block 5: Cost Impact (last buy) */}
                            {detail.costImpact && (
                              <div>
                                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                                  成本影響 — 最近一筆買進
                                </p>
                                {detail.lastBuy && (
                                  <div className="flex flex-wrap gap-4 text-xs mb-3 rounded-md bg-muted/40 px-3 py-2">
                                    <span>日期：<b>{fmtDate(detail.lastBuy.date)}</b></span>
                                    <span>數量：<b className="tabular-nums">{detail.lastBuy.qty}</b></span>
                                    <span>價格：<b className="tabular-nums">{fmtMoney(detail.lastBuy.price, 4)}</b></span>
                                    <span>手續費：<b className="tabular-nums">{fmtMoney(detail.lastBuy.commission + detail.lastBuy.tax)}</b></span>
                                  </div>
                                )}
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                                  {[
                                    { label: "前均成本", value: detail.costImpact.prevAvgCost != null ? fmtMoney(detail.costImpact.prevAvgCost, 4) : "—", color: false },
                                    { label: "新均成本", value: fmtMoney(detail.costImpact.newAvgCost, 4), color: false },
                                    { label: "Δ 均成本", raw: detail.costImpact.deltaAvgCost, pct: detail.costImpact.deltaAvgCostPct },
                                    { label: "未實現損益影響", raw: detail.costImpact.impactUnrealizedPnl, pct: null },
                                  ].map((s, i) => (
                                    <div key={i} className="rounded-md bg-muted/40 p-3">
                                      <p className="text-xs text-muted-foreground mb-0.5">{s.label}</p>
                                      {"raw" in s ? (
                                        <p className={`text-sm font-semibold tabular-nums ${pnlClass(s.raw)}`}>
                                          {s.raw != null
                                            ? `${s.raw >= 0 ? "+" : ""}${fmtMoney(s.raw, 4)}`
                                            : "—"}
                                          {s.pct != null && (
                                            <span className="ml-1 text-xs opacity-70">
                                              ({fmtPct(s.pct)})
                                            </span>
                                          )}
                                        </p>
                                      ) : (
                                        <p className="text-sm font-semibold tabular-nums">{s.value}</p>
                                      )}
                                    </div>
                                  ))}
                                </div>
                                <CostImpactChart impact={detail.costImpact} lastPrice={p.lastPrice} />
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
