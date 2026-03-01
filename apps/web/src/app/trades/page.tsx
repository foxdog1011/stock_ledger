"use client";

import { useState } from "react";
import { useTrades, useVoidTrade } from "@/hooks/use-queries";
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
import { fmtMoney } from "@/lib/format";
import { Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { Trade } from "@/lib/types";

export default function TradesPage() {
  const [symbol, setSymbol] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [showVoided, setShowVoided] = useState(false);

  // Confirmation dialog state
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Trades</h1>
        <AddTradeDialog>
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            Add Trade
          </Button>
        </AddTradeDialog>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="py-3 flex flex-wrap gap-3 items-center">
          <Input
            placeholder="Symbol (e.g. AAPL)"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-36 uppercase"
          />
          <Input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="w-40"
          />
          <span className="text-muted-foreground text-sm">to</span>
          <Input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="w-40"
          />
          {(symbol || start || end) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setSymbol(""); setStart(""); setEnd(""); }}
            >
              Clear
            </Button>
          )}

          {/* Show voided toggle */}
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

      {/* Table */}
      <Card>
        {tradesQuery.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
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
                <TableRow
                  key={t.id}
                  className={cn(t.isVoid && "opacity-40 line-through")}
                >
                  <TableCell className="font-mono text-sm">{t.date}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{t.symbol}</Badge>
                  </TableCell>
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
                  <TableCell className="text-right tabular-nums">
                    {fmtMoney(t.commission)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums font-medium">
                    {fmtMoney(t.qty * t.price)}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm max-w-xs truncate">
                    {t.note || "—"}
                  </TableCell>
                  <TableCell>
                    {!t.isVoid && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                        onClick={() => setVoidTarget(t)}
                        aria-label={`Void trade ${t.id}`}
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

      {/* Void confirmation dialog */}
      <Dialog open={!!voidTarget} onOpenChange={(open) => { if (!open) setVoidTarget(null); }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Void this trade?</DialogTitle>
          </DialogHeader>
          {voidTarget && (
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">
                {voidTarget.side.toUpperCase()} {voidTarget.qty} {voidTarget.symbol}
              </span>{" "}
              @ {fmtMoney(voidTarget.price, 4)} on {voidTarget.date}
              <br />
              This will remove the trade&apos;s cash and position impact.
              The record is kept for audit purposes.
            </p>
          )}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setVoidTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleVoidConfirm}
              disabled={voidMutation.isPending}
            >
              {voidMutation.isPending ? "Voiding…" : "Confirm Void"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
