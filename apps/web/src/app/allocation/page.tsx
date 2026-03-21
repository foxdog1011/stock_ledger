"use client";

import dynamic from "next/dynamic";
import { useAllocation } from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fmtMoney } from "@/lib/format";
import { PieChart as PieChartIcon } from "lucide-react";
import type { AllocationSlice } from "@/lib/types";

const AllocDonutChart = dynamic(
  () => import("@/components/charts/alloc-donut-chart").then((m) => m.AllocDonutChart),
  { ssr: false, loading: () => <Skeleton className="h-[200px] w-full" /> },
);

const COLORS = [
  "#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6",
  "#06b6d4","#f97316","#84cc16","#ec4899","#6366f1",
];

function AllocationDonut({ title, slices }: { title: string; slices: AllocationSlice[] }) {
  const data = slices.map((s, i) => ({
    name: s.label,
    value: s.value,
    fill: COLORS[i % COLORS.length],
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <AllocDonutChart data={data} />
        <div className="mt-3 space-y-1">
          {slices.map((s, i) => (
            <div key={s.label} className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <div className="h-2.5 w-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                <span className="text-muted-foreground truncate max-w-[120px]">{s.label}</span>
              </div>
              <div className="flex gap-2 font-mono">
                <span className="text-muted-foreground">{s.pct}%</span>
                <span className="font-medium">{fmtMoney(s.value)}</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function AllocationPage() {
  const { data, isLoading } = useAllocation();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Asset Allocation</h1>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-[300px]" />)}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Asset Allocation</h1>
        <p className="text-sm text-muted-foreground">No allocation data available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <PieChartIcon className="h-6 w-6 text-blue-500" />
          Asset Allocation
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          As of {data.asOf} · Total equity: {fmtMoney(data.totalEquity)}
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Total Equity</p>
            <p className="text-xl font-bold font-mono">{fmtMoney(data.totalEquity)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Market Value</p>
            <p className="text-xl font-bold font-mono">{fmtMoney(data.totalMarketValue)}</p>
            <p className="text-xs text-muted-foreground">
              {data.totalEquity > 0 ? Math.round(data.totalMarketValue / data.totalEquity * 100) : 0}% of equity
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground">Cash</p>
            <p className="text-xl font-bold font-mono">{fmtMoney(data.cash)}</p>
            <p className="text-xs text-muted-foreground">
              {data.totalEquity > 0 ? Math.round(data.cash / data.totalEquity * 100) : 0}% of equity
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Donut charts */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AllocationDonut title="Asset Class" slices={data.byAssetClass} />
        <AllocationDonut title="Sector" slices={data.bySector} />
        <AllocationDonut title="Geography" slices={data.byGeography} />
      </div>

      {/* Position breakdown table */}
      {data.positions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Position Weights</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Sector</TableHead>
                  <TableHead>Geography</TableHead>
                  <TableHead className="text-right">Market Value</TableHead>
                  <TableHead className="text-right">Weight</TableHead>
                  <TableHead className="text-right">Bar</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.positions.map((p) => (
                  <TableRow key={p.symbol}>
                    <TableCell className="font-mono font-semibold">{p.symbol}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">{p.sector}</Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{p.geography}</TableCell>
                    <TableCell className="text-right font-mono">{fmtMoney(p.marketValue)}</TableCell>
                    <TableCell className="text-right font-mono font-semibold">{p.pct}%</TableCell>
                    <TableCell className="text-right w-24">
                      <div className="h-2 rounded-full bg-muted overflow-hidden">
                        <div
                          className="h-full rounded-full bg-blue-500"
                          style={{ width: `${Math.min(p.pct * 2, 100)}%` }}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
