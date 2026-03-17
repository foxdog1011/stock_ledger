"use client";

import { useState, useRef } from "react";
import { Plus, Archive, ArchiveRestore, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useWatchlists,
  useWatchlistItems,
  useWatchlistGaps,
  useCreateWatchlist,
  useAddWatchlistItem,
  useArchiveWatchlistItem,
} from "@/hooks/use-queries";
import type { WatchlistItem } from "@/lib/types";

// ── Create Watchlist Dialog ───────────────────────────────────────────────────

function CreateWatchlistDialog() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const mut = useCreateWatchlist();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    mut.mutate(
      { name: name.trim() },
      {
        onSuccess: () => {
          toast.success(`Watchlist "${name.trim()}" created`);
          setName("");
          setOpen(false);
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4 mr-1.5" /> New Watchlist
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Create Watchlist</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3 pt-2">
          <Input
            placeholder="Watchlist name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!name.trim() || mut.isPending}>
              {mut.isPending && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />}
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Add Symbol Row ────────────────────────────────────────────────────────────

function AddSymbolRow({ watchlistId }: { watchlistId: number }) {
  const [symbol, setSymbol] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const mut = useAddWatchlistItem();

  function handleAdd(sym: string) {
    const s = sym.trim().toUpperCase();
    if (!s) return;
    mut.mutate(
      { watchlistId, symbol: s },
      {
        onSuccess: () => {
          toast.success(`${s} added`);
          setSymbol("");
          inputRef.current?.focus();
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); handleAdd(symbol); }}
      className="flex gap-2 pt-2"
    >
      <Input
        ref={inputRef}
        placeholder="Add symbol, e.g. AAPL"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value.toUpperCase())}
        className="max-w-[200px] font-mono"
      />
      <Button type="submit" size="sm" variant="outline" disabled={!symbol.trim() || mut.isPending}>
        {mut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
        Add
      </Button>
    </form>
  );
}

// ── Watchlist Card ────────────────────────────────────────────────────────────

function WatchlistCard({ watchlistId, name }: { watchlistId: number; name: string }) {
  const [showArchived, setShowArchived] = useState(false);
  const { data: items, isLoading: itemsLoading } = useWatchlistItems(watchlistId, showArchived);
  const { data: gaps } = useWatchlistGaps(watchlistId);
  const addMut = useAddWatchlistItem();
  const archiveMut = useArchiveWatchlistItem();

  const activeItems = items?.filter((i) => i.status !== "archived") ?? [];
  const archivedItems = items?.filter((i) => i.status === "archived") ?? [];
  const coverageSufficient = gaps?.coverageSufficient ?? true;
  const gapCount = gaps?.gap ?? 0;
  const notInWatchlist = gaps?.positionsNotInWatchlist ?? [];

  function quickAdd(sym: string) {
    addMut.mutate(
      { watchlistId, symbol: sym },
      {
        onSuccess: () => toast.success(`${sym} added`),
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  function archive(item: WatchlistItem) {
    archiveMut.mutate(
      { watchlistId, itemId: item.id },
      {
        onSuccess: () => toast.success(`${item.symbol} archived`),
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <CardTitle className="text-base">{name}</CardTitle>
          <div className="flex items-center gap-2">
            {gaps && (
              <span className="text-xs text-muted-foreground">
                {gaps.currentActiveItemCount} / {gaps.requiredWatchlistCount} required
              </span>
            )}
            {coverageSufficient ? (
              <Badge variant="outline" className="text-emerald-600 border-emerald-300 text-xs">
                <CheckCircle2 className="h-3 w-3 mr-1" /> OK
              </Badge>
            ) : (
              <Badge variant="outline" className="text-red-500 border-red-300 text-xs">
                <AlertTriangle className="h-3 w-3 mr-1" /> -{gapCount} short
              </Badge>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Gap: positions not yet in this watchlist */}
        {notInWatchlist.length > 0 && (
          <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 space-y-1.5">
            <p className="text-xs font-medium text-amber-700">
              Open positions not in this watchlist:
            </p>
            <div className="flex flex-wrap gap-1.5">
              {notInWatchlist.map((sym) => (
                <button
                  key={sym}
                  onClick={() => quickAdd(sym)}
                  disabled={addMut.isPending}
                  className="font-mono text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 hover:bg-amber-200 border border-amber-300 transition-colors disabled:opacity-50"
                >
                  + {sym}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Active items table */}
        {itemsLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : activeItems.length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No symbols yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Thesis</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {activeItems.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-mono font-medium">{item.symbol}</TableCell>
                  <TableCell>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      item.status === "monitoring"
                        ? "bg-blue-100 text-blue-800"
                        : "bg-gray-100 text-gray-700"
                    }`}>
                      {item.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-[240px] truncate">
                    {item.thesisSummary || "—"}
                  </TableCell>
                  <TableCell>
                    <button
                      onClick={() => archive(item)}
                      disabled={archiveMut.isPending}
                      className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                      title="Archive"
                    >
                      <Archive className="h-4 w-4" />
                    </button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Archived section toggle */}
        {archivedItems.length > 0 && (
          <button
            onClick={() => setShowArchived((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
          >
            <ArchiveRestore className="h-3.5 w-3.5" />
            {showArchived
              ? `Hide ${archivedItems.length} archived`
              : `Show ${archivedItems.length} archived`}
          </button>
        )}

        {/* Archived items table */}
        {showArchived && archivedItems.length > 0 && (
          <Table>
            <TableBody>
              {archivedItems.map((item) => (
                <TableRow key={item.id} className="opacity-50">
                  <TableCell className="font-mono text-sm">{item.symbol}</TableCell>
                  <TableCell>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                      archived
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-[240px] truncate">
                    {item.thesisSummary || "—"}
                  </TableCell>
                  <TableCell />
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {/* Add symbol */}
        <AddSymbolRow watchlistId={watchlistId} />
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WatchlistPage() {
  const { data: watchlists, isLoading, isError } = useWatchlists();

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Watchlist</h1>
        <CreateWatchlistDialog />
      </div>

      {isError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-md px-4 py-3">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          Failed to load watchlists.
        </div>
      )}

      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-40 w-full rounded-lg" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      )}

      {!isLoading && watchlists?.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <p className="text-sm">No watchlists yet.</p>
          <p className="text-xs mt-1">Create one to start tracking your bench candidates.</p>
        </div>
      )}

      {watchlists?.map((wl) => (
        <WatchlistCard key={wl.id} watchlistId={wl.id} name={wl.name} />
      ))}
    </div>
  );
}
