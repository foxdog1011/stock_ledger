"use client";

import { useState } from "react";
import { Bell, BellOff, CheckCircle, Trash2, Plus, RefreshCw, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { useAlerts, useCheckAlerts, useCreateAlert, useDeleteAlert } from "@/hooks/use-queries";
import { fmtMoney } from "@/lib/format";
import type { PriceAlert } from "@/lib/types";

function today() {
  return new Date().toISOString().slice(0, 10);
}

function AlertTypeBadge({ type }: { type: PriceAlert["alertType"] }) {
  return type === "stop_loss" ? (
    <Badge variant="destructive" className="text-xs">停損</Badge>
  ) : (
    <Badge className="bg-emerald-600 text-white text-xs">目標</Badge>
  );
}

function AddAlertForm({ onClose }: { onClose: () => void }) {
  const [symbol, setSymbol] = useState("");
  const [alertType, setAlertType] = useState<"stop_loss" | "target">("stop_loss");
  const [price, setPrice] = useState("");
  const [note, setNote] = useState("");
  const createAlert = useCreateAlert();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!symbol || !price) return;
    createAlert.mutate(
      { symbol: symbol.toUpperCase(), alert_type: alertType, price: parseFloat(price), note },
      { onSuccess: () => { onClose(); setSymbol(""); setPrice(""); setNote(""); } },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="border rounded-lg p-4 bg-muted/30 space-y-3">
      <div className="flex gap-2 flex-wrap">
        <Input
          placeholder="股票代號 (e.g. 2337)"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          className="w-36"
          required
        />
        <select
          value={alertType}
          onChange={(e) => setAlertType(e.target.value as "stop_loss" | "target")}
          className="border rounded px-2 py-1 text-sm bg-background"
        >
          <option value="stop_loss">停損 (stop_loss)</option>
          <option value="target">目標價 (target)</option>
        </select>
        <Input
          type="number"
          step="0.01"
          placeholder="觸發價格"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          className="w-32"
          required
        />
        <Input
          placeholder="備註 (選填)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="flex-1 min-w-[120px]"
        />
        <Button type="submit" size="sm" disabled={createAlert.isPending}>
          {createAlert.isPending ? "新增中..." : "新增"}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>取消</Button>
      </div>
    </form>
  );
}

export default function AlertsPage() {
  const [showTriggered, setShowTriggered] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const { data: alerts, isLoading } = useAlerts(showTriggered);
  const checkAlerts = useCheckAlerts();
  const deleteAlert = useDeleteAlert();

  const active = alerts?.filter((a) => a.triggered === 0) ?? [];
  const triggered = alerts?.filter((a) => a.triggered === 1) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Price Alerts</h1>
          <p className="text-sm text-muted-foreground">停損 / 目標價警示管理</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowTriggered((v) => !v)}
          >
            {showTriggered ? <Bell className="h-4 w-4 mr-1" /> : <BellOff className="h-4 w-4 mr-1" />}
            {showTriggered ? "只看監控中" : "顯示已觸發"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => checkAlerts.mutate()}
            disabled={checkAlerts.isPending}
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${checkAlerts.isPending ? "animate-spin" : ""}`} />
            立即檢查
          </Button>
          <Button size="sm" onClick={() => setShowForm((v) => !v)}>
            <Plus className="h-4 w-4 mr-1" />
            新增警示
          </Button>
        </div>
      </div>

      {showForm && <AddAlertForm onClose={() => setShowForm(false)} />}

      {checkAlerts.data && (
        <Card className={checkAlerts.data.summary.triggeredNow > 0 ? "border-red-500" : "border-emerald-500"}>
          <CardContent className="pt-4">
            {checkAlerts.data.summary.triggeredNow > 0 ? (
              <div className="flex items-center gap-2 text-red-600 font-semibold">
                <AlertTriangle className="h-5 w-5" />
                觸發 {checkAlerts.data.summary.triggeredNow} 個警示！
              </div>
            ) : (
              <div className="flex items-center gap-2 text-emerald-600">
                <CheckCircle className="h-5 w-5" />
                無觸發警示（共 {checkAlerts.data.summary.stillPending} 個監控中）
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-amber-500" />
            監控中 ({active.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : active.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">無監控警示，點擊「新增警示」建立</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>代號</TableHead>
                  <TableHead>類型</TableHead>
                  <TableHead className="text-right">觸發價</TableHead>
                  <TableHead>備註</TableHead>
                  <TableHead>建立日期</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {active.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-mono font-semibold">{a.symbol}</TableCell>
                    <TableCell><AlertTypeBadge type={a.alertType} /></TableCell>
                    <TableCell className="text-right font-mono">{fmtMoney(a.price)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{a.note || "—"}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{a.createdAt.slice(0, 10)}</TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => deleteAlert.mutate(a.id)}
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

      {showTriggered && triggered.length > 0 && (
        <Card className="opacity-60">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-muted-foreground">
              <CheckCircle className="h-5 w-5" />
              已觸發 ({triggered.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>代號</TableHead>
                  <TableHead>類型</TableHead>
                  <TableHead className="text-right">觸發價</TableHead>
                  <TableHead>觸發日期</TableHead>
                  <TableHead>備註</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {triggered.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="font-mono font-semibold">{a.symbol}</TableCell>
                    <TableCell><AlertTypeBadge type={a.alertType} /></TableCell>
                    <TableCell className="text-right font-mono">{fmtMoney(a.price)}</TableCell>
                    <TableCell className="text-sm">{a.triggeredAt ?? "—"}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{a.note || "—"}</TableCell>
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
