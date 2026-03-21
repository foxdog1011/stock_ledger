"use client";

import { useState } from "react";
import { useRef } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { urls } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { useProviderInfo, useBenchmarkBootstrapStatus, useBootstrapBenchmark } from "@/hooks/use-queries";
import { toast } from "sonner";

// ── Download helper ────────────────────────────────────────────────────────────

function downloadUrl(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// ── Provider Status section ───────────────────────────────────────────────────

function ProviderSection() {
  const { data, isLoading } = useProviderInfo();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Price Provider</CardTitle>
        <CardDescription>
          Configured source for automatic quote refreshes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : data ? (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-4 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Configured:</span>
                <Badge variant="outline">{data.configured}</Badge>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Effective:</span>
                <Badge variant={data.effective === "finmind" ? "default" : "secondary"}>
                  {data.effective}
                </Badge>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">FinMind token:</span>
                {data.finmindTokenSet ? (
                  <Badge className="bg-green-600 text-white hover:bg-green-700">set</Badge>
                ) : (
                  <Badge variant="destructive">not set</Badge>
                )}
              </div>
            </div>

            {!data.finmindTokenSet && (
              <div className="rounded-md bg-muted p-3 text-sm space-y-1">
                <p className="font-medium">Using TWSE public API (no token required)</p>
                <p className="text-muted-foreground">
                  To switch to FinMind (more reliable, historical data), set{" "}
                  <code className="bg-background px-1 rounded text-xs">FINMIND_TOKEN</code>{" "}
                  in your environment:
                </p>
                <ol className="list-decimal list-inside text-muted-foreground space-y-0.5 text-xs ml-1">
                  <li>
                    Register at{" "}
                    <a
                      href="https://finmindtrade.com/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline hover:text-foreground"
                    >
                      finmindtrade.com
                    </a>{" "}
                    and copy your API token.
                  </li>
                  <li>
                    Add to your <code className="bg-background px-1 rounded">.env</code> file:
                    <pre className="mt-1 bg-background p-2 rounded text-xs overflow-x-auto">
                      FINMIND_TOKEN=your_token_here
                    </pre>
                  </li>
                  <li>
                    Restart: <code className="bg-background px-1 rounded">docker compose up -d api</code>
                  </li>
                </ol>
              </div>
            )}

            {data.finmindTokenSet && (
              <div className="rounded-md bg-muted p-3 text-sm">
                <p className="font-medium">Using FinMind API</p>
                <p className="text-muted-foreground text-xs mt-0.5">
                  Token is configured. Prices are fetched from FinMind{" "}
                  <code className="bg-background px-1 rounded">TaiwanStockPrice</code> dataset.
                </p>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Unable to load provider info.</p>
        )}
      </CardContent>
    </Card>
  );
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

// ── Benchmark Data section ─────────────────────────────────────────────────────

const BENCH_PRESETS: { label: string; benches: string[]; desc: string }[] = [
  { label: "Taiwan (0050 + TAIEX)",  benches: ["0050", "TAIEX"],        desc: "Taiwan 50 ETF and TAIEX index" },
  { label: "US (SPY + QQQ)",         benches: ["SPY", "QQQ"],           desc: "S&P 500 ETF and NASDAQ-100 ETF" },
  { label: "All defaults",           benches: ["0050", "TAIEX", "SPY", "QQQ"], desc: "All four benchmarks" },
];

function BenchmarkDataSection() {
  const status = useBenchmarkBootstrapStatus();
  const bootstrap = useBootstrapBenchmark();
  const [selectedPreset, setSelectedPreset] = useState(0);

  const handleBootstrap = async () => {
    const preset = BENCH_PRESETS[selectedPreset];
    toast.info(`Bootstrapping ${preset.benches.join(", ")} from 2016…`);
    try {
      const result = await bootstrap.mutateAsync({ benches: preset.benches, start: "2016-01-01" });
      if (result.errors.length === 0) {
        toast.success(
          `Bootstrap complete — ${result.inserted.toLocaleString()} rows inserted, ${result.skipped.toLocaleString()} skipped.`,
        );
      } else {
        toast.warning(
          `Done with errors — ${result.inserted} inserted. Errors: ${result.errors.map((e) => e.bench).join(", ")}`,
        );
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Bootstrap failed");
    }
  };

  const s = status.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Benchmark Data</CardTitle>
        <CardDescription>
          Download historical daily prices for benchmark tickers (0050, TAIEX, SPY, QQQ)
          from Yahoo Finance and store them in the local database. Required for the Portfolio
          Benchmark comparison chart.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Preset selector */}
        <div className="space-y-2">
          <p className="text-sm font-medium">Select benchmarks to bootstrap</p>
          <div className="flex flex-wrap gap-2">
            {BENCH_PRESETS.map((p, i) => (
              <button
                key={p.label}
                onClick={() => setSelectedPreset(i)}
                className={[
                  "px-3 py-1.5 rounded-md border text-sm transition-colors",
                  selectedPreset === i
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-background hover:bg-muted border-border",
                ].join(" ")}
              >
                {p.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            {BENCH_PRESETS[selectedPreset].desc} — data from 2016-01-01 to today.
            Existing rows are skipped (safe to re-run).
          </p>
        </div>

        {/* Bootstrap button */}
        <button
          onClick={handleBootstrap}
          disabled={bootstrap.isPending}
          className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {bootstrap.isPending
            ? "Fetching from Yahoo Finance…"
            : `Bootstrap ${BENCH_PRESETS[selectedPreset].benches.join(" + ")} (2016→Today)`}
        </button>

        {/* Last run status */}
        {status.isLoading ? (
          <Skeleton className="h-10 w-full" />
        ) : s?.lastRunAt ? (
          <div className="rounded-md bg-muted px-3 py-2 text-xs space-y-1">
            <p className="font-medium text-muted-foreground">Last bootstrap run</p>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5">
              <span>Run at: <b>{s.lastRunAt}</b></span>
              <span>Provider: <b>{s.provider ?? "—"}</b></span>
              <span>Range: <b>{s.from} → {s.to}</b></span>
              <span>Inserted: <b>{s.inserted?.toLocaleString()}</b></span>
              <span>Skipped: <b>{s.skipped?.toLocaleString()}</b></span>
              {(s.errorsCount ?? 0) > 0 && (
                <span className="text-destructive">Errors: <b>{s.errorsCount}</b></span>
              )}
            </div>
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">No bootstrap run recorded yet.</p>
        )}

        <div className="rounded-md bg-muted/50 px-3 py-2 text-xs text-muted-foreground space-y-1">
          <p className="font-medium">Ticker mapping (Yahoo Finance)</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-1 font-mono">
            {[["0050", "0050.TW"], ["TAIEX", "^TWII"], ["SPY", "SPY"], ["QQQ", "QQQ"]].map(([k, v]) => (
              <span key={k}>{k} → {v}</span>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>
      <ProviderSection />
      <BenchmarkDataSection />
      <ExportSection />
      <BackupSection />
    </div>
  );
}
