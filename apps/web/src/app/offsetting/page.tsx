"use client";

import { useState } from "react";
import { useLosingPositions, useProfitInventory, useOffsetSimulate } from "@/hooks/use-queries";
import type { LosingPositionItem, OffsetSimulateResult } from "@/lib/types";
import { fmtMoney, fmtPct } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { ShieldCheck, ShieldX, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";

// ── Guardrail result panel ─────────────────────────────────────────────────────

const REASON_LABELS: Record<string, string> = {
  no_price:            "No last price available. Enter a price manually to simulate.",
  qty_exceeds_position:"Quantity exceeds the current position size.",
  not_a_loss:          "At this price the exit would not be a loss.",
  over_offset:         "The realized loss exceeds available profit inventory. Net result would remain negative.",
};

function GuardrailPanel({ result }: { result: OffsetSimulateResult }) {
  const { guardrail, simulation, profitInventory } = result;
  const avail = profitInventory.summary.availableToOffset;

  return (
    <div className="mt-4 space-y-3">
      {/* Pass / Fail badge */}
      <div className="flex items-center gap-3">
        {guardrail.passed ? (
          <>
            <ShieldCheck className="h-6 w-6 text-green-600" />
            <span className="text-lg font-semibold text-green-700">Exit Allowed</span>
            <Badge className="bg-green-100 text-green-800 border-green-300">PASSED</Badge>
          </>
        ) : (
          <>
            <ShieldX className="h-6 w-6 text-red-600" />
            <span className="text-lg font-semibold text-red-700">Exit Blocked</span>
            <Badge variant="destructive">FAILED</Badge>
          </>
        )}
      </div>

      {/* Reason */}
      {!guardrail.passed && guardrail.reason && (
        <p className="text-sm text-muted-foreground">
          {REASON_LABELS[guardrail.reason] ?? guardrail.reason}
        </p>
      )}

      {/* Simulation numbers */}
      {simulation.simPrice != null && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
          <div className="bg-muted/40 rounded-md p-3">
            <p className="text-xs text-muted-foreground mb-1">Sim Qty</p>
            <p className="font-medium">{simulation.simQty.toLocaleString()}</p>
          </div>
          <div className="bg-muted/40 rounded-md p-3">
            <p className="text-xs text-muted-foreground mb-1">Sim Price</p>
            <p className="font-medium">{fmtMoney(simulation.simPrice)}</p>
          </div>
          <div className="bg-muted/40 rounded-md p-3">
            <p className="text-xs text-muted-foreground mb-1">Realized Loss</p>
            <p className={`font-medium ${(simulation.simRealizedLoss ?? 0) < 0 ? "text-red-600" : "text-green-600"}`}>
              {simulation.simRealizedLoss != null ? fmtMoney(simulation.simRealizedLoss) : "—"}
            </p>
          </div>
          <div className="bg-muted/40 rounded-md p-3">
            <p className="text-xs text-muted-foreground mb-1">Covered by Profit</p>
            <p className="font-medium text-blue-700">
              {simulation.matchedAmount != null ? fmtMoney(simulation.matchedAmount) : "—"}
            </p>
          </div>
        </div>
      )}

      {/* Projected gross P&L */}
      {simulation.projectedGrossRealizedPnl != null && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Projected gross realized P&L after exit:</span>
          <span className={`font-semibold ${simulation.projectedGrossRealizedPnl >= 0 ? "text-green-700" : "text-red-600"}`}>
            {fmtMoney(simulation.projectedGrossRealizedPnl)}
          </span>
          <span className="text-muted-foreground text-xs">(available now: {fmtMoney(avail)})</span>
        </div>
      )}

      {simulation.commissionNotIncluded && (
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />
          Commission & tax not included in simulation.
        </p>
      )}
    </div>
  );
}

// ── Simulate panel (inline per position) ──────────────────────────────────────

function SimulatePanel({ pos }: { pos: LosingPositionItem }) {
  const [qty,   setQty]   = useState(String(pos.qty));
  const [price, setPrice] = useState(pos.lastPrice != null ? String(pos.lastPrice) : "");
  const [params, setParams] = useState<{ symbol: string; qty?: number; price?: number } | null>(null);

  const { data: result, isFetching } = useOffsetSimulate(params);

  function run() {
    const q = parseFloat(qty);
    const p = parseFloat(price);
    setParams({
      symbol: pos.symbol,
      qty:    isNaN(q) ? undefined : q,
      price:  isNaN(p) ? undefined : p,
    });
  }

  return (
    <div className="pt-4 border-t mt-4 space-y-4">
      <p className="text-sm font-medium text-muted-foreground">Simulate exit</p>
      <div className="flex flex-wrap gap-4 items-end">
        <div className="space-y-1">
          <Label className="text-xs">Qty (max {pos.qty})</Label>
          <Input
            type="number"
            min={1}
            max={pos.qty}
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            className="w-32"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-xs">Price</Label>
          <Input
            type="number"
            step="0.01"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder={pos.lastPrice != null ? String(pos.lastPrice) : "Enter price"}
            className="w-32"
          />
        </div>
        <Button onClick={run} disabled={isFetching} size="sm">
          {isFetching ? "Running…" : "Run"}
        </Button>
      </div>
      {result && <GuardrailPanel result={result} />}
    </div>
  );
}

// ── Losing position card ───────────────────────────────────────────────────────

function LosingPositionCard({ pos }: { pos: LosingPositionItem }) {
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          {/* Left: symbol + metrics */}
          <div className="flex flex-wrap gap-6">
            <div>
              <p className="text-xs text-muted-foreground">Symbol</p>
              <p className="font-semibold text-base">{pos.symbol}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Qty</p>
              <p className="font-medium">{pos.qty.toLocaleString()}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Avg Cost</p>
              <p className="font-medium">{pos.avgCost != null ? fmtMoney(pos.avgCost) : "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Last Price</p>
              <p className="font-medium">{pos.lastPrice != null ? fmtMoney(pos.lastPrice) : "—"}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Unrealized P&L</p>
              <p className="font-semibold text-red-600">
                {fmtMoney(pos.unrealizedPnl)}
                {pos.unrealizedPct != null && (
                  <span className="ml-1 text-sm">({fmtPct(pos.unrealizedPct / 100)})</span>
                )}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Full-exit Loss</p>
              <p className="font-medium text-red-600">{fmtMoney(-pos.lossIfFullExit)}</p>
            </div>
          </div>

          {/* Right: expand button */}
          <Button variant="outline" size="sm" onClick={() => setOpen((v) => !v)}>
            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            <span className="ml-1">{open ? "Hide" : "Simulate"}</span>
          </Button>
        </div>

        {open && <SimulatePanel pos={pos} />}
      </CardContent>
    </Card>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function OffsettingPage() {
  const { data: losing,    isLoading: loadingLosing }    = useLosingPositions();
  const { data: inventory, isLoading: loadingInventory } = useProfitInventory();

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Offsetting 守門機制</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Before exiting a losing position, verify that available realized profits can fully absorb the loss.
        </p>
      </div>

      {/* Profit Inventory summary */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Profit Inventory</CardTitle>
        </CardHeader>
        <CardContent>
          {loadingInventory ? (
            <div className="grid grid-cols-3 gap-4">
              {[0,1,2].map((i) => <Skeleton key={i} className="h-14" />)}
            </div>
          ) : inventory ? (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Available to Offset</p>
                <p className={`text-2xl font-bold ${inventory.summary.availableToOffset > 0 ? "text-green-700" : "text-muted-foreground"}`}>
                  {fmtMoney(inventory.summary.availableToOffset)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Gross Realized P&L</p>
                <p className={`text-xl font-semibold ${inventory.summary.grossRealizedPnl >= 0 ? "text-green-700" : "text-red-600"}`}>
                  {fmtMoney(inventory.summary.grossRealizedPnl)}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Positive Realized (sum)</p>
                <p className="text-xl font-semibold text-green-700">
                  {fmtMoney(inventory.summary.positiveRealizedPnl)}
                </p>
              </div>
            </div>
          ) : null}

          {/* Per-symbol breakdown (collapsed by default, show top 5) */}
          {inventory && inventory.bySymbol.length > 0 && (
            <>
              <Separator className="my-4" />
              <p className="text-xs font-medium text-muted-foreground mb-2">Realized P&L by symbol</p>
              <div className="space-y-1">
                {inventory.bySymbol.map((s) => (
                  <div key={s.symbol} className="flex items-center justify-between text-sm">
                    <span className="font-medium w-20">{s.symbol}</span>
                    <span className={s.realizedPnl >= 0 ? "text-green-700" : "text-red-600"}>
                      {fmtMoney(s.realizedPnl)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Losing positions */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wide">
          Losing Positions
        </h2>

        {loadingLosing ? (
          <div className="space-y-3">
            {[0,1].map((i) => <Skeleton key={i} className="h-24" />)}
          </div>
        ) : losing && losing.length > 0 ? (
          <div className="space-y-3">
            {losing.map((pos) => (
              <LosingPositionCard key={pos.symbol} pos={pos} />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="py-10 text-center text-muted-foreground">
              <ShieldCheck className="h-10 w-10 mx-auto mb-3 text-green-500" />
              <p className="font-medium">No losing positions</p>
              <p className="text-sm mt-1">All open positions are currently in profit.</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
