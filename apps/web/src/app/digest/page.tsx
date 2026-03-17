"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useDigestList, useDigest, useGenerateDigest, usePatchDigestNotes } from "@/hooks/use-queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtMoney, fmtPct, pnlClass } from "@/lib/format";
import { cn } from "@/lib/utils";
import { RefreshCw, FileText, ChevronDown, ChevronRight } from "lucide-react";
import type { DigestSummary, DigestAlert } from "@/lib/types";

// ── Helpers ───────────────────────────────────────────────────────────────────

function today() {
  return new Date().toISOString().slice(0, 10);
}

const SEVERITY_STYLES: Record<DigestAlert["severity"], string> = {
  warning: "border-yellow-300 bg-yellow-50 text-yellow-800 dark:border-yellow-800 dark:bg-yellow-950/30 dark:text-yellow-300",
  info: "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300",
  error: "border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300",
};

// ── Detail Panel ──────────────────────────────────────────────────────────────

function DigestDetail({ date }: { date: string }) {
  const { data, isLoading } = useDigest(date);
  const patch = usePatchDigestNotes();
  const [editingNotes, setEditingNotes] = useState(false);
  const [noteText, setNoteText] = useState("");

  const handleEditNotes = () => {
    setNoteText(data?.notes ?? "");
    setEditingNotes(true);
  };

  const handleSaveNotes = () => {
    patch.mutate(
      { date, notes: noteText },
      {
        onSuccess: () => {
          setEditingNotes(false);
          toast.success("Notes saved");
        },
        onError: () => toast.error("Failed to save notes"),
      },
    );
  };

  if (isLoading) return <Skeleton className="h-48 w-full" />;
  if (!data) return null;

  return (
    <div className="space-y-4 border-t pt-4 mt-2">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total Equity", value: data.totalEquity != null ? `$${fmtMoney(data.totalEquity)}` : "—" },
          { label: "Market Value", value: data.marketValue != null ? `$${fmtMoney(data.marketValue)}` : "—" },
          { label: "Cash", value: data.cash != null ? `$${fmtMoney(data.cash)}` : "—" },
          { label: "Ext. Cashflow", value: data.externalCashflow != null ? `$${fmtMoney(data.externalCashflow)}` : "—" },
        ].map((s) => (
          <div key={s.label} className="rounded-md bg-muted/40 p-3">
            <p className="text-xs text-muted-foreground mb-0.5">{s.label}</p>
            <p className="text-sm font-semibold tabular-nums">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Contributors + Losers */}
      {(data.topContributors?.length || data.topLosers?.length) ? (
        <div className="grid md:grid-cols-2 gap-4">
          {[
            { title: "Top Contributors", items: data.topContributors ?? [] },
            { title: "Top Detractors",   items: data.topLosers ?? [] },
          ].map(({ title, items }) => (
            <div key={title}>
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1.5">{title}</p>
              <ul className="space-y-1">
                {items.map((item) => (
                  <li key={item.symbol} className="flex items-center justify-between text-sm">
                    <span className="font-mono">{item.symbol}</span>
                    <span className={`tabular-nums font-medium ${pnlClass(item.contribution)}`}>
                      {item.contribution >= 0 ? "+" : ""}${fmtMoney(item.contribution)}
                      {item.contributionPct != null && (
                        <span className="ml-1 text-xs opacity-70">({item.contributionPct.toFixed(1)}%)</span>
                      )}
                    </span>
                  </li>
                ))}
                {!items.length && <li className="text-xs text-muted-foreground">—</li>}
              </ul>
            </div>
          ))}
        </div>
      ) : null}

      {/* Alerts */}
      {data.alerts && data.alerts.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Alerts</p>
          {data.alerts.map((alert, i) => (
            <div key={i} className={cn("text-xs p-2 rounded border", SEVERITY_STYLES[alert.severity])}>
              {alert.message}
            </div>
          ))}
        </div>
      )}

      {/* Notes */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Notes</p>
          {!editingNotes && (
            <button onClick={handleEditNotes} className="text-xs text-primary hover:underline">
              {data.notes ? "Edit" : "+ Add note"}
            </button>
          )}
        </div>
        {editingNotes ? (
          <div className="space-y-2">
            <textarea
              className="w-full min-h-[80px] text-sm rounded-md border bg-background p-2 resize-y focus:outline-none focus:ring-1 focus:ring-primary"
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Write your notes here…"
            />
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveNotes} disabled={patch.isPending}>
                {patch.isPending ? "Saving…" : "Save"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditingNotes(false)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground whitespace-pre-wrap">
            {data.notes || <span className="italic opacity-60">No notes yet.</span>}
          </p>
        )}
      </div>

      <p className="text-xs text-muted-foreground">Generated: {data.createdAt}</p>
    </div>
  );
}

// ── Digest Row ────────────────────────────────────────────────────────────────

function DigestRow({ item }: { item: DigestSummary }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-muted/40 transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
        <span className="font-mono text-sm font-medium w-28 shrink-0">{item.date}</span>
        <div className="flex items-center gap-4 flex-1 flex-wrap">
          {item.dailyPnl != null && (
            <span className={`tabular-nums text-sm font-semibold ${pnlClass(item.dailyPnl)}`}>
              {item.dailyPnl >= 0 ? "+" : ""}${fmtMoney(item.dailyPnl)}
            </span>
          )}
          {item.dailyReturnPct != null && (
            <Badge variant={item.dailyReturnPct >= 0 ? "default" : "destructive"} className="text-xs">
              {item.dailyReturnPct >= 0 ? "+" : ""}{fmtPct(item.dailyReturnPct)}
            </Badge>
          )}
          {item.totalEquity != null && (
            <span className="text-xs text-muted-foreground">
              Equity: ${fmtMoney(item.totalEquity)}
            </span>
          )}
          {item.notes && (
            <span className="text-xs text-muted-foreground italic truncate max-w-[200px]">
              "{item.notes}"
            </span>
          )}
        </div>
      </button>
      {expanded && (
        <div className="px-4 pb-4">
          <DigestDetail date={item.date} />
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DigestPage() {
  const list = useDigestList({ limit: 30 });
  const generate = useGenerateDigest();

  const handleGenerate = () => {
    generate.mutate(
      { date: today(), overwrite: true },
      {
        onSuccess: (result) => {
          toast.success(`Digest generated for ${result.date}`);
        },
        onError: (err) => {
          toast.error(err instanceof Error ? err.message : "Failed to generate digest");
        },
      },
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Daily Digest</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Daily portfolio snapshots — click a row to expand</p>
        </div>
        <Button onClick={handleGenerate} disabled={generate.isPending}>
          <RefreshCw className={`h-4 w-4 mr-2 ${generate.isPending ? "animate-spin" : ""}`} />
          {generate.isPending ? "Generating…" : "Generate Today"}
        </Button>
      </div>

      {list.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : list.isError ? (
        <Card>
          <CardContent className="p-6 text-center text-destructive text-sm">Failed to load digests</CardContent>
        </Card>
      ) : !list.data?.length ? (
        <Card>
          <CardContent className="p-8 text-center space-y-3">
            <FileText className="h-10 w-10 mx-auto text-muted-foreground/50" />
            <p className="text-muted-foreground text-sm">No digests yet.</p>
            <Button size="sm" onClick={handleGenerate} disabled={generate.isPending}>
              Generate today&apos;s digest
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {list.data.map((item) => (
            <DigestRow key={item.date} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}
