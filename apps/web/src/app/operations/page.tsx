"use client";

import { useRef, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useImportCsv, useProviderInfo, useBenchmarkBootstrapStatus, useBootstrapBenchmark } from "@/hooks/use-queries";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { urls, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import type { ImportResult } from "@/lib/types";

// ── Import panel ──────────────────────────────────────────────────────────────

type ImportType = "trades" | "cash" | "quotes";

const IMPORT_TABS: { value: ImportType; label: string; columns: string; example: string }[] = [
  {
    value: "trades",
    label: "Trades",
    columns: "date, symbol, side, qty, price [, commission, tax, note]",
    example: `date,symbol,side,qty,price,commission,tax,note
2024-01-15,AAPL,buy,100,185.50,5.00,0,Initial position
2024-06-20,AAPL,sell,50,210.00,5.00,1.50,Partial exit`,
  },
  {
    value: "cash",
    label: "Cash",
    columns: "date, amount [, note]",
    example: `date,amount,note
2024-01-02,500000,Initial deposit
2024-07-01,200000,Top-up`,
  },
  {
    value: "quotes",
    label: "Quotes",
    columns: "symbol, date, close",
    example: `symbol,date,close
AAPL,2024-01-31,184.40
AAPL,2024-02-29,181.42
MSFT,2024-01-31,397.58`,
  },
];

function ResultView({ result, dryRun }: { result: ImportResult; dryRun: boolean }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 items-center">
        <Badge variant={result.ok ? "default" : "destructive"}>{result.ok ? "OK" : "Errors"}</Badge>
        {dryRun && <Badge variant="secondary">Dry Run</Badge>}
        <span className="text-sm text-muted-foreground">
          {dryRun ? "Would insert" : "Inserted"}: <strong>{result.inserted}</strong>
          {result.skipped > 0 && <> · Skipped: <strong>{result.skipped}</strong></>}
          {result.errors.length > 0 && (
            <> · <span className="text-destructive">Errors: <strong>{result.errors.length}</strong></span></>
          )}
        </span>
      </div>
      {result.errors.length > 0 && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 divide-y divide-destructive/20 max-h-64 overflow-auto">
          {result.errors.map((e, i) => (
            <div key={i} className="px-4 py-2 text-sm">
              <span className="font-medium text-destructive">Row {e.row}:</span>{" "}
              <span>{e.message}</span>
              <div className="mt-0.5 text-xs text-muted-foreground font-mono truncate">{e.raw}</div>
            </div>
          ))}
        </div>
      )}
      {result.ok && result.inserted > 0 && (
        <p className="text-sm text-green-700 dark:text-green-400">
          {dryRun
            ? `✓ Validation passed. ${result.inserted} row(s) ready to import.`
            : `✓ Successfully imported ${result.inserted} row(s).`}
        </p>
      )}
    </div>
  );
}

function UploadPanel({ type }: { type: ImportType }) {
  const tab = IMPORT_TABS.find((t) => t.value === type)!;
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [lastDryRun, setLastDryRun] = useState(false);
  const mutation = useImportCsv(type);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFile(e.target.files?.[0] ?? null);
    setResult(null);
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith(".csv")) { setFile(f); setResult(null); }
  };

  const run = async (dryRun: boolean) => {
    if (!file) return;
    setLastDryRun(dryRun);
    setResult(await mutation.mutateAsync({ file, dryRun }));
  };

  return (
    <div className="space-y-4">
      <Card className="bg-muted/40">
        <CardContent className="pt-4 pb-4 space-y-2">
          <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Required columns</p>
          <code className="text-xs">{tab.columns}</code>
          <details className="mt-2">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">Example CSV</summary>
            <pre className="mt-2 p-3 rounded bg-background border text-xs overflow-auto whitespace-pre">{tab.example}</pre>
          </details>
        </CardContent>
      </Card>

      <label
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
        className={cn(
          "flex flex-col items-center justify-center gap-2 w-full h-40 rounded-xl border-2 border-dashed cursor-pointer transition-colors",
          file
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/30 hover:border-primary/60 hover:bg-muted/30",
        )}
      >
        <input ref={fileRef} type="file" accept=".csv,text/csv" className="sr-only" onChange={handleFile} />
        {file ? (
          <>
            <span className="text-2xl">📄</span>
            <span className="text-sm font-medium">{file.name}</span>
            <span className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</span>
          </>
        ) : (
          <>
            <span className="text-2xl text-muted-foreground">⬆</span>
            <span className="text-sm text-muted-foreground">Drop CSV here or click to browse</span>
          </>
        )}
      </label>

      <div className="flex gap-3">
        <button
          disabled={!file || mutation.isPending}
          onClick={() => run(true)}
          className="px-4 py-2 rounded-md border text-sm font-medium transition-colors disabled:opacity-50 hover:bg-muted"
        >
          {mutation.isPending && lastDryRun ? "Validating…" : "Dry Run (validate)"}
        </button>
        <button
          disabled={!file || mutation.isPending}
          onClick={() => run(false)}
          className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium transition-colors disabled:opacity-50 hover:bg-primary/90"
        >
          {mutation.isPending && !lastDryRun ? "Importing…" : "Import"}
        </button>
        {file && (
          <button
            onClick={() => { setFile(null); setResult(null); if (fileRef.current) fileRef.current.value = ""; }}
            className="px-3 py-2 rounded-md text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {result && <ResultView result={result} dryRun={lastDryRun} />}
    </div>
  );
}

function ImportPanel() {
  const [active, setActive] = useState<ImportType>("trades");

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground">
          Upload CSV files to bulk-import trades, cash entries, or price quotes.
          Use <em>Dry Run</em> to validate without writing to the database.
        </p>
      </div>

      <div className="flex gap-1 border-b">
        {IMPORT_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActive(tab.value)}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
              active === tab.value
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">
            Import {IMPORT_TABS.find((t) => t.value === active)?.label}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <UploadPanel key={active} type={active} />
        </CardContent>
      </Card>
    </div>
  );
}

// ── Settings panel ────────────────────────────────────────────────────────────

function downloadUrl(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function ProviderSection() {
  const { data, isLoading } = useProviderInfo();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Price Provider</CardTitle>
        <CardDescription>Configured source for automatic quote refreshes.</CardDescription>
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
                <Badge variant={data.effective === "finmind" ? "default" : "secondary"}>{data.effective}</Badge>
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
                  To switch to FinMind, set{" "}
                  <code className="bg-background px-1 rounded text-xs">FINMIND_TOKEN</code> in your environment.
                </p>
              </div>
            )}
            {data.finmindTokenSet && (
              <div className="rounded-md bg-muted p-3 text-sm">
                <p className="font-medium">Using FinMind API</p>
                <p className="text-muted-foreground text-xs mt-0.5">Token is configured.</p>
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
            type="checkbox" checked={includeVoid}
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

function BackupSection() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [restoreState, setRestoreState] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [restoreMsg, setRestoreMsg] = useState("");

  const handleRestore = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.endsWith(".db")) { setRestoreState("error"); setRestoreMsg("Please select a .db file."); return; }
    if (!confirm(`Replace the current database with "${file.name}"? This cannot be undone.`)) {
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setRestoreState("loading");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(urls.restoreDb(), { method: "POST", body: form });
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
        <CardDescription>Download a copy of the SQLite database, or upload a backup to restore it.</CardDescription>
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
            <input ref={fileRef} type="file" accept=".db" className="sr-only" disabled={restoreState === "loading"} onChange={handleRestore} />
          </label>
        </div>
        {restoreState === "ok" && <p className="text-sm text-green-700 dark:text-green-400">{restoreMsg}</p>}
        {restoreState === "error" && <p className="text-sm text-destructive">{restoreMsg}</p>}
        <p className="text-xs text-muted-foreground">
          <strong>Caution:</strong> Restoring will immediately replace all data. Download a backup first if you are unsure.
        </p>
      </CardContent>
    </Card>
  );
}

const BENCH_PRESETS: { label: string; benches: string[]; desc: string }[] = [
  { label: "Taiwan (0050 + TAIEX)", benches: ["0050", "TAIEX"], desc: "Taiwan 50 ETF and TAIEX index" },
  { label: "US (SPY + QQQ)", benches: ["SPY", "QQQ"], desc: "S&P 500 ETF and NASDAQ-100 ETF" },
  { label: "All defaults", benches: ["0050", "TAIEX", "SPY", "QQQ"], desc: "All four benchmarks" },
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
        toast.success(`Bootstrap complete — ${result.inserted.toLocaleString()} rows inserted, ${result.skipped.toLocaleString()} skipped.`);
      } else {
        toast.warning(`Done with errors — ${result.inserted} inserted. Errors: ${result.errors.map((e) => e.bench).join(", ")}`);
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
          Download historical daily prices for benchmark tickers from Yahoo Finance. Required for Portfolio Benchmark comparison.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <p className="text-sm font-medium">Select benchmarks to bootstrap</p>
          <div className="flex flex-wrap gap-2">
            {BENCH_PRESETS.map((p, i) => (
              <button
                key={p.label}
                onClick={() => setSelectedPreset(i)}
                className={[
                  "px-3 py-1.5 rounded-md border text-sm transition-colors",
                  selectedPreset === i ? "bg-primary text-primary-foreground border-primary" : "bg-background hover:bg-muted border-border",
                ].join(" ")}
              >
                {p.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            {BENCH_PRESETS[selectedPreset].desc} — data from 2016-01-01 to today. Existing rows are skipped (safe to re-run).
          </p>
        </div>
        <button
          onClick={handleBootstrap}
          disabled={bootstrap.isPending}
          className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {bootstrap.isPending ? "Fetching from Yahoo Finance…" : `Bootstrap ${BENCH_PRESETS[selectedPreset].benches.join(" + ")} (2016→Today)`}
        </button>
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
              {(s.errorsCount ?? 0) > 0 && <span className="text-destructive">Errors: <b>{s.errorsCount}</b></span>}
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

function SettingsPanel() {
  return (
    <div className="space-y-6">
      <ProviderSection />
      <BenchmarkDataSection />
      <ExportSection />
      <BackupSection />
    </div>
  );
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

type OpsTab = "import" | "settings";

const TABS: { value: OpsTab; label: string }[] = [
  { value: "import",   label: "匯入資料" },
  { value: "settings", label: "設定" },
];

function OperationsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const active = (searchParams.get("tab") as OpsTab) ?? "import";

  const setTab = (tab: OpsTab) => {
    router.replace(`/operations?tab=${tab}`);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">操作中心</h1>

      <div className="flex gap-1 border-b">
        {TABS.map(({ value, label }) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={cn(
              "px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px",
              active === value
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {active === "import" ? <ImportPanel /> : <SettingsPanel />}
    </div>
  );
}

export default function OperationsPage() {
  return (
    <Suspense>
      <OperationsContent />
    </Suspense>
  );
}
