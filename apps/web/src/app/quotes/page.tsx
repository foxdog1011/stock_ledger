"use client";

import { useState } from "react";
import { useLastPrice } from "@/hooks/use-queries";
import { usePositions } from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AddQuoteDialog } from "@/components/forms/add-quote-dialog";
import { fmtMoney } from "@/lib/format";
import { Plus, Search } from "lucide-react";

function PriceLookup() {
  const [input, setInput] = useState("");
  const [symbol, setSymbol] = useState("");

  const query = useLastPrice(symbol);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Price Lookup</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder="Symbol (e.g. AAPL)"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && setSymbol(input.trim())}
            className="uppercase"
          />
          <Button variant="outline" onClick={() => setSymbol(input.trim())}>
            <Search className="h-4 w-4" />
          </Button>
        </div>
        {query.isLoading && symbol && <Skeleton className="h-12 w-full" />}
        {query.data && (
          <div className="flex items-center justify-between rounded-md border p-3">
            <div className="flex items-center gap-2">
              <Badge variant="secondary">{query.data.symbol}</Badge>
              <span className="text-xs text-muted-foreground">{query.data.priceSource ?? "—"}</span>
            </div>
            <span className="font-semibold tabular-nums">
              {query.data.price != null ? `$${fmtMoney(query.data.price, 4)}` : "No price"}
            </span>
          </div>
        )}
        {query.isError && (
          <p className="text-destructive text-sm">Symbol not found or no price available</p>
        )}
      </CardContent>
    </Card>
  );
}

function PositionPrices() {
  const positions = usePositions({ includeClosed: false });
  const rows = positions.data ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Current Position Prices</CardTitle>
        <AddQuoteDialog>
          <Button size="sm">
            <Plus className="h-4 w-4 mr-1" />
            Add Quote
          </Button>
        </AddQuoteDialog>
      </CardHeader>
      <CardContent className="p-0">
        {positions.isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : !rows.length ? (
          <p className="p-6 text-center text-muted-foreground text-sm">No open positions</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead className="text-right">Last Price</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => (
                <TableRow key={p.symbol}>
                  <TableCell>
                    <Badge variant="secondary">{p.symbol}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {p.lastPrice != null ? `$${fmtMoney(p.lastPrice, 4)}` : "—"}
                  </TableCell>
                  <TableCell>
                    <span className="text-xs text-muted-foreground">{p.priceSource ?? "—"}</span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export default function QuotesPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Quotes</h1>
      <div className="grid md:grid-cols-2 gap-6">
        <PriceLookup />
        <PositionPrices />
      </div>
    </div>
  );
}
