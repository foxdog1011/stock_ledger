"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useLots } from "@/hooks/use-queries";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fmtMoney, fmtDate, fmtPct, pnlClass } from "@/lib/format";
import { LotsBubbleChart } from "@/components/charts/lots-bubble-chart";
import type { RealizedBreakdown } from "@/lib/types";

type Method = "fifo" | "lifo" | "wac";

export default function LotsPage() {
  const params = useParams();
  const symbol = (params.symbol as string).toUpperCase();
  const [method, setMethod] = useState<Method>("fifo");
  const today = new Date().toISOString().slice(0, 10);
  const [asOf, setAsOf] = useState(today);

  const query = useLots({ symbol, asOf, method });
  const data = query.data;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/positions"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Positions
        </Link>
        <Badge variant="secondary" className="text-base px-3 py-1">
          {symbol}
        </Badge>
        <Tabs
          value={method}
          onValueChange={(v) => setMethod(v as Method)}
        >
          <TabsList>
            <TabsTrigger value="fifo">FIFO</TabsTrigger>
            <TabsTrigger value="lifo">LIFO</TabsTrigger>
            <TabsTrigger value="wac">WAC</TabsTrigger>
          </TabsList>
        </Tabs>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <label className="text-muted-foreground">As of</label>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="border rounded px-2 py-1 text-sm bg-background"
          />
        </div>
      </div>

      {/* Loading / Error */}
      {query.isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      )}
      {query.isError && (
        <p className="text-center text-destructive text-sm">
          Failed to load lots: {String((query.error as Error)?.message ?? "")}
        </p>
      )}

      {data && (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <Card>
              <CardHeader className="pb-1">
                <CardTitle className="text-xs text-muted-foreground">Position Qty</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold tabular-nums">
                {data.positionQty}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-1">
                <CardTitle className="text-xs text-muted-foreground">Avg Cost (WAC)</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold tabular-nums">
                {fmtMoney(data.avgCostWac, 4)}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-1">
                <CardTitle className="text-xs text-muted-foreground">Open Lots</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold">
                {data.lots.length}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-1">
                <CardTitle className="text-xs text-muted-foreground">Sell Events</CardTitle>
              </CardHeader>
              <CardContent className="text-lg font-semibold">
                {data.realizedBreakdown.length}
              </CardContent>
            </Card>
          </div>

          {/* Chart */}
          {data.lots.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Cost / Share vs WAC &amp; Market Price</CardTitle>
              </CardHeader>
              <CardContent>
                <LotsBubbleChart lots={data.lots} avgCostWac={data.avgCostWac} />
              </CardContent>
            </Card>
          )}

          {/* Lots Highlights */}
          {data.lots.length > 0 && data.lots[0].unrealizedPct != null && (() => {
            const sorted = [...data.lots].sort((a, b) => (b.unrealizedPct ?? 0) - (a.unrealizedPct ?? 0));
            const best  = sorted[0];
            const worst = sorted[sorted.length - 1];
            const underwaterCount = data.lots.filter((l) => (l.underwaterPct ?? 0) > 0).length;
            const totalUnreal = data.lots.reduce((s, l) => s + (l.unrealizedPnl ?? 0), 0);
            return (
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Lots Highlights</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Best Lot</p>
                      <p className="font-medium">#{best.lotId} <span className="text-xs text-muted-foreground">{fmtDate(best.buyDate)}</span></p>
                      <p className={`tabular-nums text-xs font-semibold ${pnlClass(best.unrealizedPct)}`}>
                        {fmtPct(best.unrealizedPct)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Worst Lot</p>
                      <p className="font-medium">#{worst.lotId} <span className="text-xs text-muted-foreground">{fmtDate(worst.buyDate)}</span></p>
                      <p className={`tabular-nums text-xs font-semibold ${pnlClass(worst.unrealizedPct)}`}>
                        {fmtPct(worst.unrealizedPct)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Underwater Lots</p>
                      <p className="font-medium tabular-nums">
                        {underwaterCount} / {data.lots.length}
                      </p>
                      {underwaterCount > 0 && (
                        <p className="text-xs text-red-500">
                          {((underwaterCount / data.lots.length) * 100).toFixed(0)}% of lots
                        </p>
                      )}
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Total Unrealized</p>
                      <p className={`font-semibold tabular-nums ${pnlClass(totalUnreal)}`}>
                        {totalUnreal >= 0 ? "+" : ""}{fmtMoney(totalUnreal)}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })()}

          {/* Lots table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Open Lots</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto p-0">
              {data.lots.length === 0 ? (
                <p className="p-6 text-center text-muted-foreground text-sm">
                  No open lots
                </p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Lot</TableHead>
                      <TableHead>Buy Date</TableHead>
                      <TableHead className="text-right">Qty Remaining</TableHead>
                      <TableHead className="text-right">Buy Price</TableHead>
                      <TableHead className="text-right">Cost/Share</TableHead>
                      <TableHead className="text-right">Total Cost</TableHead>
                      <TableHead className="text-right">Market Value</TableHead>
                      <TableHead className="text-right">Unrealized P&L</TableHead>
                      <TableHead className="text-right">Return %</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.lots.map((lot) => (
                      <TableRow key={lot.lotId}>
                        <TableCell className="tabular-nums text-muted-foreground">
                          #{lot.lotId}
                        </TableCell>
                        <TableCell className="tabular-nums">
                          {fmtDate(lot.buyDate)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {lot.qtyRemaining}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtMoney(lot.buyPrice, 4)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtMoney(lot.costPerShare, 4)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtMoney(lot.totalCost)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtMoney(lot.marketValue)}
                        </TableCell>
                        <TableCell className={`text-right tabular-nums ${pnlClass(lot.unrealizedPnl)}`}>
                          {fmtMoney(lot.unrealizedPnl)}
                        </TableCell>
                        <TableCell className={`text-right tabular-nums ${pnlClass(lot.unrealizedPct)}`}>
                          {lot.unrealizedPct != null ? fmtPct(lot.unrealizedPct) : "—"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Realized Breakdown (FIFO / LIFO only) */}
          {method !== "wac" && data.realizedBreakdown.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Realized Breakdown</CardTitle>
              </CardHeader>
              <CardContent className="overflow-x-auto p-0">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Sell Date</TableHead>
                      <TableHead className="text-right">Qty</TableHead>
                      <TableHead className="text-right">Sell Price</TableHead>
                      <TableHead className="text-right">Comm</TableHead>
                      <TableHead className="text-right">Tax</TableHead>
                      <TableHead>Lot Allocations</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.realizedBreakdown.map((rb: RealizedBreakdown) => (
                      <TableRow key={rb.sellTradeId}>
                        <TableCell className="tabular-nums">
                          {fmtDate(rb.sellDate)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {rb.sellQty}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtMoney(rb.sellPrice, 4)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtMoney(rb.commission)}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {fmtMoney(rb.tax)}
                        </TableCell>
                        <TableCell>
                          <div className="flex flex-wrap gap-2">
                            {rb.allocations.map((a) => (
                              <span
                                key={a.lotId}
                                className="text-xs bg-muted rounded px-2 py-0.5 tabular-nums"
                              >
                                #{a.lotId} ×{a.qty}{" "}
                                <span className={pnlClass(a.realizedPnlPiece)}>
                                  {fmtMoney(a.realizedPnlPiece)}
                                </span>
                              </span>
                            ))}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}

          {/* WAC note */}
          {method === "wac" && (
            <p className="text-xs text-muted-foreground">
              WAC method uses weighted average cost for all open lots. Realized breakdown is not available under WAC.
            </p>
          )}
        </>
      )}
    </div>
  );
}
