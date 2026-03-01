"use client";

import { useRef, useState } from "react";
import { useImportCsv } from "@/hooks/use-queries";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ImportResult } from "@/lib/types";

// ── Tab types ─────────────────────────────────────────────────────────────────

type ImportType = "trades" | "cash" | "quotes";

const TABS: { value: ImportType; label: string; columns: string; example: string }[] = [
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

// ── Import Result view ────────────────────────────────────────────────────────

function ResultView({ result, dryRun }: { result: ImportResult; dryRun: boolean }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-3 items-center">
        <Badge variant={result.ok ? "default" : "destructive"}>
          {result.ok ? "OK" : "Errors"}
        </Badge>
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

// ── Upload panel ──────────────────────────────────────────────────────────────

function UploadPanel({ type }: { type: ImportType }) {
  const tab = TABS.find((t) => t.value === type)!;
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [lastDryRun, setLastDryRun] = useState(false);

  const mutation = useImportCsv(type);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setResult(null);
  };

  const handleDrop = (e: React.DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && f.name.endsWith(".csv")) {
      setFile(f);
      setResult(null);
    }
  };

  const run = async (dryRun: boolean) => {
    if (!file) return;
    setLastDryRun(dryRun);
    const res = await mutation.mutateAsync({ file, dryRun });
    setResult(res);
  };

  return (
    <div className="space-y-4">
      {/* Schema hint */}
      <Card className="bg-muted/40">
        <CardContent className="pt-4 pb-4 space-y-2">
          <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">Required columns</p>
          <code className="text-xs">{tab.columns}</code>
          <details className="mt-2">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
              Example CSV
            </summary>
            <pre className="mt-2 p-3 rounded bg-background border text-xs overflow-auto whitespace-pre">
              {tab.example}
            </pre>
          </details>
        </CardContent>
      </Card>

      {/* Drop zone */}
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
        <input
          ref={fileRef}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          onChange={handleFile}
        />
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

      {/* Actions */}
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
            onClick={() => {
              setFile(null);
              setResult(null);
              if (fileRef.current) fileRef.current.value = "";
            }}
            className="px-3 py-2 rounded-md text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Result */}
      {result && <ResultView result={result} dryRun={lastDryRun} />}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ImportPage() {
  const [active, setActive] = useState<ImportType>("trades");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Import Data</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload CSV files to bulk-import trades, cash entries, or price quotes.
          Use <em>Dry Run</em> to validate without writing to the database.
        </p>
      </div>

      <div className="flex gap-1 border-b">
        {TABS.map((tab) => (
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
            Import {TABS.find((t) => t.value === active)?.label}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <UploadPanel key={active} type={active} />
        </CardContent>
      </Card>
    </div>
  );
}
