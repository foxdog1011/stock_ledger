"use client";

import { useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  useAnomaly, useAnomalyBatch,
  useAlerts, useCheckAlerts, useCreateAlert, useDeleteAlert,
} from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  AlertTriangle, Activity, ScanSearch, RefreshCw, ExternalLink,
  Bell, BellOff, CheckCircle, Trash2, Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fmtMoney, fmtDate } from "@/lib/format";
import type { AnomalyPoint, AnomalyBatchItem, PriceAlert } from "@/lib/types";

// ── Anomaly helpers ───────────────────────────────────────────────────────────

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

// ── Anomaly panel ─────────────────────────────────────────────────────────────

function AnomalyPanel() {
  const [inputSymbol, setInputSymbol] = useState("");
  const [symbol, setSymbol] = useState<string | null>(null);
  const { data: batchData, isLoading: batchLoading, refetch, isFetching } = useAnomalyBatch({ days: 120 });
  const { data, isLoading, error, refetch: refetchSingle } = useAnomaly(symbol, {
    days: 120, method: "both", zscoreThreshold: 2.5, aeThreshold: 2.5,
  });

  function run() {
    const s = inputSymbol.trim().toUpperCase();
    if (!s) return;
    if (s === symbol) refetchSingle();
    else setSymbol(s);
  }

  const allAnomalies: AnomalyPoint[] = data
    ? [...data.zscore_anomalies, ...data.ae_anomalies].sort((a, b) => b.date.localeCompare(a.date))
    : [];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <ScanSearch className="h-5 w-5 text-purple-500" />
          <span className="font-semibold">市場異動掃描</span>
        </div>
        <p className="text-sm text-muted-foreground">
          自動偵測持倉中的異常量價行為 — 搭配催化劑日曆與價格警示，形成完整的市場監控閉環
        </p>
      </div>

      <div className="rounded-lg border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
        <b className="text-foreground">理論依據：</b>
        重要的市場事件往往先在價格和成交量留下痕跡，才有公開消息。
        統計異動可能是知情交易者行動的訊號，建議結合催化劑日曆判斷是否有基本面原因。
      </div>

      {/* Batch scan */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-2">
              <ScanSearch className="h-4 w-4 text-purple-500" />
              持倉全局掃描
            </CardTitle>
            <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} />
              重新掃描
            </Button>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            自動偵測所有持倉中統計上不尋常的量價行為，提醒你在新聞前就注意市場變化。
          </p>
        </CardHeader>
        <CardContent>
          {batchLoading ? (
            <div className="space-y-2">{[0, 1, 2].map(i => <Skeleton key={i} className="h-10 w-full" />)}</div>
          ) : !batchData ? null : batchData.results.length === 0 ? (
            <div className="flex items-center gap-2 py-4 text-sm text-emerald-600">
              <Activity className="h-4 w-4" />
              掃描 {batchData.scanned} 支持倉股，近期無統計異動
            </div>
          ) : (
            <>
              <p className="text-xs text-muted-foreground mb-3">
                掃描 <b>{batchData.scanned}</b> 支持倉 — <b className="text-amber-600">{batchData.with_anomalies}</b> 支有異動
              </p>
              <div className="space-y-2">
                {batchData.results.map(item => (
                  <div
                    key={item.symbol}
                    className={cn(
                      "flex items-start justify-between rounded-lg border px-3 py-2.5 gap-3",
                      item.has_high_severity ? "border-red-200 bg-red-50/40" : "border-amber-200 bg-amber-50/40"
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
                      <Link href="/positions" className="text-xs text-muted-foreground hover:text-foreground" title="查看持倉">
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

      {/* Single symbol scan */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Activity className="h-4 w-4 text-blue-500" />
            個股異動查詢
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
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
          {isLoading && <Skeleton className="h-32 w-full" />}
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {(error as Error).message}
            </div>
          )}
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
                  {data.volume_enriched && <span className="text-xs font-normal text-sky-600">（量來自 yfinance）</span>}
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
                          <TableCell className="text-right font-mono text-sm">{fmtMoney(a.close, 2)}</TableCell>
                          <TableCell className={cn("text-right text-sm font-mono", a.price_change_pct > 0 ? "text-emerald-600" : "text-red-500")}>
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
    </div>
  );
}

// ── Alerts panel ──────────────────────────────────────────────────────────────

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
          className="w-36" required
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
          type="number" step="0.01" placeholder="觸發價格"
          value={price} onChange={(e) => setPrice(e.target.value)}
          className="w-32" required
        />
        <Input
          placeholder="備註 (選填)" value={note}
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

function AlertsPanel() {
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
          <p className="font-semibold">Price Alerts</p>
          <p className="text-sm text-muted-foreground">停損 / 目標價警示管理</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setShowTriggered((v) => !v)}>
            {showTriggered ? <Bell className="h-4 w-4 mr-1" /> : <BellOff className="h-4 w-4 mr-1" />}
            {showTriggered ? "只看監控中" : "顯示已觸發"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => checkAlerts.mutate()} disabled={checkAlerts.isPending}>
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
                        variant="ghost" size="icon"
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

// ── Tab bar ───────────────────────────────────────────────────────────────────

type MonitorTab = "anomaly" | "alerts";

const TABS: { value: MonitorTab; label: string }[] = [
  { value: "anomaly", label: "異常偵測" },
  { value: "alerts",  label: "價格警示" },
];

function MonitorContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const active = (searchParams.get("tab") as MonitorTab) ?? "anomaly";

  const setTab = (tab: MonitorTab) => {
    router.replace(`/monitor?tab=${tab}`);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">監控中心</h1>

      <div className="flex gap-1 border-b">
        {TABS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
              active === value
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {active === "anomaly" ? <AnomalyPanel /> : <AlertsPanel />}
    </div>
  );
}

export default function MonitorPage() {
  return (
    <Suspense>
      <MonitorContent />
    </Suspense>
  );
}
