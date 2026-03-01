"use client";

import { useState } from "react";
import { useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { urls } from "@/lib/api";
import { ApiError } from "@/lib/api";

// ── Download helper ────────────────────────────────────────────────────────────

function downloadUrl(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ── Export section ────────────────────────────────────────────────────────────

function ExportSection() {
  const [includeVoid, setIncludeVoid] = useState(false);

  const exports: { label: string; filename: string; urlFn: () => string }[] = [
    { label: "Trades CSV", filename: "trades.csv", urlFn: () => urls.exportTrades(includeVoid) },
    { label: "Cash CSV", filename: "cash.csv", urlFn: () => urls.exportCash(includeVoid) },
    { label: "Quotes CSV", filename: "quotes.csv", urlFn: () => urls.exportQuotes() },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Export Data</CardTitle>
        <CardDescription>Download your data as CSV files.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={includeVoid}
            onChange={(e) => setIncludeVoid(e.target.checked)}
            className="h-4 w-4 rounded border border-input"
          />
          Include voided entries
        </label>
        <div className="flex flex-wrap gap-3">
          {exports.map(({ label, filename, urlFn }) => (
            <button
              key={filename}
              onClick={() => downloadUrl(urlFn(), filename)}
              className="px-4 py-2 rounded-md border text-sm font-medium hover:bg-muted transition-colors"
            >
              ↓ {label}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Backup / Restore section ──────────────────────────────────────────────────

function BackupSection() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [restoreState, setRestoreState] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [restoreMsg, setRestoreMsg] = useState("");

  const handleRestore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".db")) {
      setRestoreState("error");
      setRestoreMsg("Please select a .db file.");
      return;
    }
    if (!confirm(`Replace the current database with "${file.name}"? This cannot be undone.`)) {
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setRestoreState("loading");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(urls.restoreDb(), {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const data = (await res.json()) as { detail?: string };
        throw new ApiError(res.status, data.detail ?? `HTTP ${res.status}`);
      }
      setRestoreState("ok");
      setRestoreMsg("Database restored successfully. Reload the page to see fresh data.");
    } catch (err) {
      setRestoreState("error");
      setRestoreMsg(err instanceof Error ? err.message : "Restore failed");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Database Backup & Restore</CardTitle>
        <CardDescription>
          Download a copy of the SQLite database, or upload a backup to restore it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap gap-3 items-center">
          <button
            onClick={() => downloadUrl(urls.backupDb(), "ledger.db")}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            ↓ Download Backup (ledger.db)
          </button>

          <label className="px-4 py-2 rounded-md border text-sm font-medium cursor-pointer hover:bg-muted transition-colors">
            {restoreState === "loading" ? "Restoring…" : "↑ Restore from backup"}
            <input
              ref={fileRef}
              type="file"
              accept=".db"
              className="sr-only"
              disabled={restoreState === "loading"}
              onChange={handleRestore}
            />
          </label>
        </div>

        {restoreState === "ok" && (
          <p className="text-sm text-green-700 dark:text-green-400">{restoreMsg}</p>
        )}
        {restoreState === "error" && (
          <p className="text-sm text-destructive">{restoreMsg}</p>
        )}

        <p className="text-xs text-muted-foreground">
          <strong>Caution:</strong> Restoring will immediately replace all data.
          Download a backup first if you are unsure.
        </p>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      <ExportSection />
      <BackupSection />
    </div>
  );
}
