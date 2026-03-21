"use client";

import { useState } from "react";
import { TrendingUp, TrendingDown, Minus, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { usePortfolioChip, useChipRange } from "@/hooks/use-queries";
import { fmtMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ChipData } from "@/lib/types";

function today() { return new Date().toISOString().slice(0, 10); }
function daysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function NetBadge({ net }: { net: number }) {
  if (net > 0) return (
    <span className="text-emerald-600 font-mono font-semibold flex items-center gap-0.5">
      <TrendingUp className="h-3 w-3" />{net.toLocaleString()}
    </span>
  );
  if (net < 0) return (
    <span className="text-red-500 font-mono font-semibold flex items-center gap-0.5">
      <TrendingDown className="h-3 w-3" />{net.toLocaleString()}
    </span>
  );
  return <span className="text-muted-foreground font-mono flex items-center gap-0.5"><Minus className="h-3 w-3" />0</span>;
}

function ChipCard({ data }: { data: ChipData }) {
  if (data.error) {
    return (
      <Card className="opacity-50">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-mono">{data.symbol}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">暫無資料（{data.error}）</p>
        </CardContent>
      </Card>
    );
  }

  const totalColor = data.totalNet > 0 ? "text-emerald-600" : data.totalNet < 0 ? "text-red-500" : "text-muted-foreground";

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-mono">{data.symbol}</CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">{data.source}</Badge>
            <span className={cn("text-lg font-bold", totalColor)}>
              {data.totalNet > 0 ? "+" : ""}{data.totalNet.toLocaleString()}
            </span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{data.date} 三大法人合計買賣超</p>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-3 gap-3 text-sm">
          {[
            { label: "外資", group: data.foreign },
            { label: "投信", group: data.investmentTrust },
            { label: "自營商", group: data.dealer },
          ].map(({ label, group }) => (
            <div key={label} className="rounded-md border p-2">
              <p className="text-xs text-muted-foreground mb-1">{label}</p>
              <div className="space-y-0.5 font-mono text-xs">
                <div className="flex justify-between"><span className="text-muted-foreground">買</span><span className="text-emerald-600">{group.buy.toLocaleString()}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">賣</span><span className="text-red-500">{group.sell.toLocaleString()}</span></div>
                <div className="flex justify-between border-t pt-0.5 mt-0.5">
                  <span className="font-semibold">淨</span>
                  <NetBadge net={group.net} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function RangeTable({ symbol }: { symbol: string }) {
  const end = today();
  const start = daysAgo(14);
  const { data, isLoading } = useChipRange(symbol, start, end);

  if (isLoading) return <Skeleton className="h-48 w-full" />;
  if (!data || data.daily.length === 0) return <p className="text-sm text-muted-foreground py-4 text-center">近 14 日無資料</p>;

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-4 gap-3 text-sm">
        {[
          { label: "外資 14日淨", val: data.summary.foreignNetTotal },
          { label: "投信 14日淨", val: data.summary.investmentTrustNetTotal },
          { label: "自營商 14日淨", val: data.summary.dealerNetTotal },
          { label: "三大合計", val: data.summary.totalNet },
        ].map(({ label, val }) => (
          <div key={label} className="rounded-lg border p-3 text-center">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className={cn("text-base font-bold font-mono mt-1",
              val > 0 ? "text-emerald-600" : val < 0 ? "text-red-500" : "text-muted-foreground"
            )}>{val > 0 ? "+" : ""}{val.toLocaleString()}</p>
          </div>
        ))}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>日期</TableHead>
            <TableHead className="text-right">外資淨</TableHead>
            <TableHead className="text-right">投信淨</TableHead>
            <TableHead className="text-right">自營商淨</TableHead>
            <TableHead className="text-right">合計</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...data.daily].reverse().map((row) => (
            <TableRow key={row.date}>
              <TableCell className="text-sm">{row.date}</TableCell>
              <TableCell className="text-right"><NetBadge net={row.foreign.net} /></TableCell>
              <TableCell className="text-right"><NetBadge net={row.investmentTrust.net} /></TableCell>
              <TableCell className="text-right"><NetBadge net={row.dealer.net} /></TableCell>
              <TableCell className="text-right"><NetBadge net={row.totalNet} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export default function ChipPage() {
  const [date, setDate] = useState(today());
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const { data: portfolio, isLoading, refetch, isFetching } = usePortfolioChip(date);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">三大法人籌碼</h1>
          <p className="text-sm text-muted-foreground">外資 / 投信 / 自營商 買賣超</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={date}
            max={today()}
            onChange={(e) => setDate(e.target.value)}
            className="border rounded px-2 py-1 text-sm bg-background"
          />
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-1 ${isFetching ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-52 w-full" />)}
        </div>
      ) : !portfolio ? null : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {portfolio.holdings.map((chip) => (
              <div key={chip.symbol} className="space-y-2">
                <ChipCard data={chip} />
                {!chip.error && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full text-xs text-muted-foreground"
                    onClick={() => setExpandedSymbol(expandedSymbol === chip.symbol ? null : chip.symbol)}
                  >
                    {expandedSymbol === chip.symbol ? "收起近 14 日▲" : "展開近 14 日▼"}
                  </Button>
                )}
                {expandedSymbol === chip.symbol && !chip.error && (
                  <Card>
                    <CardContent className="pt-4">
                      <RangeTable symbol={chip.symbol} />
                    </CardContent>
                  </Card>
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground text-center">
            資料來源：TWSE（上市）/ FinMind（上櫃，需 FINMIND_TOKEN）。
            單位：張（1000 股）
          </p>
        </div>
      )}
    </div>
  );
}
