"use client";

import { useState } from "react";
import {
  Plus, ChevronDown, ChevronUp, CheckCircle2,
  XCircle, Clock, AlertTriangle, Loader2,
} from "lucide-react";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useCatalysts,
  useCatalystScenario,
  useCreateCatalyst,
  useUpdateCatalyst,
  useUpsertScenario,
} from "@/hooks/use-queries";
import type { Catalyst, CatalystEventType, CatalystStatus } from "@/lib/types";

// ── helpers ───────────────────────────────────────────────────────────────────

const EVENT_TYPE_LABELS: Record<CatalystEventType, string> = {
  company: "Company",
  macro:   "Macro",
  sector:  "Sector",
};

const EVENT_TYPE_COLORS: Record<CatalystEventType, string> = {
  company: "bg-blue-100 text-blue-800",
  macro:   "bg-purple-100 text-purple-800",
  sector:  "bg-orange-100 text-orange-800",
};

const STATUS_COLORS: Record<CatalystStatus, string> = {
  pending:   "bg-yellow-100 text-yellow-800",
  passed:    "bg-emerald-100 text-emerald-800",
  cancelled: "bg-gray-100 text-gray-500",
};

// ── Create Catalyst Dialog ────────────────────────────────────────────────────

function CreateCatalystDialog() {
  const [open, setOpen]           = useState(false);
  const [title, setTitle]         = useState("");
  const [eventType, setEventType] = useState<CatalystEventType>("company");
  const [symbol, setSymbol]       = useState("");
  const [eventDate, setEventDate] = useState("");
  const mut = useCreateCatalyst();

  function reset() {
    setTitle(""); setSymbol(""); setEventDate("");
    setEventType("company");
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    mut.mutate(
      {
        event_type: eventType,
        title: title.trim(),
        symbol: symbol.trim() || undefined,
        event_date: eventDate || undefined,
      },
      {
        onSuccess: () => {
          toast.success("Catalyst created");
          reset();
          setOpen(false);
        },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm"><Plus className="h-4 w-4 mr-1.5" /> New Catalyst</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader><DialogTitle>New Catalyst</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3 pt-2">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Type</label>
            <Select value={eventType} onValueChange={(v) => setEventType(v as CatalystEventType)}>
              <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="company">Company</SelectItem>
                <SelectItem value="macro">Macro</SelectItem>
                <SelectItem value="sector">Sector</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Title *</label>
            <Input
              placeholder="e.g. Q1 Earnings, Fed Rate Decision"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Symbol</label>
              <Input
                placeholder="AAPL"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                className="font-mono"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Date</label>
              <Input
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!title.trim() || mut.isPending}>
              {mut.isPending && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />}
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Scenario Panel ────────────────────────────────────────────────────────────

function ScenarioPanel({ catalystId }: { catalystId: number }) {
  const { data: scenario, isLoading, isError } = useCatalystScenario(catalystId);
  const mut = useUpsertScenario();

  const [editing, setEditing] = useState(false);
  const [planA, setPlanA]     = useState("");
  const [planB, setPlanB]     = useState("");
  const [planC, setPlanC]     = useState("");
  const [planD, setPlanD]     = useState("");
  const [priceTarget, setPriceTarget] = useState("");
  const [stopLoss, setStopLoss]       = useState("");

  function startEdit() {
    setPlanA(scenario?.planA ?? "");
    setPlanB(scenario?.planB ?? "");
    setPlanC(scenario?.planC ?? "");
    setPlanD(scenario?.planD ?? "");
    setPriceTarget(scenario?.priceTarget != null ? String(scenario.priceTarget) : "");
    setStopLoss(scenario?.stopLoss != null ? String(scenario.stopLoss) : "");
    setEditing(true);
  }

  function handleSave() {
    mut.mutate(
      {
        catalystId,
        plan_a: planA, plan_b: planB, plan_c: planC, plan_d: planD,
        price_target: priceTarget ? Number(priceTarget) : null,
        stop_loss:    stopLoss    ? Number(stopLoss)    : null,
      },
      {
        onSuccess: () => { toast.success("Scenario saved"); setEditing(false); },
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  if (isLoading) return <Skeleton className="h-20 w-full" />;

  if (!scenario || isError) {
    return (
      <div className="space-y-2">
        {!editing ? (
          <Button variant="outline" size="sm" onClick={startEdit}>
            <Plus className="h-3.5 w-3.5 mr-1" /> Add Scenario Plan
          </Button>
        ) : (
          <ScenarioForm
            planA={planA} planB={planB} planC={planC} planD={planD}
            priceTarget={priceTarget} stopLoss={stopLoss}
            setPlanA={setPlanA} setPlanB={setPlanB}
            setPlanC={setPlanC} setPlanD={setPlanD}
            setPriceTarget={setPriceTarget} setStopLoss={setStopLoss}
            onSave={handleSave} onCancel={() => setEditing(false)}
            isPending={mut.isPending}
          />
        )}
      </div>
    );
  }

  if (editing) {
    return (
      <ScenarioForm
        planA={planA} planB={planB} planC={planC} planD={planD}
        priceTarget={priceTarget} stopLoss={stopLoss}
        setPlanA={setPlanA} setPlanB={setPlanB}
        setPlanC={setPlanC} setPlanD={setPlanD}
        setPriceTarget={setPriceTarget} setStopLoss={setStopLoss}
        onSave={handleSave} onCancel={() => setEditing(false)}
        isPending={mut.isPending}
      />
    );
  }

  const plans = [
    { label: "Plan A", value: scenario.planA },
    { label: "Plan B", value: scenario.planB },
    { label: "Plan C", value: scenario.planC },
    { label: "Plan D", value: scenario.planD },
  ].filter((p) => p.value);

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {plans.map((p) => (
          <div key={p.label} className="rounded-md bg-muted/50 px-3 py-2">
            <p className="text-xs font-medium text-muted-foreground mb-0.5">{p.label}</p>
            <p className="text-sm">{p.value}</p>
          </div>
        ))}
        {plans.length === 0 && (
          <p className="text-sm text-muted-foreground italic">No plans written yet.</p>
        )}
      </div>
      {(scenario.priceTarget != null || scenario.stopLoss != null) && (
        <div className="flex gap-4 text-sm text-muted-foreground pt-1">
          {scenario.priceTarget != null && (
            <span>Target: <span className="font-medium text-foreground">{scenario.priceTarget}</span></span>
          )}
          {scenario.stopLoss != null && (
            <span>Stop: <span className="font-medium text-red-500">{scenario.stopLoss}</span></span>
          )}
        </div>
      )}
      <Button variant="outline" size="sm" onClick={startEdit}>Edit Scenario</Button>
    </div>
  );
}

interface ScenarioFormProps {
  planA: string; planB: string; planC: string; planD: string;
  priceTarget: string; stopLoss: string;
  setPlanA: (v: string) => void; setPlanB: (v: string) => void;
  setPlanC: (v: string) => void; setPlanD: (v: string) => void;
  setPriceTarget: (v: string) => void; setStopLoss: (v: string) => void;
  onSave: () => void; onCancel: () => void; isPending: boolean;
}

function ScenarioForm({
  planA, planB, planC, planD, priceTarget, stopLoss,
  setPlanA, setPlanB, setPlanC, setPlanD, setPriceTarget, setStopLoss,
  onSave, onCancel, isPending,
}: ScenarioFormProps) {
  return (
    <div className="space-y-3 pt-1">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {[
          { label: "Plan A", value: planA, set: setPlanA, placeholder: "Best case response" },
          { label: "Plan B", value: planB, set: setPlanB, placeholder: "Base case response" },
          { label: "Plan C", value: planC, set: setPlanC, placeholder: "Worse case response" },
          { label: "Plan D", value: planD, set: setPlanD, placeholder: "Exit / abort scenario" },
        ].map((p) => (
          <div key={p.label} className="space-y-1">
            <label className="text-xs text-muted-foreground">{p.label}</label>
            <Input
              value={p.value}
              onChange={(e) => p.set(e.target.value)}
              placeholder={p.placeholder}
              className="text-sm"
            />
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Price Target</label>
          <Input
            type="number"
            value={priceTarget}
            onChange={(e) => setPriceTarget(e.target.value)}
            placeholder="0.00"
            className="w-28 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Stop Loss</label>
          <Input
            type="number"
            value={stopLoss}
            onChange={(e) => setStopLoss(e.target.value)}
            placeholder="0.00"
            className="w-28 text-sm"
          />
        </div>
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={onSave} disabled={isPending}>
          {isPending && <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />} Save
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

// ── Catalyst Row ──────────────────────────────────────────────────────────────

function CatalystRow({ catalyst }: { catalyst: Catalyst }) {
  const [expanded, setExpanded] = useState(false);
  const updateMut = useUpdateCatalyst();

  function markStatus(status: CatalystStatus) {
    updateMut.mutate(
      { id: catalyst.id, status },
      {
        onSuccess: () => toast.success(`Marked as ${status}`),
        onError: (err) => toast.error(err instanceof Error ? err.message : "Failed"),
      },
    );
  }

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-muted/40"
        onClick={() => setExpanded((v) => !v)}
      >
        <TableCell className="font-mono text-sm w-24">
          {catalyst.eventDate ?? <span className="text-muted-foreground">TBD</span>}
        </TableCell>
        <TableCell>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${EVENT_TYPE_COLORS[catalyst.eventType]}`}>
            {EVENT_TYPE_LABELS[catalyst.eventType]}
          </span>
        </TableCell>
        <TableCell className="font-mono font-medium">
          {catalyst.symbol ?? <span className="text-muted-foreground">—</span>}
        </TableCell>
        <TableCell className="max-w-[220px] truncate text-sm">{catalyst.title}</TableCell>
        <TableCell>
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[catalyst.status]}`}>
            {catalyst.status}
          </span>
        </TableCell>
        <TableCell onClick={(e) => e.stopPropagation()}>
          {catalyst.status === "pending" && (
            <div className="flex gap-1">
              <button
                onClick={() => markStatus("passed")}
                disabled={updateMut.isPending}
                className="p-1 text-emerald-600 hover:text-emerald-700 disabled:opacity-40"
                title="Mark passed"
              >
                <CheckCircle2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => markStatus("cancelled")}
                disabled={updateMut.isPending}
                className="p-1 text-gray-400 hover:text-gray-600 disabled:opacity-40"
                title="Mark cancelled"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </div>
          )}
        </TableCell>
        <TableCell className="text-muted-foreground">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </TableCell>
      </TableRow>

      {expanded && (
        <TableRow>
          <TableCell colSpan={7} className="bg-muted/20 px-6 py-4">
            {catalyst.notes && (
              <p className="text-sm text-muted-foreground mb-3">{catalyst.notes}</p>
            )}
            <ScenarioPanel catalystId={catalyst.id} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CatalystPage() {
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const { data: catalysts, isLoading, isError } = useCatalysts({
    status: statusFilter === "all" ? undefined : statusFilter,
  });

  const upcoming = catalysts?.filter(
    (c) => c.status === "pending" && c.eventDate != null,
  ) ?? [];
  const rest = catalysts?.filter(
    (c) => !(c.status === "pending" && c.eventDate != null),
  ) ?? [];

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold">Catalysts</h1>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-8 text-sm w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="passed">Passed</SelectItem>
              <SelectItem value="cancelled">Cancelled</SelectItem>
            </SelectContent>
          </Select>
          <CreateCatalystDialog />
        </div>
      </div>

      {isError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 rounded-md px-4 py-3">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" /> Failed to load catalysts.
        </div>
      )}

      {isLoading && (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-3/4" />
        </div>
      )}

      {/* Upcoming section */}
      {!isLoading && upcoming.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Clock className="h-4 w-4 text-amber-500" /> Upcoming
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <CatalystTable catalysts={upcoming} />
          </CardContent>
        </Card>
      )}

      {/* All catalysts */}
      {!isLoading && catalysts && catalysts.length === 0 && (
        <div className="text-center py-16 text-muted-foreground">
          <p className="text-sm">No catalysts found.</p>
          <p className="text-xs mt-1">Add one to start tracking upcoming events and scenarios.</p>
        </div>
      )}

      {!isLoading && (rest.length > 0 || (upcoming.length === 0 && (catalysts?.length ?? 0) > 0)) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">All Catalysts</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <CatalystTable catalysts={statusFilter === "pending" || statusFilter === "all" ? rest : (catalysts ?? [])} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function CatalystTable({ catalysts }: { catalysts: Catalyst[] }) {
  if (catalysts.length === 0) return null;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-24">Date</TableHead>
          <TableHead className="w-24">Type</TableHead>
          <TableHead className="w-20">Symbol</TableHead>
          <TableHead>Title</TableHead>
          <TableHead className="w-24">Status</TableHead>
          <TableHead className="w-16" />
          <TableHead className="w-8" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {catalysts.map((c) => <CatalystRow key={c.id} catalyst={c} />)}
      </TableBody>
    </Table>
  );
}
