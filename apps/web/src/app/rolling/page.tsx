"use client";

import { useState, useEffect } from "react";
import { RotateCcw, TrendingUp, PieChart, AlertTriangle, CheckCircle2, Plus, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  useRollingLog, useRollingLogSummary, useSectorCheck,
  useCreateRollingLog, useDeleteRollingLog,
} from "@/hooks/use-queries";
import { fmtMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { RollingAction, SectorCheckSector } from "@/lib/types";

function today() { return new Date().toISOString().slice(0, 10); }

const ACTION_LABELS: Record<RollingAction, { label: string; color: string }> = {
  roll:    { label: "Roll",    color: "bg-blue-500/10 text-blue-600 border-blue-200" },
  realize: { label: "認列",   color: "bg-emerald-500/10 text-emerald-600 border-emerald-200" },
  reopen:  { label: "重開倉", color: "bg-amber-500/10 text-amber-600 border-amber-200" },
  note:    { label: "備注",   color: "bg-slate-500/10 text-slate-600 border-slate-200" },
};

function ActionBadge({ action }: { action: RollingAction }) {
  const { label, color } = ACTION_LABELS[action];
  return <Badge variant="outline" className={cn("text-xs", color)}>{label}</Badge>;
}

function SectorBar({ sector }: { sector: SectorCheckSector }) {
  const pct = sector.pctOfPortfolio;
  const isOver = pct > 50;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{sector.sector}</span>
        <span className={cn("font-mono font-semibold", isOver ? "text-red-500" : "text-foreground")}>
          {pct}%
        </span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", isOver ? "bg-red-400" : "bg-blue-500")}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground">{sector.symbols.join(", ")} · {fmtMoney(sector.marketValue)}</p>
    </div>
  );
}

function AddRollingForm({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({
    date: today(),
    symbol: "",
    action: "realize" as RollingAction,
    shares: "",
    sell_price: "",
    buy_price: "",
    profit_amount: "",
    note: "",
  });
  const create = useCreateRollingLog();

  // Auto-calculate profit_amount when sell_price, buy_price, shares are all filled
  useEffect(() => {
    const sell = parseFloat(form.sell_price);
    const buy = parseFloat(form.buy_price);
    const shares = parseFloat(form.shares);
    if (!isNaN(sell) && !isNaN(buy) && !isNaN(shares) && shares > 0) {
      const profit = (sell - buy) * shares;
      setForm((f) => ({ ...f, profit_amount: profit.toFixed(2) }));
    }
  }, [form.sell_price, form.buy_price, form.shares]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.symbol || !form.date) return;
    create.mutate(
      {
        date: form.date,
        symbol: form.symbol.toUpperCase(),
        action: form.action,
        shares:        form.shares        ? parseFloat(form.shares)        : undefined,
        sell_price:    form.sell_price    ? parseFloat(form.sell_price)    : undefined,
        buy_price:     form.buy_price     ? parseFloat(form.buy_price)     : undefined,
        profit_amount: form.profit_amount ? parseFloat(form.profit_amount) : undefined,
        note: form.note,
      },
      { onSuccess: onClose },
    );
  }

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <form onSubmit={handleSubmit} className="border rounded-lg p-4 bg-muted/30 space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input type="date" value={form.date} onChange={set("date")}
          className="border rounded px-2 py-1 text-sm bg-background" required />
        <Input placeholder="代號" value={form.symbol} onChange={set("symbol")}
          className="w-24" required />
        <select value={form.action} onChange={set("action") as React.ChangeEventHandler<HTMLSelectElement>}
          className="border rounded px-2 py-1 text-sm bg-background">
          {(Object.keys(ACTION_LABELS) as RollingAction[]).map((a) => (
            <option key={a} value={a}>{ACTION_LABELS[a].label}</option>
          ))}
        </select>
        <Input type="number" step="1" placeholder="股數" value={form.shares} onChange={set("shares")}
          className="w-24" />
        <Input type="number" step="0.01" placeholder="賣出價" value={form.sell_price} onChange={set("sell_price")}
          className="w-24" />
        <Input type="number" step="0.01" placeholder="買回價" value={form.buy_price} onChange={set("buy_price")}
          className="w-24" />
        <Input type="number" step="0.01" placeholder="認列獲利 $" value={form.profit_amount} onChange={set("profit_amount")}
          className="w-28" />
        <Input placeholder="備註" value={form.note} onChange={set("note")}
          className="flex-1 min-w-[120px]" />
      </div>
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={create.isPending}>
          {create.isPending ? "儲存中..." : "儲存"}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>取消</Button>
      </div>
    </form>
  );
}

export default function RollingPage() {
  const [showForm, setShowForm] = useState(false);
  const { data: logs, isLoading: logsLoading } = useRollingLog({ limit: 50 });
  const { data: summary, isLoading: summaryLoading } = useRollingLogSummary();
  const { data: sector, isLoading: sectorLoading } = useSectorCheck();
  const deleteLog = useDeleteRollingLog();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <RotateCcw className="h-6 w-6 text-blue-500" />
            Rolling Position
          </h1>
          <p className="text-sm text-muted-foreground">Jimmy 風格：每日認列獲利 + 持續滾動部位</p>
        </div>
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus className="h-4 w-4 mr-1" />
          記錄 Rolling
        </Button>
      </div>

      {showForm && <AddRollingForm onClose={() => setShowForm(false)} />}

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm text-muted-foreground flex items-center gap-1">
              <TrendingUp className="h-4 w-4" /> 累積認列獲利
            </CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? <Skeleton className="h-8 w-24" /> : (
              <p className={cn("text-2xl font-bold font-mono",
                (summary?.grandTotalProfit ?? 0) >= 0 ? "text-emerald-600" : "text-red-500"
              )}>
                {summary?.grandTotalProfit != null
                  ? `${summary.grandTotalProfit >= 0 ? "+" : ""}${fmtMoney(summary.grandTotalProfit)}`
                  : "—"}
              </p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm text-muted-foreground">Rolling 次數</CardTitle>
          </CardHeader>
          <CardContent>
            {summaryLoading ? <Skeleton className="h-8 w-16" /> : (
              <p className="text-2xl font-bold">{summary?.totalRolls ?? 0}</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-1">
            <CardTitle className="text-sm text-muted-foreground">已覆蓋產業數</CardTitle>
          </CardHeader>
          <CardContent>
            {sectorLoading ? <Skeleton className="h-8 w-16" /> : (
              <div className="flex items-center gap-2">
                <p className="text-2xl font-bold">{sector?.uniqueSectors ?? 0}</p>
                <span className="text-muted-foreground text-sm">/ {sector?.totalPositions ?? 0} 持倉</span>
                {sector && sector.uniqueSectors === sector.totalPositions && sector.totalPositions > 0 && (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sector Rotation Check */}
      <Card className={sector?.alert ? "border-amber-400" : ""}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PieChart className="h-5 w-5 text-blue-500" />
            Sector Rotation 警示
            {sector?.alert && (
              <Badge variant="outline" className="border-amber-400 text-amber-600 bg-amber-50">
                <AlertTriangle className="h-3 w-3 mr-1" /> 集中警示
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {sectorLoading ? (
            <div className="space-y-3">{[1, 2, 3].map((i) => <Skeleton key={i} className="h-8 w-full" />)}</div>
          ) : !sector ? null : (
            <div className="space-y-4">
              {sector.alerts.length > 0 && (
                <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-700 space-y-1">
                  {sector.alerts.map((a, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 flex-shrink-0" />{a}
                    </div>
                  ))}
                </div>
              )}
              <div className="space-y-3">
                {sector.sectors.map((s) => (
                  <SectorBar key={s.sector} sector={s} />
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Jimmy 原則：每個持倉應屬於完全不同的產業，分散 Sector Rotation 風險。
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Per-symbol rolling summary */}
      {summary && summary.bySymbol.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">各股累積 Rolling 獲利</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>代號</TableHead>
                  <TableHead className="text-right">次數</TableHead>
                  <TableHead className="text-right">累積獲利</TableHead>
                  <TableHead className="text-right">平均每次</TableHead>
                  <TableHead>最後一次</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summary.bySymbol.map((s) => (
                  <TableRow key={s.symbol}>
                    <TableCell className="font-mono font-semibold">{s.symbol}</TableCell>
                    <TableCell className="text-right">{s.rollCount}</TableCell>
                    <TableCell className={cn("text-right font-mono", s.totalProfit >= 0 ? "text-emerald-600" : "text-red-500")}>
                      {s.totalProfit >= 0 ? "+" : ""}{fmtMoney(s.totalProfit)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-muted-foreground">
                      {fmtMoney(s.avgProfit)}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{s.lastRollDate}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Rolling Log */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Rolling 操作紀錄（最近 50 筆）</CardTitle>
        </CardHeader>
        <CardContent>
          {logsLoading ? (
            <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : !logs || logs.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              尚無紀錄。每天收盤後記錄是否有認列獲利，追蹤 Rolling 進度！
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>日期</TableHead>
                  <TableHead>代號</TableHead>
                  <TableHead>動作</TableHead>
                  <TableHead className="text-right">認列獲利</TableHead>
                  <TableHead className="text-right">賣出/買回</TableHead>
                  <TableHead>備註</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="text-sm">{log.date}</TableCell>
                    <TableCell className="font-mono font-semibold">{log.symbol}</TableCell>
                    <TableCell><ActionBadge action={log.action} /></TableCell>
                    <TableCell className={cn("text-right font-mono",
                      log.profitAmount != null && log.profitAmount >= 0 ? "text-emerald-600" : "text-red-500"
                    )}>
                      {log.profitAmount != null
                        ? `${log.profitAmount >= 0 ? "+" : ""}${fmtMoney(log.profitAmount)}`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right text-sm text-muted-foreground font-mono">
                      {log.sellPrice != null ? `${fmtMoney(log.sellPrice)}` : ""}
                      {log.sellPrice != null && log.buyPrice != null ? " → " : ""}
                      {log.buyPrice != null ? `${fmtMoney(log.buyPrice)}` : ""}
                      {log.sellPrice == null && log.buyPrice == null ? "—" : ""}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground max-w-[180px] truncate">
                      {log.note || "—"}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => deleteLog.mutate(log.id)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
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
