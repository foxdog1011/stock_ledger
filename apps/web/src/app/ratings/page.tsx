"use client";

import { useState } from "react";
import Link from "next/link";
import { RefreshCw, Target, TrendingUp, TrendingDown, Minus, Star } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useRatings } from "@/hooks/use-queries";
import { cn } from "@/lib/utils";

const RATING_COLORS: Record<string, string> = {
  strong_buy:  "bg-emerald-500/15 text-emerald-400 border-emerald-500/40",
  buy:         "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  hold:        "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  sell:        "bg-red-500/10 text-red-300 border-red-500/30",
  strong_sell: "bg-red-500/15 text-red-400 border-red-500/40",
};

const RATING_LABELS: Record<string, string> = {
  strong_buy: "Strong Buy",
  buy: "Buy",
  hold: "Hold",
  sell: "Sell",
  strong_sell: "Strong Sell",
};

function ratingOrder(r: string): number {
  const order: Record<string, number> = {
    strong_buy: 0, buy: 1, hold: 2, sell: 3, strong_sell: 4,
  };
  return order[r] ?? 5;
}

function UpsideBadge({ current, target }: { current?: number; target?: number }) {
  if (!current || !target) return <span className="text-zinc-500">—</span>;
  const pct = ((target - current) / current) * 100;
  const color = pct > 10 ? "text-emerald-400" : pct < -10 ? "text-red-400" : "text-zinc-300";
  const Icon = pct > 0 ? TrendingUp : pct < 0 ? TrendingDown : Minus;
  return (
    <span className={cn("flex items-center gap-1 font-mono", color)}>
      <Icon className="h-3 w-3" />
      {pct >= 0 ? "+" : ""}{pct.toFixed(1)}%
    </span>
  );
}

export default function RatingsPage() {
  const { data: ratings, isLoading, refetch, isFetching } = useRatings();

  const sorted = [...(ratings ?? [])].sort(
    (a, b) => ratingOrder(a.rating) - ratingOrder(b.rating),
  );

  const summary = {
    strongBuy: sorted.filter((r) => r.rating === "strong_buy").length,
    buy: sorted.filter((r) => r.rating === "buy").length,
    hold: sorted.filter((r) => r.rating === "hold").length,
    sell: sorted.filter((r) => r.rating === "sell").length,
    strongSell: sorted.filter((r) => r.rating === "strong_sell").length,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Star className="h-6 w-6 text-amber-400" />
            投資評等總覽
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            所有股票的評等、目標價與情境分析
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={cn("h-4 w-4 mr-1", isFetching && "animate-spin")} />
          刷新
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-5 gap-3">
        {[
          { label: "Strong Buy", count: summary.strongBuy, cls: "text-emerald-400" },
          { label: "Buy", count: summary.buy, cls: "text-emerald-300" },
          { label: "Hold", count: summary.hold, cls: "text-zinc-300" },
          { label: "Sell", count: summary.sell, cls: "text-red-300" },
          { label: "Strong Sell", count: summary.strongSell, cls: "text-red-400" },
        ].map(({ label, count, cls }) => (
          <Card key={label}>
            <CardContent className="pt-4 pb-3 text-center">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className={cn("text-2xl font-bold mt-1", cls)}>{count}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Ratings table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">評等清單</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
            </div>
          ) : sorted.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              尚無評等資料。透過個股深研頁或 J.A.R.V.I.S. 設定評等。
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>股票</TableHead>
                  <TableHead>評等</TableHead>
                  <TableHead className="text-right">現價</TableHead>
                  <TableHead className="text-right">目標價</TableHead>
                  <TableHead className="text-right">停損價</TableHead>
                  <TableHead className="text-right">潛在漲幅</TableHead>
                  <TableHead className="text-right">風險報酬比</TableHead>
                  <TableHead>投資論點</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((r) => {
                  const upside = r.current_price && r.target_price
                    ? ((r.target_price - r.current_price) / r.current_price) * 100
                    : null;
                  const downside = r.current_price && r.stop_loss
                    ? ((r.current_price - r.stop_loss) / r.current_price) * 100
                    : null;
                  const rrr = upside != null && downside != null && downside > 0
                    ? (upside / downside).toFixed(1)
                    : null;

                  return (
                    <TableRow key={r.symbol}>
                      <TableCell>
                        <Link
                          href={`/stock/${r.symbol}`}
                          className="font-mono font-semibold text-primary hover:underline"
                        >
                          {r.symbol}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={cn("text-xs", RATING_COLORS[r.rating] ?? "")}
                        >
                          {RATING_LABELS[r.rating] ?? r.rating}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {r.current_price?.toLocaleString() ?? "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-emerald-400">
                        {r.target_price?.toLocaleString() ?? "—"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-red-400">
                        {r.stop_loss?.toLocaleString() ?? "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <UpsideBadge current={r.current_price} target={r.target_price} />
                      </TableCell>
                      <TableCell className={cn(
                        "text-right font-mono",
                        rrr && parseFloat(rrr) >= 2 ? "text-emerald-400" : "text-zinc-400",
                      )}>
                        {rrr ? `${rrr}:1` : "—"}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                        {r.thesis ?? ""}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
