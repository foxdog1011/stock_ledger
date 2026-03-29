"use client";

import { useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";
import { useTrades, useVoidTrade, useCashTx, useCashBalance, useVoidCash } from "@/hooks/use-queries";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AddTradeDialog } from "@/components/forms/add-trade-dialog";
import { AddCashDialog } from "@/components/forms/add-cash-dialog";
import { fmtMoney, pnlClass } from "@/lib/format";
import { Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { Trade, CashTx } from "@/lib/types";

// ── Trades panel ──────────────────────────────────────────────────────────────

function TradesPanel() {
  const [symbol, setSymbol] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [showVoided, setShowVoided] = useState(false);
  const [voidTarget, setVoidTarget] = useState<Trade | null>(null);
  const voidMutation = useVoidTrade();

  const tradesQuery = useTrades({
    symbol: symbol.trim().toUpperCase() || undefined,
    start: start || undefined,
    end: end || undefined,
    includeVoid: showVoided,
  });

  const rows = tradesQuery.data ?? [];
  const activeCount = rows.filter((r) => !r.isVoid).length;

  const handleVoidConfirm = async () => {
    if (!voidTarget) return;
    try {
      await voidMutation.mutateAsync(voidTarget.id);
      toast.success(`Voided: ${voidTarget.side.toUpperCase()} ${voidTarget.qty} ${voidTarget.symbol}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Void failed");
    } finally {
      setVoidTarget(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span />
        <AddTradeDialog>
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            Add Trade
          </Button>
        </AddTradeDialog>
      </div>

      <Card>
        <CardContent className="py-3 flex flex-wrap gap-3 items-center">
          <Input
            placeholder="Symbol (e.g. AAPL)"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-36 uppercase"
          />
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-40" />
          <span className="text-muted-foreground text-sm">to</span>
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-40" />
          {(symbol || start || end) && (
            <Button variant="ghost" size="sm" onClick={() => { setSymbol(""); setStart(""); setEnd(""); }}>
              Clear
            </Button>
          )}
          <Button
            variant={showVoided ? "secondary" : "outline"}
            size="sm"
            onClick={() => setShowVoided((v) => !v)}
            className="ml-auto"
          >
            {showVoided ? "Hide Voided" : "Show Voided"}
          </Button>
          <span className="text-sm text-muted-foreground">
            {activeCount} active
            {showVoided && rows.length !== activeCount && ` + ${rows.length - activeCount} voided`}
          </span>
        </CardContent>
      </Card>

      <Card>
        {tradesQuery.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : tradesQuery.isError ? (
          <p className="p-6 text-center text-destructive text-sm">Failed to load trades</p>
        ) : !rows.length ? (
          <p className="p-6 text-center text-muted-foreground text-sm">No trades found</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Side</TableHead>
                <TableHead className="text-right">Qty</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Commission</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Note</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((t) => (
                <TableRow key={t.id} className={cn(t.isVoid && "opacity-40 line-through")}>
                  <TableCell className="font-mono text-sm">{t.date}</TableCell>
                  <TableCell><Badge variant="secondary">{t.symbol}</Badge></TableCell>
                  <TableCell>
                    {t.isVoid ? (
                      <Badge variant="outline" className="text-muted-foreground">VOID</Badge>
                    ) : (
                      <Badge variant={t.side === "buy" ? "default" : "outline"}>
                        {t.side.toUpperCase()}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{t.qty}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtMoney(t.price, 4)}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtMoney(t.commission)}</TableCell>
                  <TableCell className="text-right tabular-nums font-medium">{fmtMoney(t.qty * t.price)}</TableCell>
                  <TableCell className="text-muted-foreground text-sm max-w-xs truncate">{t.note || "—"}</TableCell>
                  <TableCell>
                    {!t.isVoid && (
                      <Button
                        variant="ghost" size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => setVoidTarget(t)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={!!voidTarget} onOpenChange={(open) => { if (!open) setVoidTarget(null); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>Void this trade?</DialogTitle></DialogHeader>
          {voidTarget && (
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">
                {voidTarget.side.toUpperCase()} {voidTarget.qty} {voidTarget.symbol}
              </span>{" "}
              @ {fmtMoney(voidTarget.price, 4)} on {voidTarget.date}
              <br />
              This will remove the trade&apos;s cash and position impact.
            </p>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setVoidTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleVoidConfirm} disabled={voidMutation.isPending}>
              {voidMutation.isPending ? "Voiding…" : "Confirm Void"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Cash panel ────────────────────────────────────────────────────────────────

const TYPE_VARIANT: Record<string, "default" | "secondary" | "success" | "destructive"> = {
  deposit: "success",
  withdrawal: "destructive",
  buy: "secondary",
  sell: "default",
};

function CashPanel() {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [showVoided, setShowVoided] = useState(false);
  const [voidTarget, setVoidTarget] = useState<CashTx | null>(null);
  const voidMutation = useVoidCash();

  const txQuery = useCashTx({ start: start || undefined, end: end || undefined, includeVoid: showVoided });
  const balance = useCashBalance();

  const rows = txQuery.data ?? [];
  const activeRows = rows.filter((r) => !r.isVoid);
  const inflow = activeRows.filter((r) => r.amount > 0).reduce((s, r) => s + r.amount, 0);
  const outflow = activeRows.filter((r) => r.amount < 0).reduce((s, r) => s + r.amount, 0);

  const handleVoidConfirm = async () => {
    if (!voidTarget || voidTarget.id == null) return;
    try {
      await voidMutation.mutateAsync(voidTarget.id);
      const label = voidTarget.type === "deposit" ? "Deposit" : "Withdrawal";
      toast.success(`Voided: ${label} ${fmtMoney(Math.abs(voidTarget.amount))} on ${voidTarget.date}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Void failed");
    } finally {
      setVoidTarget(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span />
        <AddCashDialog>
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            Add Cash
          </Button>
        </AddCashDialog>
      </div>

      <Card>
        <CardContent className="py-3 flex flex-wrap gap-3 items-center">
          <span className="text-sm text-muted-foreground">Date range:</span>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-40" />
          <span className="text-muted-foreground text-sm">to</span>
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-40" />
          {(start || end) && (
            <Button variant="ghost" size="sm" onClick={() => { setStart(""); setEnd(""); }}>Clear</Button>
          )}
          <Button
            variant={showVoided ? "secondary" : "outline"}
            size="sm"
            onClick={() => setShowVoided((v) => !v)}
            className="ml-auto"
          >
            {showVoided ? "Hide Voided" : "Show Voided"}
          </Button>
          <div className="text-sm text-muted-foreground">
            Balance:{" "}
            <span className="font-semibold text-foreground">${fmtMoney(balance.data?.balance)}</span>
          </div>
        </CardContent>
      </Card>

      {!txQuery.isLoading && activeRows.length > 0 && (
        <div className="grid grid-cols-3 gap-3 text-center">
          <Card><CardContent className="py-3">
            <p className="text-xs text-muted-foreground">Inflow</p>
            <p className="font-semibold text-emerald-600 tabular-nums">${fmtMoney(inflow)}</p>
          </CardContent></Card>
          <Card><CardContent className="py-3">
            <p className="text-xs text-muted-foreground">Outflow</p>
            <p className="font-semibold text-red-500 tabular-nums">${fmtMoney(outflow)}</p>
          </CardContent></Card>
          <Card><CardContent className="py-3">
            <p className="text-xs text-muted-foreground">Net</p>
            <p className={`font-semibold tabular-nums ${pnlClass(inflow + outflow)}`}>
              ${fmtMoney(inflow + outflow)}
            </p>
          </CardContent></Card>
        </div>
      )}

      <Card>
        {txQuery.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          </div>
        ) : txQuery.isError ? (
          <p className="p-6 text-center text-destructive text-sm">Failed to load cash flow</p>
        ) : !rows.length ? (
          <p className="p-6 text-center text-muted-foreground text-sm">No transactions found</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead className="text-right">Balance</TableHead>
                <TableHead>Note</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, i) => (
                <TableRow key={i} className={cn(row.isVoid && "opacity-40 line-through")}>
                  <TableCell className="font-mono text-sm">{row.date}</TableCell>
                  <TableCell>
                    {row.isVoid ? (
                      <Badge variant="outline" className="text-muted-foreground">VOID</Badge>
                    ) : (
                      <Badge variant={TYPE_VARIANT[row.type] ?? "outline"}>{row.type}</Badge>
                    )}
                  </TableCell>
                  <TableCell>{row.symbol ?? "—"}</TableCell>
                  <TableCell className={`text-right tabular-nums ${pnlClass(row.amount)}`}>
                    {row.amount >= 0 ? "+" : ""}${fmtMoney(row.amount)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">${fmtMoney(row.balance)}</TableCell>
                  <TableCell className="text-muted-foreground text-sm max-w-xs truncate">{row.note || "—"}</TableCell>
                  <TableCell>
                    {!row.isVoid && row.id != null && (row.type === "deposit" || row.type === "withdrawal") && (
                      <Button
                        variant="ghost" size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => setVoidTarget(row)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      <Dialog open={!!voidTarget} onOpenChange={(open) => { if (!open) setVoidTarget(null); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>Void this entry?</DialogTitle></DialogHeader>
          {voidTarget && (
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">
                {voidTarget.type.charAt(0).toUpperCase() + voidTarget.type.slice(1)}{" "}
                ${fmtMoney(Math.abs(voidTarget.amount))}
              </span>{" "}
              on {voidTarget.date}
              {voidTarget.note && <> — {voidTarget.note}</>}
              <br />
              This will remove the entry&apos;s cash impact.
            </p>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setVoidTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleVoidConfirm} disabled={voidMutation.isPending}>
              {voidMutation.isPending ? "Voiding…" : "Confirm Void"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

type LedgerTab = "trades" | "cash";

const TABS: { value: LedgerTab; label: string }[] = [
  { value: "trades", label: "交易紀錄" },
  { value: "cash",   label: "現金" },
];

function LedgerContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const active = (searchParams.get("tab") as LedgerTab) ?? "trades";

  const setTab = (tab: LedgerTab) => {
    router.replace(`/ledger?tab=${tab}`);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">帳務紀錄</h1>

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

      {active === "trades" ? <TradesPanel /> : <CashPanel />}
    </div>
  );
}

export default function LedgerPage() {
  return (
    <Suspense>
      <LedgerContent />
    </Suspense>
  );
}
