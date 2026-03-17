"use client";

import { useState, useMemo } from "react";
import { toast } from "sonner";
import {
  useUniverseCompanies,
  useCompanyDetail,
  useAddUniverseCompany,
  useAddThesis,
  useDeactivateThesis,
  useWatchlists,
  useAddWatchlistItem,
} from "@/hooks/use-queries";
import type { UniverseCompany, ThesisType } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ChevronDown, ChevronUp, Plus, Trash2, ListPlus } from "lucide-react";

// ── constants ──────────────────────────────────────────────────────────────────

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

// ── Add Company Dialog ─────────────────────────────────────────────────────────

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

// ── Add Thesis Panel ───────────────────────────────────────────────────────────

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

// ── Add to Watchlist Button ────────────────────────────────────────────────────

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

// ── Company Detail Panel ───────────────────────────────────────────────────────

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
      {/* Meta fields */}
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

      {/* Thesis */}
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

      {/* Relationships */}
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

// ── Company Row ────────────────────────────────────────────────────────────────

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

// ── Page ───────────────────────────────────────────────────────────────────────

export default function UniversePage() {
  const { data: companies, isLoading } = useUniverseCompanies();
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
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Universe</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Eligible companies for Watchlist selection. Maintain 3× coverage of open positions.
          </p>
        </div>
        <AddCompanyDialog onDone={() => {}} />
      </div>

      {/* Search */}
      <Input
        placeholder="Search symbol, name, sector…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
      />

      {/* Company count */}
      {companies && (
        <p className="text-xs text-muted-foreground">
          {filtered.length} of {companies.length} companies
        </p>
      )}

      {/* List */}
      {isLoading ? (
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
    </div>
  );
}
