"use client";

import { useState } from "react";
import Link from "next/link";
import { usePositions, usePositionsDetail } from "@/hooks/use-queries";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtMoney, fmtPct, pnlClass, fmtDate } from "@/lib/format";
import { WacMiniChart } from "@/components/charts/wac-mini-chart";
import { CostImpactChart } from "@/components/charts/cost-impact-chart";
import { ExternalLink } from "lucide-react";
import type { PositionDetailItem } from "@/lib/types";

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
        <h1 className="text-2xl font-bold">Positions</h1>
        <Button
          variant={includeClosed ? "default" : "outline"}
          size="sm"
          onClick={() => setIncludeClosed((v) => !v)}
        >
          {includeClosed ? "Show Open Only" : "Show Closed"}
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
          <p className="p-6 text-center text-destructive text-sm">Failed to load positions</p>
        ) : !rows.length ? (
          <p className="p-6 text-center text-muted-foreground text-sm">
            {includeClosed ? "No positions found" : "No open positions"}
          </p>
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
                <TableHead>Actions</TableHead>
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
                          Lots
                        </Link>
                      </TableCell>
                    </TableRow>

                    {isExpanded && detail && (
                      <TableRow key={`${p.symbol}-detail`}>
                        <TableCell colSpan={9} className="bg-muted/30 p-4">
                          <div className="space-y-4">
                            {/* Block 1: Cost Summary */}
                            {detail.costSummary && (
                              <div>
                                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                                  Cost Summary
                                </p>
                                <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 text-sm">
                                  <div>
                                    <p className="text-xs text-muted-foreground">Buy Count</p>
                                    <p className="font-medium">{detail.costSummary.buyCount}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">Total Qty</p>
                                    <p className="font-medium tabular-nums">{detail.costSummary.buyQtyTotal}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">Total Cost</p>
                                    <p className="font-medium tabular-nums">{fmtMoney(detail.costSummary.buyCostTotalIncludingFees)}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">Min Price</p>
                                    <p className="font-medium tabular-nums">{fmtMoney(detail.costSummary.minBuyPrice, 4)}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">Max Price</p>
                                    <p className="font-medium tabular-nums">{fmtMoney(detail.costSummary.maxBuyPrice, 4)}</p>
                                  </div>
                                  <div>
                                    <p className="text-xs text-muted-foreground">Date Range</p>
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
                                  Running WAC
                                </p>
                                <div className="overflow-x-auto">
                                  <table className="w-full text-xs">
                                    <thead>
                                      <tr className="border-b">
                                        <th className="text-left py-1 pr-3 text-muted-foreground">Date</th>
                                        <th className="text-left py-1 pr-3 text-muted-foreground">Side</th>
                                        <th className="text-right py-1 pr-3 text-muted-foreground">Qty</th>
                                        <th className="text-right py-1 pr-3 text-muted-foreground">Price</th>
                                        <th className="text-right py-1 text-muted-foreground">Avg Cost After</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {detail.runningWac.map((entry) => (
                                        <tr key={entry.tradeId} className="border-b border-border/40">
                                          <td className="py-1 pr-3 tabular-nums">{fmtDate(entry.date)}</td>
                                          <td className="py-1 pr-3">
                                            <span className={entry.side === "buy" ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}>
                                              {entry.side}
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
                                  Avg Cost History
                                </p>
                                <WacMiniChart data={detail.wacSeries} />
                              </div>
                            )}

                            {/* Block 4: Cost Impact (last buy) */}
                            {detail.costImpact && (
                              <div>
                                <p className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">
                                  Cost Impact — Last Buy
                                </p>
                                {detail.lastBuy && (
                                  <div className="flex flex-wrap gap-4 text-xs mb-3 rounded-md bg-muted/40 px-3 py-2">
                                    <span>Date: <b>{fmtDate(detail.lastBuy.date)}</b></span>
                                    <span>Qty: <b className="tabular-nums">{detail.lastBuy.qty}</b></span>
                                    <span>Price: <b className="tabular-nums">{fmtMoney(detail.lastBuy.price, 4)}</b></span>
                                    <span>Fees: <b className="tabular-nums">{fmtMoney(detail.lastBuy.commission + detail.lastBuy.tax)}</b></span>
                                  </div>
                                )}
                                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
                                  {[
                                    { label: "Prev Avg Cost", value: detail.costImpact.prevAvgCost != null ? fmtMoney(detail.costImpact.prevAvgCost, 4) : "—", color: false },
                                    { label: "New Avg Cost",  value: fmtMoney(detail.costImpact.newAvgCost, 4), color: false },
                                    { label: "Δ Avg Cost",    raw: detail.costImpact.deltaAvgCost, pct: detail.costImpact.deltaAvgCostPct },
                                    { label: "Unrealized Impact", raw: detail.costImpact.impactUnrealizedPnl, pct: null },
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
