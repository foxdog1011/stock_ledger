"use client";

import { useState, useMemo, useRef } from "react";
import { toast } from "sonner";
import {
  useUniverseCompanies,
  useCompanyDetail,
  useAddUniverseCompany,
  useAddThesis,
  useDeactivateThesis,
  useWatchlists,
  useWatchlistItems,
  useWatchlistGaps,
  useCreateWatchlist,
  useAddWatchlistItem,
  useArchiveWatchlistItem,
  useUpdateWatchlistItem,
} from "@/hooks/use-queries";
import type { UniverseCompany, ThesisType, WatchlistItem } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  ChevronDown, ChevronUp, Plus, Trash2, ListPlus,
  Archive, ArchiveRestore, AlertTriangle, CheckCircle2, Loader2, Pencil,
} from "lucide-react";

// ── Universe constants ─────────────────────────────────────────────────────────

const THESIS_LABELS: Record<ThesisType, string> = {
  bull:              "Bull",
  bear:              "Bear",
  operation_focus:   "Operation Focus",
  risk_factor:       "Risk Factor",
};

const THESIS_COLORS: Record<ThesisType, string> = {
  bull:            "bg-green-100 text-green-800 border-green-300",
  bear:            "bg-red-100 text-red-800 border-red-300",
  operation_focus: "bg-blue-100 text-blue-800 border-blue-300",
  risk_factor:     "bg-yellow-100 text-yellow-800 border-yellow-300",
};

// ── Universe: Add Company Dialog ───────────────────────────────────────────────

function AddCompanyDialog({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    symbol: "", name: "", exchange: "", sector: "", industry: "",
    business_model: "", country: "", currency: "", note: "",
  });
  const addCompany = useAddUniverseCompany();

  function set(k: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.symbol.trim() || !form.name.trim()) return;
    const body = Object.fromEntries(
      Object.entries(form).filter(([, v]) => v.trim() !== "")
    );
    try {
      await addCompany.mutateAsync(body as Parameters<typeof addCompany.mutateAsync>[0]);
      toast.success(`${form.symbol.toUpperCase()} added to Universe`);
      setOpen(false);
      setForm({ symbol: "", name: "", exchange: "", sector: "", industry: "",
                business_model: "", country: "", currency: "", note: "" });
      onDone();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add company");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1" />Add Company</Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Company to Universe</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4 mt-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Symbol *</Label>
              <Input value={form.symbol} onChange={set("symbol")} placeholder="AAPL" required />
            </div>
            <div className="space-y-1">
              <Label>Name *</Label>
              <Input value={form.name} onChange={set("name")} placeholder="Apple Inc." required />
            </div>
            <div className="space-y-1">
              <Label>Exchange</Label>
              <Input value={form.exchange} onChange={set("exchange")} placeholder="NASDAQ" />
            </div>
            <div className="space-y-1">
              <Label>Sector</Label>
              <Input value={form.sector} onChange={set("sector")} placeholder="Technology" />
            </div>
            <div className="space-y-1">
              <Label>Industry</Label>
              <Input value={form.industry} onChange={set("industry")} placeholder="Consumer Electronics" />
            </div>
            <div className="space-y-1">
              <Label>Country</Label>
              <Input value={form.country} onChange={set("country")} placeholder="US" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label>Business Model</Label>
              <Input value={form.business_model} onChange={set("business_model")} placeholder="Hardware + services ecosystem" />
            </div>
            <div className="col-span-2 space-y-1">
              <Label>Note</Label>
              <Input value={form.note} onChange={set("note")} placeholder="Initial research note…" />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" disabled={addCompany.isPending}>
              {addCompany.isPending ? "Adding…" : "Add"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Universe: Add Thesis Panel ─────────────────────────────────────────────────

function AddThesisPanel({ symbol }: { symbol: string }) {
  const [type, setType] = useState<ThesisType>("bull");
  const [content, setContent] = useState("");
  const addThesis = useAddThesis();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    try {
      await addThesis.mutateAsync({ symbol, thesis_type: type, content: content.trim() });
      setContent("");
      toast.success("Thesis note added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap gap-2 items-end">
      <div className="space-y-1">
        <Label className="text-xs">Type</Label>
        <Select value={type} onValueChange={(v) => setType(v as ThesisType)}>
          <SelectTrigger className="w-40 h-8 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(THESIS_LABELS) as ThesisType[]).map((t) => (
              <SelectItem key={t} value={t}>{THESIS_LABELS[t]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex-1 space-y-1 min-w-48">
        <Label className="text-xs">Note</Label>
        <Input
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Add thesis note…"
          className="h-8 text-sm"
        />
      </div>
      <Button type="submit" size="sm" className="h-8" disabled={addThesis.isPending || !content.trim()}>
        Add
      </Button>
    </form>
  );
}

// ── Universe: Add to Watchlist Button ──────────────────────────────────────────

function AddToWatchlistButton({ symbol }: { symbol: string }) {
  const { data: watchlists } = useWatchlists();
  const addItem = useAddWatchlistItem();
  const [open, setOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string>("");

  if (!watchlists || watchlists.length === 0) return null;

  async function add() {
    if (!selectedId) return;
    try {
      await addItem.mutateAsync({ watchlistId: Number(selectedId), symbol });
      toast.success(`${symbol} added to watchlist`);
      setOpen(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs">
          <ListPlus className="h-3 w-3 mr-1" />Watchlist
        </Button>
      </DialogTrigger>
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
              {watchlists.map((w) => (
                <SelectItem key={w.id} value={String(w.id)}>{w.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button size="sm" disabled={!selectedId || addItem.isPending} onClick={add}>
              Add
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ── Universe: Company Detail Panel ────────────────────────────────────────────

function CompanyDetailPanel({ symbol }: { symbol: string }) {
  const { data, isLoading } = useCompanyDetail(symbol);
  const deactivate = useDeactivateThesis();

  if (isLoading) return <div className="pt-4"><Skeleton className="h-32" /></div>;
  if (!data) return null;

  const fields = [
    { label: "Exchange",       value: data.exchange },
    { label: "Sector",         value: data.sector },
    { label: "Industry",       value: data.industry },
    { label: "Business Model", value: data.businessModel },
    { label: "Country",        value: data.country },
    { label: "Currency",       value: data.currency },
    { label: "Note",           value: data.note || null },
  ].filter((f) => f.value);

  return (
    <div className="pt-4 border-t mt-3 space-y-4">
      {fields.length > 0 && (
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {fields.map((f) => (
            <span key={f.label}>
              <span className="text-muted-foreground">{f.label}:</span>{" "}
              <span className="font-medium">{f.value}</span>
            </span>
          ))}
        </div>
      )}

      <Separator />

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Thesis</p>
        {data.thesis.length > 0 ? (
          <div className="space-y-1.5">
            {data.thesis.map((t) => (
              <div key={t.id} className="flex items-start gap-2 group">
                <Badge variant="outline" className={`text-xs shrink-0 ${THESIS_COLORS[t.thesisType]}`}>
                  {THESIS_LABELS[t.thesisType]}
                </Badge>
                <span className="text-sm flex-1">{t.content}</span>
                <button
                  onClick={() => deactivate.mutate({ thesisId: t.id, symbol })}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No thesis notes yet.</p>
        )}
        <AddThesisPanel symbol={symbol} />
      </div>

      {data.relationships.length > 0 && (
        <>
          <Separator />
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Relationships</p>
            {data.relationships.map((r) => (
              <div key={r.id} className="flex items-center gap-2 text-sm">
                <Badge variant="outline" className="text-xs capitalize">{r.relationshipType}</Badge>
                <span className="font-medium">{r.relatedSymbol}</span>
                {r.note && <span className="text-muted-foreground">— {r.note}</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Universe: Company Row ──────────────────────────────────────────────────────

function CompanyRow({ co }: { co: UniverseCompany }) {
  const [open, setOpen] = useState(false);

  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <span className="font-bold text-base w-20 shrink-0">{co.symbol}</span>
            <span className="font-medium">{co.name}</span>
            {co.exchange && <Badge variant="outline" className="text-xs">{co.exchange}</Badge>}
            {co.sector && (
              <span className="text-xs text-muted-foreground hidden sm:inline">{co.sector}</span>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <AddToWatchlistButton symbol={co.symbol} />
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setOpen((v) => !v)}>
              {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>
        {open && <CompanyDetailPanel symbol={co.symbol} />}
      </CardContent>
    </Card>
  );
}

// ── Watchlist: Create Dialog ───────────────────────────────────────────────────

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

// ── Watchlist: Edit Item Dialog ────────────────────────────────────────────────

function EditItemDialog({ item, watchlistId }: { item: WatchlistItem; watchlistId: number }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    industry_position: item.industryPosition,
    operation_focus: item.operationFocus,
    thesis_summary: item.thesisSummary,
    primary_catalyst: item.primaryCatalyst,
    status: item.status,
  });
  const mut = useUpdateWatchlistItem();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mut.mutate(
      { watchlistId, itemId: item.id, data: form },
      {
        onSuccess: () => {
          toast.success(`${item.symbol} updated`);
          setOpen(false);
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="text-muted-foreground hover:text-foreground transition-colors" title="Edit">
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit {item.symbol}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3 pt-1">
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">產業定位 Industry Position</label>
            <Input value={form.industry_position} onChange={set("industry_position")} placeholder="e.g. AI晶片龍頭 / 半導體設備" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">營運重心 Operation Focus</label>
            <Input value={form.operation_focus} onChange={set("operation_focus")} placeholder="e.g. 先進封裝 CoWoS 擴產" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">投資論點 Thesis</label>
            <Input value={form.thesis_summary} onChange={set("thesis_summary")} placeholder="e.g. AI 需求驅動，護城河深" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">主要催化劑 Primary Catalyst</label>
            <Input value={form.primary_catalyst} onChange={set("primary_catalyst")} placeholder="e.g. Q3 法說會、新品發布" />
          </div>
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground">狀態 Status</label>
            <select
              value={form.status}
              onChange={set("status")}
              className="w-full border rounded px-2 py-1.5 text-sm bg-background"
            >
              <option value="watching">Watching</option>
              <option value="monitoring">Monitoring</option>
            </select>
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" size="sm" disabled={mut.isPending}>
              {mut.isPending && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />}
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Watchlist: Add Symbol Row ──────────────────────────────────────────────────

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

// ── Watchlist: Watchlist Card ──────────────────────────────────────────────────

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
                <TableHead>產業定位</TableHead>
                <TableHead>營運重心</TableHead>
                <TableHead>Thesis / Catalyst</TableHead>
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
                  <TableCell className="text-sm text-muted-foreground max-w-[140px] truncate">
                    {item.industryPosition || <span className="italic opacity-40">未填</span>}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-[140px] truncate">
                    {item.operationFocus || <span className="italic opacity-40">未填</span>}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-[200px]">
                    {item.thesisSummary && <div className="truncate">{item.thesisSummary}</div>}
                    {item.primaryCatalyst && (
                      <div className="truncate text-xs text-blue-500">{item.primaryCatalyst}</div>
                    )}
                    {!item.thesisSummary && !item.primaryCatalyst && "—"}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <EditItemDialog item={item} watchlistId={watchlistId} />
                      <button
                        onClick={() => archive(item)}
                        disabled={archiveMut.isPending}
                        className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                        title="Archive"
                      >
                        <Archive className="h-4 w-4" />
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

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

        <AddSymbolRow watchlistId={watchlistId} />
      </CardContent>
    </Card>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function UniversePage() {
  const { data: companies, isLoading: compLoading } = useUniverseCompanies();
  const { data: watchlists, isLoading: wlLoading, isError: wlError } = useWatchlists();
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    if (!companies) return [];
    const q = search.toLowerCase();
    if (!q) return companies;
    return companies.filter(
      (c) =>
        c.symbol.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q) ||
        (c.sector ?? "").toLowerCase().includes(q),
    );
  }, [companies, search]);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <Tabs defaultValue="universe">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <TabsList>
            <TabsTrigger value="universe">股票池</TabsTrigger>
            <TabsTrigger value="watchlist">觀察清單</TabsTrigger>
          </TabsList>
        </div>

        {/* ── Universe Tab ── */}
        <TabsContent value="universe" className="space-y-4 mt-4">
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              Eligible companies for Watchlist selection. Maintain 3× coverage of open positions.
            </p>
            <AddCompanyDialog onDone={() => {}} />
          </div>

          <Input
            placeholder="Search symbol, name, sector…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="max-w-sm"
          />

          {companies && (
            <p className="text-xs text-muted-foreground">
              {filtered.length} of {companies.length} companies
            </p>
          )}

          {compLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}
            </div>
          ) : filtered.length > 0 ? (
            <div className="space-y-2">
              {filtered.map((co) => <CompanyRow key={co.symbol} co={co} />)}
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <p className="font-medium">
                  {search ? "No companies match your search." : "Universe is empty."}
                </p>
                {!search && (
                  <p className="text-sm mt-1">Add companies to begin building your eligible pool.</p>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ── Watchlist Tab ── */}
        <TabsContent value="watchlist" className="space-y-4 mt-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Active monitoring lists with 3× coverage tracking.
            </p>
            <CreateWatchlistDialog />
          </div>

          {wlError && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-md px-4 py-3">
              <AlertTriangle className="h-4 w-4 flex-shrink-0" />
              Failed to load watchlists.
            </div>
          )}

          {wlLoading && (
            <div className="space-y-4">
              <Skeleton className="h-40 w-full rounded-lg" />
              <Skeleton className="h-40 w-full rounded-lg" />
            </div>
          )}

          {!wlLoading && watchlists?.length === 0 && (
            <div className="text-center py-16 text-muted-foreground">
              <p className="text-sm">No watchlists yet.</p>
              <p className="text-xs mt-1">Create one to start tracking your bench candidates.</p>
            </div>
          )}

          {watchlists?.map((wl) => (
            <WatchlistCard key={wl.id} watchlistId={wl.id} name={wl.name} />
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}
