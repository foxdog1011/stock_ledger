/**
 * API layer
 * ──────────
 * • BASE_URL  – NEXT_PUBLIC_API_BASE (empty → use Next.js rewrite proxy)
 * • urls.*    – typed URL builders for every endpoint
 * • post/del  – typed mutation helpers
 * • map*      – snake_case → camelCase mappers (defensive: accepts both)
 */

import type {
  CashTx,
  Trade,
  Position,
  EquitySnapshot,
  EquityCurvePoint,
  LastPrice,
  DailyPoint,
  CostSummary,
  RunningWacEntry,
  PositionDetailItem,
  LotRecord,
  LotAllocation,
  RealizedBreakdown,
  LotsResponse,
  QuoteTodo,
  PerfSummary,
  RiskMetrics,
  RebalanceCheck,
  ImportResult,
} from "./types";

// ── Base URL ───────────────────────────────────────────────────────────────────
// Empty string → relative paths → Next.js rewrite proxy (/api/* → FastAPI)
// Set NEXT_PUBLIC_API_BASE=http://localhost:8000 to bypass proxy (direct calls)
const BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

// ── Error class ───────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Core fetch + timeout ──────────────────────────────────────────────────────

const TIMEOUT_MS = 12_000;

async function coreFetch(url: string, init?: RequestInit): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...init, signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        detail = ((await res.json()) as { detail?: string }).detail ?? detail;
      } catch {
        /* ignore */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json();
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(408, "Request timed out");
    }
    throw err;
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const fetcher = (url: string): Promise<any> => coreFetch(url);

export async function post<T>(path: string, body: unknown): Promise<T> {
  return coreFetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }) as Promise<T>;
}

export async function patch<T>(path: string, body: unknown = {}): Promise<T> {
  return coreFetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }) as Promise<T>;
}

// ── URL builders ──────────────────────────────────────────────────────────────

function qs(params: Record<string, string | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") u.set(k, v);
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

function url(path: string) {
  return `${BASE}${path}`;
}

export const urls = {
  health: () => url("/api/health"),

  cashBalance: (asOf?: string) => url(`/api/cash/balance${qs({ as_of: asOf })}`),

  cashTx: (p?: { start?: string; end?: string; includeVoid?: boolean }) =>
    url(`/api/cash/tx${qs({ start: p?.start, end: p?.end, include_void: p?.includeVoid ? "true" : undefined })}`),

  trades: (p?: { symbol?: string; start?: string; end?: string; includeVoid?: boolean }) =>
    url(
      `/api/trades${qs({
        symbol: p?.symbol,
        start: p?.start,
        end: p?.end,
        include_void: p?.includeVoid ? "true" : undefined,
      })}`,
    ),

  positions: (p?: { asOf?: string; includeClosed?: boolean }) =>
    url(
      `/api/positions${qs({
        as_of: p?.asOf,
        include_closed: p?.includeClosed ? "true" : undefined,
      })}`,
    ),

  equitySnapshot: (asOf?: string) => url(`/api/equity/snapshot${qs({ as_of: asOf })}`),

  equityCurve: (p: { start: string; end: string; freq?: string }) =>
    url(`/api/equity/curve${qs({ start: p.start, end: p.end, freq: p.freq ?? "ME" })}`),

  lastPrice: (symbol: string, asOf?: string) =>
    url(`/api/quotes/last${qs({ symbol, as_of: asOf })}`),

  equityDaily: (p: { start: string; end: string; mode?: string; freq?: string }) =>
    url(`/api/equity/daily${qs({ start: p.start, end: p.end, mode: p.mode ?? "pnl", freq: p.freq ?? "B" })}`),

  positionsDetail: (asOf?: string) =>
    url(`/api/positions/detail${qs({ as_of: asOf })}`),

  lots: (p: { symbol: string; asOf?: string; method?: string }) =>
    url(`/api/lots${qs({ symbol: p.symbol, as_of: p.asOf, method: p.method ?? "fifo" })}`),

  quotesTodo: (p?: { asOf?: string; staleDays?: number }) =>
    url(`/api/quotes/todo${qs({ as_of: p?.asOf, stale_days: p?.staleDays != null ? String(p.staleDays) : undefined })}`),

  perfSummary: (p: { start: string; end: string }) =>
    url(`/api/perf/summary${qs({ start: p.start, end: p.end })}`),

  riskMetrics: (p: { start: string; end: string }) =>
    url(`/api/risk/metrics${qs({ start: p.start, end: p.end })}`),

  rebalanceCheck: (asOf?: string) =>
    url(`/api/rebalance/check${qs({ as_of: asOf })}`),

  exportTrades: (includeVoid?: boolean) =>
    url(`/api/export/trades.csv${qs({ include_void: includeVoid ? "true" : undefined })}`),

  exportCash: (includeVoid?: boolean) =>
    url(`/api/export/cash.csv${qs({ include_void: includeVoid ? "true" : undefined })}`),

  exportQuotes: () => url("/api/export/quotes.csv"),

  backupDb: () => url("/api/backup/db"),
  restoreDb: () => url("/api/restore/db"),
} as const;

// ── Multipart upload helper ───────────────────────────────────────────────────

export async function uploadCsv<T>(path: string, file: File, dryRun: boolean): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}?dry_run=${dryRun}`, {
      method: "POST",
      body: form,
      signal: controller.signal,
    });
    clearTimeout(timer);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try { detail = ((await res.json()) as { detail?: string }).detail ?? detail; } catch { /* ignore */ }
      throw new ApiError(res.status, detail);
    }
    return res.json() as Promise<T>;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof DOMException && err.name === "AbortError") throw new ApiError(408, "Request timed out");
    throw err;
  }
}

// ── Mappers (snake_case → camelCase, defensive fallback) ──────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Raw = Record<string, any>;

function pick<T>(raw: Raw, snake: string, camel: string, fallback: T): T {
  return raw[snake] ?? raw[camel] ?? fallback;
}

export function mapCashTx(raw: Raw): CashTx {
  return {
    id: (raw.id as number | null) ?? null,
    date: raw.date as string,
    type: raw.type as CashTx["type"],
    amount: raw.amount as number,
    symbol: (raw.symbol as string | null) ?? null,
    note: (raw.note as string) ?? "",
    balance: raw.balance as number,
    isVoid: Boolean(pick(raw, "is_void", "isVoid", 0)),
  };
}

export function mapTrade(raw: Raw): Trade {
  return {
    id: raw.id as number,
    date: raw.date as string,
    symbol: raw.symbol as string,
    side: raw.side as Trade["side"],
    qty: raw.qty as number,
    price: raw.price as number,
    commission: raw.commission as number,
    tax: (raw.tax as number) ?? 0,
    note: (raw.note as string) ?? "",
    isVoid: Boolean(pick(raw, "is_void", "isVoid", 0)),
    createdAt: pick(raw, "created_at", "createdAt", "") as string,
  };
}

export function mapPosition(raw: Raw): Position {
  return {
    symbol: raw.symbol as string,
    qty: raw.qty as number,
    avgCost: pick(raw, "avg_cost", "avgCost", null) as number | null,
    realizedPnl: pick(raw, "realized_pnl", "realizedPnl", 0) as number,
    unrealizedPnl: pick(raw, "unrealized_pnl", "unrealizedPnl", null) as number | null,
    lastPrice: pick(raw, "last_price", "lastPrice", null) as number | null,
    priceSource: pick(raw, "price_source", "priceSource", null) as Position["priceSource"],
    marketValue: pick(raw, "market_value", "marketValue", null) as number | null,
  };
}

export function mapEquitySnapshot(raw: Raw): EquitySnapshot {
  const rawPos = (raw.positions ?? {}) as Record<string, Raw>;
  const positions: EquitySnapshot["positions"] = {};
  for (const [sym, p] of Object.entries(rawPos)) {
    positions[sym] = {
      qty: p.qty as number,
      price: (p.price as number | null) ?? null,
      marketValue: pick(p, "market_value", "marketValue", 0) as number,
    };
  }
  return {
    date: raw.date as string,
    cash: raw.cash as number,
    marketValue: pick(raw, "market_value", "marketValue", 0) as number,
    totalEquity: pick(raw, "total_equity", "totalEquity", 0) as number,
    positions,
  };
}

export function mapEquityCurvePoint(raw: Raw): EquityCurvePoint {
  const nullIfNaN = (v: unknown) =>
    v === null || (typeof v === "number" && isNaN(v)) ? null : (v as number);
  return {
    date: raw.date as string,
    cash: raw.cash as number,
    marketValue: pick(raw, "market_value", "marketValue", 0) as number,
    totalEquity: pick(raw, "total_equity", "totalEquity", 0) as number,
    returnPct: nullIfNaN(pick(raw, "return_pct", "returnPct", null)),
    cumReturnPct: nullIfNaN(pick(raw, "cum_return_pct", "cumReturnPct", null)),
  };
}

export function mapLastPrice(raw: Raw): LastPrice {
  return {
    symbol: raw.symbol as string,
    price: (raw.price as number | null) ?? null,
    priceSource: pick(raw, "price_source", "priceSource", null) as LastPrice["priceSource"],
  };
}

export function mapDailyPoint(raw: Raw): DailyPoint {
  return {
    date: raw.date as string,
    cash: raw.cash as number,
    marketValue: pick(raw, "market_value", "marketValue", 0) as number,
    totalEquity: pick(raw, "total_equity", "totalEquity", 0) as number,
    externalCashflow: pick(raw, "external_cashflow", "externalCashflow", 0) as number,
    dailyChange: pick(raw, "daily_change", "dailyChange", 0) as number,
    dailyPnl: pick(raw, "daily_pnl", "dailyPnl", 0) as number,
    dailyReturnPct: (pick(raw, "daily_return_pct", "dailyReturnPct", null) as number | null),
    priceStalenessDay: (pick(raw, "price_staleness_days", "priceStalenessDay", null) as number | null),
    usedQuoteDateMap: (pick(raw, "used_quote_date_map", "usedQuoteDateMap", {}) as Record<string, string | null>),
  };
}

function mapCostSummary(raw: Raw): CostSummary {
  return {
    buyCount: pick(raw, "buy_count", "buyCount", 0) as number,
    buyQtyTotal: pick(raw, "buy_qty_total", "buyQtyTotal", 0) as number,
    buyCostTotalIncludingFees: pick(raw, "buy_cost_total_including_fees", "buyCostTotalIncludingFees", 0) as number,
    minBuyPrice: pick(raw, "min_buy_price", "minBuyPrice", 0) as number,
    maxBuyPrice: pick(raw, "max_buy_price", "maxBuyPrice", 0) as number,
    firstBuyDate: pick(raw, "first_buy_date", "firstBuyDate", "") as string,
    lastBuyDate: pick(raw, "last_buy_date", "lastBuyDate", "") as string,
  };
}

function mapRunningWacEntry(raw: Raw): RunningWacEntry {
  return {
    tradeId: pick(raw, "trade_id", "tradeId", 0) as number,
    date: raw.date as string,
    side: raw.side as string,
    qty: raw.qty as number,
    price: raw.price as number,
    commission: raw.commission as number,
    tax: raw.tax as number,
    qtyAfter: pick(raw, "qty_after", "qtyAfter", 0) as number,
    avgCostAfter: (pick(raw, "avg_cost_after", "avgCostAfter", null) as number | null),
  };
}

export function mapPositionDetail(raw: Raw): PositionDetailItem {
  const base = mapPosition(raw);
  const cs = pick(raw, "cost_summary", "costSummary", null) as Raw | null;
  const rwArr = (pick(raw, "running_wac", "runningWac", []) as Raw[]);
  const wsArr = (pick(raw, "wac_series", "wacSeries", []) as Raw[]);
  return {
    ...base,
    pnlPct: (pick(raw, "pnl_pct", "pnlPct", null) as number | null),
    costSummary: cs ? mapCostSummary(cs) : null,
    runningWac: rwArr.map(mapRunningWacEntry),
    wacSeries: wsArr.map((w: Raw) => ({ date: w.date as string, avgCost: pick(w, "avg_cost", "avgCost", 0) as number })),
  };
}

function mapLotRecord(raw: Raw): LotRecord {
  return {
    lotId: pick(raw, "lot_id", "lotId", 0) as number,
    buyTradeId: pick(raw, "buy_trade_id", "buyTradeId", 0) as number,
    buyDate: pick(raw, "buy_date", "buyDate", "") as string,
    qtyRemaining: pick(raw, "qty_remaining", "qtyRemaining", 0) as number,
    buyPrice: pick(raw, "buy_price", "buyPrice", 0) as number,
    commission: raw.commission as number,
    tax: raw.tax as number,
    costPerShare: pick(raw, "cost_per_share", "costPerShare", 0) as number,
    totalCost: pick(raw, "total_cost", "totalCost", 0) as number,
    marketPrice: (pick(raw, "market_price", "marketPrice", null) as number | null),
    marketValue: (pick(raw, "market_value", "marketValue", null) as number | null),
    unrealizedPnl: (pick(raw, "unrealized_pnl", "unrealizedPnl", null) as number | null),
  };
}

function mapLotAllocation(raw: Raw): LotAllocation {
  return {
    lotId: pick(raw, "lot_id", "lotId", 0) as number,
    qty: raw.qty as number,
    buyPrice: pick(raw, "buy_price", "buyPrice", 0) as number,
    costPerShare: pick(raw, "cost_per_share", "costPerShare", 0) as number,
    realizedPnlPiece: pick(raw, "realized_pnl_piece", "realizedPnlPiece", 0) as number,
  };
}

function mapRealizedBreakdown(raw: Raw): RealizedBreakdown {
  return {
    sellTradeId: pick(raw, "sell_trade_id", "sellTradeId", 0) as number,
    sellDate: pick(raw, "sell_date", "sellDate", "") as string,
    sellQty: pick(raw, "sell_qty", "sellQty", 0) as number,
    sellPrice: pick(raw, "sell_price", "sellPrice", 0) as number,
    commission: raw.commission as number,
    tax: raw.tax as number,
    allocations: ((raw.allocations ?? []) as Raw[]).map(mapLotAllocation),
  };
}

export function mapQuoteTodo(raw: Raw): QuoteTodo {
  return {
    symbol: raw.symbol as string,
    qty: raw.qty as number,
    lastQuoteDate: (pick(raw, "last_quote_date", "lastQuoteDate", null) as string | null),
    stalenessDays: (pick(raw, "staleness_days", "stalenessDays", null) as number | null),
    lastPrice: (pick(raw, "last_price", "lastPrice", null) as number | null),
    missing: Boolean(raw.missing),
    stale: Boolean(raw.stale),
  };
}

export function mapPerfSummary(raw: Raw): PerfSummary {
  return {
    startEquity: (pick(raw, "start_equity", "startEquity", null) as number | null),
    endEquity: (pick(raw, "end_equity", "endEquity", null) as number | null),
    externalCashflowSum: (pick(raw, "external_cashflow_sum", "externalCashflowSum", 0) as number),
    pnlExCashflow: (pick(raw, "pnl_ex_cashflow", "pnlExCashflow", null) as number | null),
    realizedPnl: (pick(raw, "realized_pnl", "realizedPnl", null) as number | null),
    unrealizedPnl: (pick(raw, "unrealized_pnl", "unrealizedPnl", null) as number | null),
    feesTotal: (pick(raw, "fees_total", "feesTotal", null) as number | null),
    feesCommission: (pick(raw, "fees_commission", "feesCommission", null) as number | null),
    feesTax: (pick(raw, "fees_tax", "feesTax", null) as number | null),
  };
}

export function mapRiskMetrics(raw: Raw): RiskMetrics {
  return {
    sharpeRatio: (pick(raw, "sharpe_ratio", "sharpeRatio", null) as number | null),
    positiveDayRatio: (pick(raw, "positive_day_ratio", "positiveDayRatio", null) as number | null),
    worstDayPct: (pick(raw, "worst_day_pct", "worstDayPct", null) as number | null),
    bestDayPct: (pick(raw, "best_day_pct", "bestDayPct", null) as number | null),
    tradingDays: (pick(raw, "trading_days", "tradingDays", 0) as number),
    avgDailyReturnPct: (pick(raw, "avg_daily_return_pct", "avgDailyReturnPct", null) as number | null),
    volatilityPct: (pick(raw, "volatility_pct", "volatilityPct", null) as number | null),
  };
}

export function mapRebalanceCheck(raw: Raw): RebalanceCheck {
  const metrics = (raw.metrics ?? {}) as Raw;
  return {
    alerts: ((raw.alerts ?? []) as Raw[]).map((a) => ({
      type: a.type as string,
      severity: a.severity as RebalanceCheck["alerts"][0]["severity"],
      message: a.message as string,
      data: (a.data ?? {}) as Record<string, unknown>,
    })),
    metrics: {
      cashPct: (pick(metrics, "cash_pct", "cashPct", 0) as number),
      top1Pct: (pick(metrics, "top1_pct", "top1Pct", 0) as number),
      top3Pct: (pick(metrics, "top3_pct", "top3Pct", 0) as number),
    },
  };
}

export function mapImportResult(raw: Raw): ImportResult {
  return {
    ok: Boolean(raw.ok),
    inserted: raw.inserted as number,
    skipped: raw.skipped as number,
    errors: ((raw.errors ?? []) as Raw[]).map((e) => ({
      row: e.row as number,
      message: e.message as string,
      raw: e.raw as string,
    })),
    dry_run: Boolean(raw.dry_run),
  };
}

export function mapLotsResponse(raw: Raw): LotsResponse {
  return {
    symbol: raw.symbol as string,
    method: raw.method as string,
    asOf: pick(raw, "as_of", "asOf", "") as string,
    positionQty: pick(raw, "position_qty", "positionQty", 0) as number,
    avgCostWac: (pick(raw, "avg_cost_wac", "avgCostWac", null) as number | null),
    lots: ((raw.lots ?? []) as Raw[]).map(mapLotRecord),
    realizedBreakdown: ((pick(raw, "realized_breakdown", "realizedBreakdown", []) as Raw[]).map(mapRealizedBreakdown)),
  };
}
