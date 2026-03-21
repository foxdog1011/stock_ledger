"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useScreener, useWatchlists, useAddWatchlistItem } from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Filter, ListPlus, TrendingUp, TrendingDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ScreenerResult } from "@/lib/types";

function YoyBadge({ pct }: { pct: number | null }) {
  if (pct == null) return <span className="text-muted-foreground text-xs">—</span>;
  const cls = pct >= 0
    ? "text-emerald-600 bg-emerald-50 border-emerald-200"
    : "text-red-500 bg-red-50 border-red-200";
  return (
    <Badge variant="outline" className={cn("text-xs", cls)}>
      {pct >= 0 ? "+" : ""}{pct.toFixed(1)}%
    </Badge>
  );
}

function ForeignNetBadge({ net }: { net: number | null }) {
  if (net == null) return <span className="text-muted-foreground text-xs">—</span>;
  const cls = net >= 0 ? "text-emerald-600" : "text-red-500";
  const Icon = net >= 0 ? TrendingUp : TrendingDown;
  return (
    <div className={cn("flex items-center gap-1 text-xs", cls)}>
      <Icon className="h-3 w-3" />
      {(net / 1000).toFixed(0)}K
    </div>
  );
}

function AddToWatchlistDialog({
  symbol,
  open,
  onClose,
}: {
  symbol: string;
  open: boolean;
  onClose: () => void;
}) {
  const { data: watchlists } = useWatchlists();
  const addItem = useAddWatchlistItem();
  const [selectedId, setSelectedId] = useState<string>("");

  async function add() {
    if (!selectedId) return;
    try {
      await addItem.mutateAsync({ watchlistId: Number(selectedId), symbol });
      toast.success(`${symbol} added to watchlist`);
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-xs">
        <DialogHeader>
          <DialogTitle>Add {symbol} to Watchlist</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 mt-2">
          <Select value={selectedId} onValueChange={setSelectedId}>
            <SelectTrigger>
              <SelectValue placeholder="Select a watchlist" />
            </SelectTrigger>
            <SelectContent>
              {(watchlists ?? []).map((w) => (
                <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
            <Button size="sm" disabled={!selectedId || addItem.isPending} onClick={add}>Add</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function ScreenerPage() {
  const [sector, setSector] = useState("");
  const [country, setCountry] = useState("");
  const [minYoy, setMinYoy] = useState("");
  const [inPositions, setInPositions] = useState<boolean | undefined>(undefined);
  const [foreignPos, setForeignPos] = useState<boolean | undefined>(undefined);
  const [addTarget, setAddTarget] = useState<string | null>(null);

  const params = {
    sector: sector || undefined,
    country: country || undefined,
    minYoyPct: minYoy ? Number(minYoy) : undefined,
    inPositions,
    foreignNetPositive: foreignPos,
    limit: 100,
  };

  const { data, isLoading, refetch } = useScreener(params);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Filter className="h-6 w-6 text-blue-500" />
          股票篩選器
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          從 Universe 依產業、法人動態、月營收篩選股票
        </p>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">篩選條件</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3 items-end">
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">產業 Sector</p>
              <Input
                placeholder="e.g. 半導體"
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                className="w-36 h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">國家 Country</p>
              <Input
                placeholder="TW / US"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                className="w-24 h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">月營收 YoY % ≥</p>
              <Input
                type="number"
                placeholder="e.g. 10"
                value={minYoy}
                onChange={(e) => setMinYoy(e.target.value)}
                className="w-24 h-8 text-sm"
              />
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">持倉狀態</p>
              <Select
                value={inPositions == null ? "all" : inPositions ? "yes" : "no"}
                onValueChange={(v) => setInPositions(v === "all" ? undefined : v === "yes")}
              >
                <SelectTrigger className="w-32 h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="yes">持倉中</SelectItem>
                  <SelectItem value="no">未持倉</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">外資動態</p>
              <Select
                value={foreignPos == null ? "all" : foreignPos ? "buy" : "sell"}
                onValueChange={(v) => setForeignPos(v === "all" ? undefined : v === "buy")}
              >
                <SelectTrigger className="w-32 h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="buy">外資淨買</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button size="sm" className="h-8" onClick={() => refetch()}>
              篩選
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => {
                setSector(""); setCountry(""); setMinYoy("");
                setInPositions(undefined); setForeignPos(undefined);
              }}
            >
              重設
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">
            結果 {data ? `(${data.total} 筆)` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2">
              {[0,1,2,3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : !data || data.results.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              沒有符合條件的股票。請調整篩選條件後重試。
            </p>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>代號</TableHead>
                    <TableHead>名稱</TableHead>
                    <TableHead>產業</TableHead>
                    <TableHead>交易所</TableHead>
                    <TableHead className="text-right">月營收 YoY</TableHead>
                    <TableHead className="text-right">外資淨買 (10日)</TableHead>
                    <TableHead>狀態</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.results.map((r: ScreenerResult) => (
                    <TableRow key={r.symbol}>
                      <TableCell className="font-mono font-semibold">{r.symbol}</TableCell>
                      <TableCell className="text-sm">{r.name}</TableCell>
                      <TableCell>
                        {r.sector && (
                          <Badge variant="outline" className="text-xs">{r.sector}</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{r.exchange || "—"}</TableCell>
                      <TableCell className="text-right">
                        <YoyBadge pct={r.revenue?.latestYoyPct ?? null} />
                      </TableCell>
                      <TableCell className="text-right">
                        <ForeignNetBadge net={r.chip?.foreignNetSum ?? null} />
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          {r.inPositions && (
                            <Badge className="text-xs bg-blue-600 text-white">持倉</Badge>
                          )}
                          {r.inWatchlist && (
                            <Badge variant="outline" className="text-xs">追蹤中</Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {!r.inWatchlist && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs"
                            onClick={() => setAddTarget(r.symbol)}
                          >
                            <ListPlus className="h-3 w-3 mr-1" />
                            加入
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {addTarget && (
        <AddToWatchlistDialog
          symbol={addTarget}
          open={!!addTarget}
          onClose={() => setAddTarget(null)}
        />
      )}
    </div>
  );
}
