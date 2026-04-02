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
  LastBuy,
  CostImpact,
  LotRecord,
  LotAllocation,
  RealizedBreakdown,
  LotsResponse,
  QuoteTodo,
  PerfSummary,
  RiskMetrics,
  RebalanceCheck,
  ImportResult,
  RefreshResult,
  RefreshStatus,
  ProviderInfo,
  Attribution,
  AttributionItem,
  DigestRecord,
  DigestSummary,
  BenchmarkSeries,
  BenchmarkCompare,
  BenchmarkComparePoint,
  BenchmarkPoint,
  BenchmarkMetrics,
  BenchmarkBootstrapResult,
  BenchmarkBootstrapStatus,
  OverviewData,
  Catalyst,
  CatalystScenario,
  Watchlist,
  WatchlistItem,
  WatchlistGaps,
  LosingPositionItem,
  ProfitInventory,
  OffsetSimulateResult,
  UniverseCompany,
  CompanyThesis,
  CompanyRelationship,
  CompanyDetail,
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

export async function del(path: string): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, { method: "DELETE", signal: controller.signal });
    clearTimeout(timer);
    if (!res.ok && res.status !== 204) {
      let detail = `HTTP ${res.status}`;
      try { detail = ((await res.json()) as { detail?: string }).detail ?? detail; } catch { /* ignore */ }
      throw new ApiError(res.status, detail);
    }
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof DOMException && err.name === "AbortError") throw new ApiError(408, "Request timed out");
    throw err;
  }
}

export async function put<T>(path: string, body: unknown = {}): Promise<T> {
  return coreFetch(`${BASE}${path}`, {
    method: "PUT",
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

  quotesRefresh: () => url("/api/quotes/refresh"),
  quotesRefreshStatus: () => url("/api/quotes/refresh/status"),
  quotesProvider: () => url("/api/quotes/provider"),

  attribution: (p: { start: string; end: string; topN?: number }) =>
    url(`/api/perf/attribution${qs({ start: p.start, end: p.end, top_n: p.topN != null ? String(p.topN) : undefined })}`),

  digestGenerate: (date?: string, overwrite?: boolean) =>
    url(`/api/digest/generate${qs({ date, overwrite: overwrite ? "true" : undefined })}`),
  digest: (date: string) => url(`/api/digest/${date}`),
  digestList: (p?: { start?: string; end?: string; limit?: number }) =>
    url(`/api/digest${qs({ start: p?.start, end: p?.end, limit: p?.limit != null ? String(p.limit) : undefined })}`),
  digestPatchNotes: (date: string) => url(`/api/digest/${date}/notes`),

  benchmarkSeries: (p: { bench: string; start: string; end: string; freq?: string }) =>
    url(`/api/benchmark/series${qs({ bench: p.bench, start: p.start, end: p.end, freq: p.freq ?? "ME" })}`),

  benchmarkCompare: (p: { bench: string; start: string; end: string; freq?: string }) =>
    url(`/api/benchmark/compare${qs({ bench: p.bench, start: p.start, end: p.end, freq: p.freq ?? "ME" })}`),

  benchmarkBootstrap: () => url("/api/benchmark/bootstrap"),
  benchmarkBootstrapStatus: () => url("/api/benchmark/bootstrap/status"),

  overview: (p?: { asOf?: string; catalystDays?: number }) =>
    url(`/api/overview${qs({ as_of: p?.asOf, catalyst_days: p?.catalystDays != null ? String(p.catalystDays) : undefined })}`),

  catalysts: (p?: { symbol?: string; status?: string; eventType?: string }) =>
    url(`/api/catalysts${qs({ symbol: p?.symbol, status: p?.status, event_type: p?.eventType })}`),
  catalystUpcoming: (p?: { asOf?: string; days?: number }) =>
    url(`/api/catalysts/upcoming${qs({ as_of: p?.asOf, days: p?.days != null ? String(p.days) : undefined })}`),
  catalyst: (id: number) => url(`/api/catalysts/${id}`),
  catalystScenario: (id: number) => url(`/api/catalysts/${id}/scenario`),

  watchlistLists: () => url("/api/watchlist/lists"),
  watchlistItems: (watchlistId: number, includeArchived?: boolean) =>
    url(`/api/watchlist/lists/${watchlistId}/items${qs({ include_archived: includeArchived ? "true" : undefined })}`),
  watchlistItem: (watchlistId: number, itemId: number) =>
    url(`/api/watchlist/lists/${watchlistId}/items/${itemId}`),
  watchlistGaps: (watchlistId: number) =>
    url(`/api/watchlist/lists/${watchlistId}/gaps`),

  offsetLosing: (asOf?: string) =>
    url(`/api/execution/offset/losing${qs({ as_of: asOf })}`),

  offsetProfitInventory: (asOf?: string) =>
    url(`/api/execution/offset/profit-inventory${qs({ as_of: asOf })}`),

  offsetSimulate: (p: { symbol: string; qty?: number; price?: number; asOf?: string }) =>
    url(`/api/execution/offset/simulate/${p.symbol}${qs({
      qty:   p.qty   != null ? String(p.qty)   : undefined,
      price: p.price != null ? String(p.price) : undefined,
      as_of: p.asOf,
    })}`),

  universeCompanies: () => url("/api/universe/companies"),
  universeCompany:   (symbol: string) => url(`/api/universe/companies/${symbol}`),
  universeTesis:     (symbol: string) => url(`/api/universe/companies/${symbol}/thesis`),

  // Alerts
  alerts: (includeTrigered?: boolean) =>
    url(`/api/alerts${qs({ include_triggered: includeTrigered ? "true" : undefined })}`),
  alertsCheck: () => url("/api/alerts/check"),
  alert: (id: number) => url(`/api/alerts/${id}`),

  // Chip
  chip: (symbol: string, date?: string) => url(`/api/chip/${symbol}${qs({ date })}`),
  chipRange: (symbol: string, start: string, end: string) =>
    url(`/api/chip/${symbol}/range${qs({ start, end })}`),
  chipPortfolio: (date?: string) => url(`/api/chip/portfolio/summary${qs({ date })}`),

  // Rolling
  rollingLog: (p?: { symbol?: string; start?: string; end?: string; limit?: number }) =>
    url(`/api/rolling${qs({ symbol: p?.symbol, start: p?.start, end: p?.end, limit: p?.limit != null ? String(p.limit) : undefined })}`),
  rollingSummary: (symbol?: string) => url(`/api/rolling/summary${qs({ symbol })}`),
  sectorCheck: (asOf?: string) => url(`/api/rolling/sector-check${qs({ as_of: asOf })}`),

  // Chart / Technical Indicators
  chart: (symbol: string, days?: number, asOf?: string) =>
    url(`/api/chart/${symbol}${qs({ days: days != null ? String(days) : undefined, as_of: asOf })}`),

  // Monthly Revenue
  revenue: (symbol: string, limit?: number) =>
    url(`/api/revenue/${symbol}${qs({ limit: limit != null ? String(limit) : undefined })}`),
  fetchRevenue: (symbol: string) => url(`/api/revenue/${symbol}/fetch`),

  // Allocation
  allocation: (asOf?: string) => url(`/api/allocation${qs({ as_of: asOf })}`),

  // Screener
  screener: (p?: {
    sector?: string; exchange?: string; country?: string;
    inPositions?: boolean; inWatchlist?: boolean;
    minYoyPct?: number; foreignNetPositive?: boolean; limit?: number;
  }) => url(`/api/screener${qs({
    sector: p?.sector,
    exchange: p?.exchange,
    country: p?.country,
    in_positions: p?.inPositions != null ? String(p.inPositions) : undefined,
    in_watchlist: p?.inWatchlist != null ? String(p.inWatchlist) : undefined,
    min_yoy_pct: p?.minYoyPct != null ? String(p.minYoyPct) : undefined,
    foreign_net_positive: p?.foreignNetPositive != null ? String(p.foreignNetPositive) : undefined,
    limit: p?.limit != null ? String(p.limit) : undefined,
  })}`),

  // Anomaly detection
  anomalyBatch: (p?: { days?: number }) =>
    url(`/api/anomaly/batch${qs({ days: p?.days != null ? String(p.days) : undefined })}`),
  anomaly: (symbol: string, p?: {
    days?: number; method?: string; zscoreThreshold?: number; aeThreshold?: number; asOf?: string;
  }) => url(`/api/anomaly/${symbol}${qs({
    days: p?.days != null ? String(p.days) : undefined,
    method: p?.method,
    zscore_threshold: p?.zscoreThreshold != null ? String(p.zscoreThreshold) : undefined,
    ae_threshold: p?.aeThreshold != null ? String(p.aeThreshold) : undefined,
    as_of: p?.asOf,
  })}`),

  // Research (My-TW-Coverage)
  researchCompany:            (ticker: string) => url(`/api/research/${ticker}`),
  researchSupplyChain:         (ticker: string) => url(`/api/research/supply-chain/${ticker}`),
  researchSupplyChainTree:     (ticker: string, depth?: number) =>
    url(`/api/research/supply-chain/${ticker}/tree${qs({ depth: depth != null ? String(depth) : undefined })}`),
  researchThemes:              () => url("/api/research/themes"),
  researchTheme:               (theme: string) => url(`/api/research/theme/${encodeURIComponent(theme)}`),
  researchThemeSupplyChain:    (theme: string) => url(`/api/research/theme/${encodeURIComponent(theme)}/supply-chain`),
  researchSearch:              (q: string, limit?: number) =>
    url(`/api/research/search${qs({ q, limit: limit != null ? String(limit) : undefined })}`),

  // Deep Dive
  deepDive:   (symbol: string) => url(`/api/deep-dive/${encodeURIComponent(symbol)}`),
  deepDiveAI: (symbol: string) => url(`/api/deep-dive/${encodeURIComponent(symbol)}/ai-analysis`),
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

function mapLastBuy(raw: Raw): LastBuy {
  return {
    tradeId:    pick(raw, "trade_id", "tradeId", 0) as number,
    date:       raw.date as string,
    qty:        raw.qty as number,
    price:      raw.price as number,
    commission: raw.commission as number,
    tax:        raw.tax as number,
  };
}

function mapCostImpact(raw: Raw): CostImpact {
  return {
    prevQty:             pick(raw, "prev_qty", "prevQty", 0) as number,
    prevAvgCost:         pick(raw, "prev_avg_cost", "prevAvgCost", null) as number | null,
    buyQty:              pick(raw, "buy_qty", "buyQty", 0) as number,
    buyPrice:            pick(raw, "buy_price", "buyPrice", 0) as number,
    buyFees:             pick(raw, "buy_fees", "buyFees", 0) as number,
    newQty:              pick(raw, "new_qty", "newQty", 0) as number,
    newAvgCost:          pick(raw, "new_avg_cost", "newAvgCost", 0) as number,
    deltaAvgCost:        pick(raw, "delta_avg_cost", "deltaAvgCost", 0) as number,
    deltaAvgCostPct:     pick(raw, "delta_avg_cost_pct", "deltaAvgCostPct", null) as number | null,
    impactUnrealizedPnl: pick(raw, "impact_unrealized_pnl", "impactUnrealizedPnl", null) as number | null,
  };
}

export function mapPositionDetail(raw: Raw): PositionDetailItem {
  const base = mapPosition(raw);
  const cs   = pick(raw, "cost_summary", "costSummary", null) as Raw | null;
  const rwArr = (pick(raw, "running_wac", "runningWac", []) as Raw[]);
  const wsArr = (pick(raw, "wac_series", "wacSeries", []) as Raw[]);
  const lb   = pick(raw, "last_buy", "lastBuy", null) as Raw | null;
  const ci   = pick(raw, "cost_impact", "costImpact", null) as Raw | null;
  return {
    ...base,
    pnlPct:     (pick(raw, "pnl_pct", "pnlPct", null) as number | null),
    costSummary: cs ? mapCostSummary(cs) : null,
    runningWac:  rwArr.map(mapRunningWacEntry),
    wacSeries:   wsArr.map((w: Raw) => ({ date: w.date as string, avgCost: pick(w, "avg_cost", "avgCost", 0) as number })),
    lastBuy:     lb ? mapLastBuy(lb) : null,
    costImpact:  ci ? mapCostImpact(ci) : null,
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
    marketPrice:   (pick(raw, "market_price", "marketPrice", null) as number | null),
    marketValue:   (pick(raw, "market_value", "marketValue", null) as number | null),
    unrealizedPnl: (pick(raw, "unrealized_pnl", "unrealizedPnl", null) as number | null),
    unrealizedPct: (pick(raw, "unrealized_pct", "unrealizedPct", null) as number | null),
    underwaterPct: (pick(raw, "underwater_pct", "underwaterPct", null) as number | null),
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

export function mapRefreshResult(raw: Raw): RefreshResult {
  return {
    asOf: pick(raw, "as_of", "asOf", "") as string,
    provider: raw.provider as string,
    requested: raw.requested as number,
    inserted: raw.inserted as number,
    skipped: raw.skipped as number,
    errors: ((raw.errors ?? []) as Raw[]).map((e) => ({
      symbol: e.symbol as string,
      message: e.message as string,
    })),
    prices: ((raw.prices ?? []) as Raw[]).map((p) => ({
      symbol: p.symbol as string,
      date: p.date as string,
      close: p.close as number,
    })),
  };
}

export function mapRefreshStatus(raw: Raw): RefreshStatus {
  return {
    lastRunAt: pick(raw, "last_run_at", "lastRunAt", null) as string | null,
    provider: raw.provider as string | null,
    asOf: pick(raw, "as_of", "asOf", null) as string | null,
    inserted: raw.inserted as number | null,
    skipped: raw.skipped as number | null,
    errorsCount: pick(raw, "errors_count", "errorsCount", null) as number | null,
    message: raw.message as string | null,
  };
}

export function mapProviderInfo(raw: Raw): ProviderInfo {
  return {
    configured: raw.configured as string,
    effective: raw.effective as string,
    finmindTokenSet: Boolean(pick(raw, "finmind_token_set", "finmindTokenSet", false)),
  };
}

function mapAttributionItem(raw: Raw): AttributionItem {
  return {
    symbol: raw.symbol as string,
    contribution: raw.contribution as number,
    contributionPct: (pick(raw, "contribution_pct", "contributionPct", null) as number | null),
    unrealizedChange: pick(raw, "unrealized_change", "unrealizedChange", 0) as number,
    realizedChange: pick(raw, "realized_change", "realizedChange", 0) as number,
    endQty: pick(raw, "end_qty", "endQty", 0) as number,
    endPrice: (pick(raw, "end_price", "endPrice", null) as number | null),
    endMarketValue: (pick(raw, "end_market_value", "endMarketValue", null) as number | null),
  };
}

export function mapAttribution(raw: Raw): Attribution {
  return {
    start: raw.start as string,
    end: raw.end as string,
    totalPnl: pick(raw, "total_pnl", "totalPnl", 0) as number,
    items: ((raw.items ?? []) as Raw[]).map(mapAttributionItem),
    topGainers: ((pick(raw, "top_gainers", "topGainers", []) as Raw[]).map(mapAttributionItem)),
    topLosers: ((pick(raw, "top_losers", "topLosers", []) as Raw[]).map(mapAttributionItem)),
  };
}

function mapDigestItem(raw: Raw): import("./types").DigestItem {
  return {
    symbol: raw.symbol as string,
    contribution: raw.contribution as number,
    contributionPct: (pick(raw, "contribution_pct", "contributionPct", null) as number | null),
    unrealizedChange: pick(raw, "unrealized_change", "unrealizedChange", 0) as number,
    realizedChange: pick(raw, "realized_change", "realizedChange", 0) as number,
  };
}

export function mapDigestRecord(raw: Raw): DigestRecord {
  return {
    id: raw.id as number,
    date: raw.date as string,
    createdAt: pick(raw, "created_at", "createdAt", "") as string,
    totalEquity: (pick(raw, "total_equity", "totalEquity", null) as number | null),
    dailyPnl: (pick(raw, "daily_pnl", "dailyPnl", null) as number | null),
    dailyReturnPct: (pick(raw, "daily_return_pct", "dailyReturnPct", null) as number | null),
    externalCashflow: (pick(raw, "external_cashflow", "externalCashflow", null) as number | null),
    marketValue: (pick(raw, "market_value", "marketValue", null) as number | null),
    cash: (raw.cash as number | null) ?? null,
    topContributors: ((raw.top_contributors ?? raw.topContributors) as Raw[] | null)?.map(mapDigestItem) ?? null,
    topLosers: ((raw.top_losers ?? raw.topLosers) as Raw[] | null)?.map(mapDigestItem) ?? null,
    alerts: ((raw.alerts ?? []) as Raw[]).map((a) => ({
      type: a.type as string,
      severity: a.severity as import("./types").DigestAlert["severity"],
      message: a.message as string,
    })),
    notes: (raw.notes as string | null) ?? null,
  };
}

export function mapDigestSummary(raw: Raw): DigestSummary {
  return {
    date: raw.date as string,
    totalEquity: (pick(raw, "total_equity", "totalEquity", null) as number | null),
    dailyPnl: (pick(raw, "daily_pnl", "dailyPnl", null) as number | null),
    dailyReturnPct: (pick(raw, "daily_return_pct", "dailyReturnPct", null) as number | null),
    notes: (raw.notes as string | null) ?? null,
  };
}

// ── Benchmark mappers ──────────────────────────────────────────────────────────

function mapBenchmarkPoint(raw: Raw): BenchmarkPoint {
  return {
    date: raw.date as string,
    close: raw.close as number,
    cumReturnPct: pick(raw, "cum_return_pct", "cumReturnPct", null) as number | null,
  };
}

export function mapBenchmarkSeries(raw: Raw): BenchmarkSeries {
  return {
    bench: raw.bench as string,
    freq: raw.freq as string,
    start: raw.start as string,
    end: raw.end as string,
    records: ((raw.records ?? []) as Raw[]).map(mapBenchmarkPoint),
    missingDays: pick(raw, "missing_days", "missingDays", null) as number | null,
    lastQuoteDate: pick(raw, "last_quote_date", "lastQuoteDate", null) as string | null,
  };
}

function mapBenchmarkComparePoint(raw: Raw): BenchmarkComparePoint {
  return {
    date: raw.date as string,
    portfolioCumReturnPct: pick(raw, "portfolio_cum_return_pct", "portfolioCumReturnPct", null) as number | null,
    benchCumReturnPct:     pick(raw, "bench_cum_return_pct",     "benchCumReturnPct",     null) as number | null,
    excessCumReturnPct:    pick(raw, "excess_cum_return_pct",    "excessCumReturnPct",    null) as number | null,
  };
}

function mapBenchmarkMetrics(raw: Raw): BenchmarkMetrics {
  return {
    excessReturnPct:         pick(raw, "excess_return_pct",         "excessReturnPct",         null) as number | null,
    trackingErrorAnnualized: pick(raw, "tracking_error_annualized", "trackingErrorAnnualized", null) as number | null,
    correlation:             pick(raw, "correlation",               "correlation",             null) as number | null,
    informationRatio:        pick(raw, "information_ratio",         "informationRatio",        null) as number | null,
  };
}

export function mapBenchmarkCompare(raw: Raw): BenchmarkCompare {
  return {
    bench:   raw.bench as string,
    freq:    raw.freq as string,
    start:   raw.start as string,
    end:     raw.end as string,
    records: ((raw.records ?? []) as Raw[]).map(mapBenchmarkComparePoint),
    metrics: raw.metrics ? mapBenchmarkMetrics(raw.metrics as Raw) : null,
  };
}

export function mapBenchmarkBootstrapResult(raw: Raw): BenchmarkBootstrapResult {
  return {
    benches:  (raw.benches ?? []) as string[],
    start:    raw.start as string,
    end:      raw.end as string,
    provider: raw.provider as string,
    inserted: raw.inserted as number,
    skipped:  raw.skipped as number,
    errors:   ((raw.errors ?? []) as Raw[]).map((e) => ({
      bench:   e.bench as string,
      message: e.message as string,
    })),
  };
}

export function mapBenchmarkBootstrapStatus(raw: Raw): BenchmarkBootstrapStatus {
  return {
    lastRunAt:   pick(raw, "last_run_at",   "lastRunAt",   null) as string | null,
    provider:    raw.provider as string | null,
    from:        raw.from as string | null,
    to:          raw.to as string | null,
    inserted:    raw.inserted as number | null,
    skipped:     raw.skipped as number | null,
    errorsCount: pick(raw, "errors_count", "errorsCount", null) as number | null,
  };
}

export function mapCatalyst(raw: Raw): Catalyst {
  return {
    id:        raw.id as number,
    eventType: pick(raw, "event_type", "eventType", "company") as Catalyst["eventType"],
    symbol:    (raw.symbol as string | null) ?? null,
    title:     raw.title as string,
    eventDate: pick(raw, "event_date", "eventDate", null) as string | null,
    status:    raw.status as Catalyst["status"],
    notes:     (raw.notes as string) ?? "",
    createdAt: pick(raw, "created_at", "createdAt", "") as string,
    updatedAt: pick(raw, "updated_at", "updatedAt", "") as string,
  };
}

export function mapCatalystScenario(raw: Raw): CatalystScenario {
  return {
    id:          raw.id as number,
    catalystId:  pick(raw, "catalyst_id", "catalystId", 0) as number,
    planA:       pick(raw, "plan_a", "planA", "") as string,
    planB:       pick(raw, "plan_b", "planB", "") as string,
    planC:       pick(raw, "plan_c", "planC", "") as string,
    planD:       pick(raw, "plan_d", "planD", "") as string,
    priceTarget: pick(raw, "price_target", "priceTarget", null) as number | null,
    stopLoss:    pick(raw, "stop_loss",    "stopLoss",    null) as number | null,
    createdAt:   pick(raw, "created_at",   "createdAt",   "") as string,
    updatedAt:   pick(raw, "updated_at",   "updatedAt",   "") as string,
  };
}

export function mapWatchlist(raw: Raw): Watchlist {
  return {
    id:          raw.id as number,
    name:        raw.name as string,
    description: (raw.description as string) ?? "",
    createdAt:   pick(raw, "created_at", "createdAt", "") as string,
    updatedAt:   pick(raw, "updated_at", "updatedAt", "") as string,
  };
}

export function mapWatchlistItem(raw: Raw): WatchlistItem {
  return {
    id:               raw.id as number,
    watchlistId:      pick(raw, "watchlist_id", "watchlistId", 0) as number,
    symbol:           raw.symbol as string,
    status:           raw.status as WatchlistItem["status"],
    industryPosition: pick(raw, "industry_position", "industryPosition", "") as string,
    operationFocus:   pick(raw, "operation_focus", "operationFocus", "") as string,
    thesisSummary:    pick(raw, "thesis_summary", "thesisSummary", "") as string,
    primaryCatalyst:  pick(raw, "primary_catalyst", "primaryCatalyst", "") as string,
    addedAt:          pick(raw, "added_at", "addedAt", "") as string,
    updatedAt:        pick(raw, "updated_at", "updatedAt", "") as string,
  };
}

export function mapWatchlistGaps(raw: Raw): WatchlistGaps {
  return {
    watchlistId:             pick(raw, "watchlist_id",              "watchlistId",             0)     as number,
    watchlistName:           pick(raw, "watchlist_name",            "watchlistName",           "")    as string,
    activePositionCount:     pick(raw, "active_position_count",     "activePositionCount",     0)     as number,
    requiredWatchlistCount:  pick(raw, "required_watchlist_count",  "requiredWatchlistCount",  0)     as number,
    currentActiveItemCount:  pick(raw, "current_active_item_count", "currentActiveItemCount",  0)     as number,
    coverageSufficient:      Boolean(pick(raw, "coverage_sufficient", "coverageSufficient",    false)),
    gap:                     (raw.gap as number) ?? 0,
    positionsNotInWatchlist: (pick(raw, "positions_not_in_watchlist", "positionsNotInWatchlist", []) as string[]),
    positionsInWatchlist:    (pick(raw, "positions_in_watchlist",     "positionsInWatchlist",    []) as string[]),
  };
}

export function mapUniverseCompany(raw: Raw): UniverseCompany {
  return {
    symbol:        raw.symbol as string,
    name:          raw.name as string,
    exchange:      (raw.exchange      as string | null) ?? null,
    sector:        (raw.sector        as string | null) ?? null,
    industry:      (raw.industry      as string | null) ?? null,
    businessModel: (pick(raw, "business_model", "businessModel", null) as string | null),
    country:       (raw.country       as string | null) ?? null,
    currency:      (raw.currency      as string | null) ?? null,
    note:          (raw.note          as string) ?? "",
    createdAt:     pick(raw, "created_at", "createdAt", "") as string,
    updatedAt:     pick(raw, "updated_at", "updatedAt", "") as string,
  };
}

function mapCompanyThesis(raw: Raw): CompanyThesis {
  return {
    id:         raw.id as number,
    symbol:     raw.symbol as string,
    thesisType: pick(raw, "thesis_type", "thesisType", "bull") as CompanyThesis["thesisType"],
    content:    raw.content as string,
    createdAt:  pick(raw, "created_at", "createdAt", "") as string,
    isActive:   Boolean(pick(raw, "is_active", "isActive", 1)),
  };
}

function mapCompanyRelationship(raw: Raw): CompanyRelationship {
  return {
    id:               raw.id as number,
    symbol:           raw.symbol as string,
    relatedSymbol:    pick(raw, "related_symbol",    "relatedSymbol",    "") as string,
    relationshipType: pick(raw, "relationship_type", "relationshipType", "") as CompanyRelationship["relationshipType"],
    note:             (raw.note as string) ?? "",
  };
}

export function mapCompanyDetail(raw: Raw): CompanyDetail {
  return {
    ...mapUniverseCompany(raw),
    thesis:        ((raw.thesis        ?? []) as Raw[]).map(mapCompanyThesis),
    relationships: ((raw.relationships ?? []) as Raw[]).map(mapCompanyRelationship),
  };
}

export function mapLosingPosition(raw: Raw): LosingPositionItem {
  return {
    symbol:         raw.symbol as string,
    qty:            raw.qty as number,
    avgCost:        pick(raw, "avg_cost",    "avgCost",    null) as number | null,
    lastPrice:      pick(raw, "last_price",  "lastPrice",  null) as number | null,
    unrealizedPnl:  pick(raw, "unrealized_pnl", "unrealizedPnl", 0) as number,
    unrealizedPct:  pick(raw, "unrealized_pct", "unrealizedPct", null) as number | null,
    lossIfFullExit: pick(raw, "loss_if_full_exit", "lossIfFullExit", 0) as number,
  };
}

export function mapProfitInventory(raw: Raw): ProfitInventory {
  const s = (pick(raw, "summary", "summary", {}) as Raw);
  return {
    summary: {
      grossRealizedPnl:    pick(s, "gross_realized_pnl",    "grossRealizedPnl",    0) as number,
      positiveRealizedPnl: pick(s, "positive_realized_pnl", "positiveRealizedPnl", 0) as number,
      availableToOffset:   pick(s, "available_to_offset",   "availableToOffset",   0) as number,
    },
    bySymbol: ((pick(raw, "by_symbol", "bySymbol", []) as Raw[]).map((r) => ({
      symbol:      r.symbol as string,
      realizedPnl: pick(r, "realized_pnl", "realizedPnl", 0) as number,
      qty:         r.qty as number,
    }))),
  };
}

export function mapOffsetSimulateResult(raw: Raw): OffsetSimulateResult {
  const lp  = pick(raw, "losing_position",  "losingPosition",  null) as Raw | null;
  const pi  = (pick(raw, "profit_inventory", "profitInventory", {}) as Raw);
  const sim = (raw.simulation ?? {}) as Raw;
  const g   = (raw.guardrail  ?? {}) as Raw;
  return {
    asOf:             pick(raw, "as_of", "asOf", "") as string,
    losingPosition:   lp ? mapLosingPosition(lp) : null,
    profitInventory:  mapProfitInventory(pi),
    simulation: {
      symbol:                     sim.symbol as string,
      simQty:                     pick(sim, "sim_qty",    "simQty",    0)    as number,
      simPrice:                   pick(sim, "sim_price",  "simPrice",  null) as number | null,
      simRealizedLoss:            pick(sim, "sim_realized_loss",            "simRealizedLoss",            null) as number | null,
      matchedAmount:              pick(sim, "matched_amount",               "matchedAmount",               null) as number | null,
      projectedGrossRealizedPnl:  pick(sim, "projected_gross_realized_pnl", "projectedGrossRealizedPnl",  null) as number | null,
      commissionNotIncluded:      Boolean(pick(sim, "commission_not_included", "commissionNotIncluded", true)),
    },
    guardrail: {
      passed:   Boolean(g.passed),
      reason:   (g.reason ?? null) as OffsetSimulateResult["guardrail"]["reason"],
      warnings: (g.warnings ?? []) as string[],
    },
  };
}

export function mapOverview(raw: Raw): OverviewData {
  const p  = (raw.portfolio    ?? {}) as Raw;
  const r  = (raw.risk         ?? {}) as Raw;
  const wc = (raw.watchlist_coverage ?? raw.watchlistCoverage ?? {}) as Raw;
  const uc = (raw.upcoming_catalysts ?? raw.upcomingCatalysts ?? {}) as Raw;
  const of_ = (raw.offsetting  ?? {}) as Raw;

  return {
    portfolio: {
      totalEquity:   pick(p, "total_equity",   "totalEquity",   0) as number,
      cash:          p.cash as number ?? 0,
      marketValue:   pick(p, "market_value",   "marketValue",   0) as number,
      totalCost:     pick(p, "total_cost",     "totalCost",     0) as number,
      unrealizedPnl: pick(p, "unrealized_pnl", "unrealizedPnl", null) as number | null,
      unrealizedPct: pick(p, "unrealized_pct", "unrealizedPct", null) as number | null,
      realizedPnl:   pick(p, "realized_pnl",   "realizedPnl",   0) as number,
      positionCount: pick(p, "position_count", "positionCount", 0) as number,
      asOf:          pick(p, "as_of",          "asOf",          "") as string,
    },
    risk: {
      atRiskCount:    pick(r, "at_risk_count",    "atRiskCount",    0) as number,
      riskFreeCount:  pick(r, "risk_free_count",  "riskFreeCount",  0) as number,
      totalNetAtRisk: pick(r, "total_net_at_risk","totalNetAtRisk", null) as number | null,
      positions: ((r.positions ?? []) as Raw[]).map((pos) => ({
        symbol:        pos.symbol as string,
        positionState: pick(pos, "position_state", "positionState", "at_risk") as "risk_free" | "at_risk",
        netAtRisk:     pick(pos, "net_at_risk",    "netAtRisk",    null) as number | null,
        pctRecovered:  pick(pos, "pct_recovered",  "pctRecovered", null) as number | null,
      })),
    },
    watchlistCoverage: {
      watchlists: ((wc.watchlists ?? []) as Raw[]).map((w) => ({
        watchlistId:             pick(w, "watchlist_id",              "watchlistId",             0)  as number,
        watchlistName:           pick(w, "watchlist_name",            "watchlistName",           "") as string,
        activePositionCount:     pick(w, "active_position_count",     "activePositionCount",     0)  as number,
        requiredWatchlistCount:  pick(w, "required_watchlist_count",  "requiredWatchlistCount",  0)  as number,
        currentActiveItemCount:  pick(w, "current_active_item_count", "currentActiveItemCount",  0)  as number,
        coverageSufficient:      Boolean(pick(w, "coverage_sufficient", "coverageSufficient",    false)),
        gap:                     w.gap as number ?? 0,
      })),
      anyInsufficient: Boolean(pick(wc, "any_insufficient", "anyInsufficient", false)),
    },
    upcomingCatalysts: {
      daysWindow: pick(uc, "days_window", "daysWindow", 30) as number,
      count:      uc.count as number ?? 0,
      items: ((uc.items ?? []) as Raw[]).map((item) => ({
        id:          item.id as number,
        eventType:   pick(item, "event_type",   "eventType",   "") as string,
        symbol:      item.symbol as string | null ?? null,
        title:       item.title as string,
        eventDate:   pick(item, "event_date",   "eventDate",   "") as string,
        hasScenario: Boolean(pick(item, "has_scenario", "hasScenario", false)),
      })),
    },
    offsetting: {
      losingCount:          pick(of_, "losing_count",           "losingCount",          0)    as number,
      totalUnrealizedLoss:  pick(of_, "total_unrealized_loss",  "totalUnrealizedLoss",  0)    as number,
      profitAvailable:      pick(of_, "profit_available",       "profitAvailable",      0)    as number,
      netOffsetCapacity:    pick(of_, "net_offset_capacity",    "netOffsetCapacity",    0)    as number,
    },
    generatedAt: pick(raw, "generated_at", "generatedAt", "") as string,
    asOf:        pick(raw, "as_of",        "asOf",        "") as string,
  };
}

import type {
  PriceAlert, AlertCheckItem, AlertCheckResult,
  ChipGroup, ChipData, ChipRangeResult,
  RollingLog, RollingLogSummary, SectorCheck, SectorCheckSector,
} from "./types";

// ── Alert mappers ─────────────────────────────────────────────────────────────

export function mapPriceAlert(raw: Raw): PriceAlert {
  return {
    id:          raw.id as number,
    symbol:      raw.symbol as string,
    alertType:   pick(raw, "alert_type", "alertType", "stop_loss") as PriceAlert["alertType"],
    price:       raw.price as number,
    note:        (raw.note as string) ?? "",
    createdAt:   pick(raw, "created_at", "createdAt", "") as string,
    triggered:   (raw.triggered as number) ?? 0,
    triggeredAt: (pick(raw, "triggered_at", "triggeredAt", null) as string | null),
  };
}

function mapAlertCheckItem(raw: Raw): AlertCheckItem {
  return {
    ...mapPriceAlert(raw),
    currentPrice: (pick(raw, "current_price", "currentPrice", null) as number | null),
    status:       raw.status as AlertCheckItem["status"],
    gapPct:       (pick(raw, "gap_pct", "gapPct", null) as number | null),
  };
}

export function mapAlertCheckResult(raw: Raw): AlertCheckResult {
  const sumRaw = (raw.summary ?? {}) as Raw;
  return {
    triggered: ((raw.triggered ?? []) as Raw[]).map(mapAlertCheckItem),
    pending:   ((raw.pending   ?? []) as Raw[]).map(mapAlertCheckItem),
    summary: {
      totalActive:    pick(sumRaw, "total_active",    "totalActive",    0) as number,
      triggeredNow:   pick(sumRaw, "triggered_now",   "triggeredNow",   0) as number,
      stillPending:   pick(sumRaw, "still_pending",   "stillPending",   0) as number,
    },
  };
}

// ── Chip mappers ──────────────────────────────────────────────────────────────

function mapChipGroup(raw: Raw): ChipGroup {
  return { buy: raw.buy as number, sell: raw.sell as number, net: raw.net as number };
}

export function mapChipData(raw: Raw): ChipData {
  return {
    symbol:          raw.symbol as string,
    date:            raw.date as string,
    source:          (raw.source as ChipData["source"]) ?? null,
    foreign:         raw.foreign ? mapChipGroup(raw.foreign as Raw) : { buy: 0, sell: 0, net: 0 },
    investmentTrust: raw.investment_trust ? mapChipGroup(raw.investment_trust as Raw) : { buy: 0, sell: 0, net: 0 },
    dealer:          raw.dealer ? mapChipGroup(raw.dealer as Raw) : { buy: 0, sell: 0, net: 0 },
    totalNet:        pick(raw, "total_net", "totalNet", 0) as number,
    error:           raw.error as string | undefined,
  };
}

export function mapChipRangeResult(raw: Raw): ChipRangeResult {
  const s = (raw.summary ?? {}) as Raw;
  return {
    symbol:       raw.symbol as string,
    start:        raw.start as string,
    end:          raw.end as string,
    daysWithData: pick(raw, "days_with_data", "daysWithData", 0) as number,
    summary: {
      foreignNetTotal:          pick(s, "foreign_net_total",           "foreignNetTotal",          0) as number,
      investmentTrustNetTotal:  pick(s, "investment_trust_net_total",  "investmentTrustNetTotal",  0) as number,
      dealerNetTotal:           pick(s, "dealer_net_total",            "dealerNetTotal",           0) as number,
      totalNet:                 pick(s, "total_net",                   "totalNet",                 0) as number,
    },
    daily: ((raw.daily ?? []) as Raw[]).map(mapChipData),
  };
}

// ── Rolling mappers ───────────────────────────────────────────────────────────

export function mapRollingLog(raw: Raw): RollingLog {
  return {
    id:           raw.id as number,
    date:         raw.date as string,
    symbol:       raw.symbol as string,
    action:       raw.action as RollingLog["action"],
    shares:       (raw.shares as number | null) ?? null,
    sellPrice:    (pick(raw, "sell_price", "sellPrice", null) as number | null),
    buyPrice:     (pick(raw, "buy_price",  "buyPrice",  null) as number | null),
    profitAmount: (pick(raw, "profit_amount", "profitAmount", null) as number | null),
    note:         (raw.note as string) ?? "",
    createdAt:    pick(raw, "created_at", "createdAt", "") as string,
  };
}

export function mapRollingLogSummary(raw: Raw): RollingLogSummary {
  return {
    grandTotalProfit: pick(raw, "grand_total_profit", "grandTotalProfit", 0) as number,
    totalRolls:       pick(raw, "total_rolls",        "totalRolls",       0) as number,
    bySymbol: ((pick(raw, "by_symbol", "bySymbol", []) as Raw[]).map((r) => ({
      symbol:       r.symbol as string,
      rollCount:    pick(r, "roll_count",   "rollCount",   0) as number,
      totalProfit:  pick(r, "total_profit", "totalProfit", 0) as number,
      avgProfit:    pick(r, "avg_profit",   "avgProfit",   0) as number,
      lastRollDate: pick(r, "last_roll_date","lastRollDate","") as string,
    }))),
  };
}

export function mapSectorCheck(raw: Raw): SectorCheck {
  return {
    asOf:             pick(raw, "as_of",              "asOf",             "") as string,
    alert:            Boolean(raw.alert),
    alerts:           (raw.alerts ?? []) as string[],
    uniqueSectors:    pick(raw, "unique_sectors",     "uniqueSectors",    0)  as number,
    totalPositions:   pick(raw, "total_positions",    "totalPositions",   0)  as number,
    totalMarketValue: pick(raw, "total_market_value", "totalMarketValue", 0)  as number,
    sectors: ((raw.sectors ?? []) as Raw[]).map((s): SectorCheckSector => ({
      sector:         s.sector as string,
      symbols:        (s.symbols ?? []) as string[],
      marketValue:    pick(s, "market_value",     "marketValue",    0) as number,
      pctOfPortfolio: pick(s, "pct_of_portfolio", "pctOfPortfolio", 0) as number,
    })),
    unknownSymbols: (pick(raw, "unknown_symbols", "unknownSymbols", []) as string[]),
  };
}


// ── Research mappers ──────────────────────────────────────────────────────────

import type {
  ResearchCompany, ResearchThemesResponse, ResearchThemeResponse,
  ResearchSearchResponse, ResearchSupplyChainResponse,
} from "@/lib/types";

export function mapResearchCompany(raw: Raw): ResearchCompany {
  return {
    ticker:               raw.ticker as string,
    name:                 raw.name as string,
    sector:               (raw.sector as string | null) ?? null,
    industry:             (raw.industry as string | null) ?? null,
    marketCapMillionTwd:  (raw.market_cap as number | null) ?? null,
    evMillionTwd:         (raw.ev as number | null) ?? null,
    description:          (raw.description as string | null) ?? null,
    supplyChain: ((raw.supply_chain ?? []) as Raw[]).map((s) => ({
      direction: s.direction as "upstream" | "downstream",
      entity:    s.entity as string,
      roleNote:  (s.role_note as string | null) ?? null,
    })),
    customers: ((raw.customers ?? []) as Raw[]).map((c) => ({
      counterpart: c.counterpart as string,
      isCustomer:  Boolean(c.is_customer),
      note:        (c.note as string | null) ?? null,
    })),
    themes: (raw.themes ?? []) as string[],
  };
}

export function mapResearchThemes(raw: Raw): ResearchThemesResponse {
  return {
    total:  raw.total as number,
    themes: ((raw.themes ?? []) as Raw[]).map((t) => ({
      themeName:    t.theme_name as string,
      companyCount: t.company_count as number,
    })),
  };
}

export function mapResearchTheme(raw: Raw): ResearchThemeResponse {
  return {
    themeName: raw.theme_name as string,
    total:     raw.total as number,
    companies: ((raw.companies ?? []) as Raw[]).map((c) => ({
      ticker:          c.ticker as string,
      name:            c.name as string,
      industry:        (c.industry as string | null) ?? null,
      supplyChainTier: (c.supply_chain_tier as string | null ?? null) as import("@/lib/types").SupplyChainTier,
    })),
  };
}

export function mapResearchThemeSupplyChain(raw: Raw): import("@/lib/types").ResearchThemeSupplyChainResponse {
  const mapCompany = (c: Raw) => ({
    ticker:   c.ticker as string,
    name:     c.name as string,
    industry: (c.industry as string | null) ?? null,
    tier:     (c.tier as string | null ?? null) as import("@/lib/types").SupplyChainTier,
  });
  return {
    themeName:  raw.theme_name as string,
    upstream:   ((raw.upstream   ?? []) as Raw[]).map(mapCompany),
    integrated: ((raw.integrated ?? []) as Raw[]).map(mapCompany),
    downstream: ((raw.downstream ?? []) as Raw[]).map(mapCompany),
    unknown:    ((raw.unknown    ?? []) as Raw[]).map(mapCompany),
    links: ((raw.links ?? []) as Raw[]).map((l) => ({
      from:      l.from as string,
      to:        l.to as string,
      direction: l.direction as "upstream" | "downstream",
    })),
  };
}

export function mapResearchSupplyChainTree(raw: Raw): import("@/lib/types").ResearchSupplyChainTree {
  const mapNode = (n: Raw) => ({
    entity:   n.entity as string,
    ticker:   (n.ticker as string | null) ?? null,
    name:     (n.name as string | null) ?? null,
    industry: (n.industry as string | null) ?? null,
    roleNote: (n.role_note as string | null) ?? null,
    via:      (n.via as string | undefined),
  });
  return {
    ticker:       raw.ticker as string,
    name:         raw.name as string,
    industry:     (raw.industry as string | null) ?? null,
    upstreamL1:   ((raw.upstream_l1   ?? []) as Raw[]).map(mapNode),
    upstreamL2:   ((raw.upstream_l2   ?? []) as Raw[]).map(mapNode),
    downstreamL1: ((raw.downstream_l1 ?? []) as Raw[]).map(mapNode),
    downstreamL2: ((raw.downstream_l2 ?? []) as Raw[]).map(mapNode),
  };
}

export function mapResearchSearch(raw: Raw): ResearchSearchResponse {
  return {
    total:   raw.total as number,
    results: ((raw.results ?? []) as Raw[]).map((r) => ({
      ticker:             r.ticker as string,
      name:               r.name as string,
      industry:           (r.industry as string | null) ?? null,
      descriptionSnippet: (r.description_snippet as string) ?? "",
    })),
  };
}

export function mapResearchSupplyChain(raw: Raw): ResearchSupplyChainResponse {
  return {
    ticker:     raw.ticker as string,
    upstream:   ((raw.upstream ?? []) as Raw[]).map((e) => ({
      entity:   e.entity as string,
      roleNote: (e.role_note as string | null) ?? null,
    })),
    downstream: ((raw.downstream ?? []) as Raw[]).map((e) => ({
      entity:   e.entity as string,
      roleNote: (e.role_note as string | null) ?? null,
    })),
    relatedCompanies: ((raw.related_companies ?? []) as Raw[]).map((c) => ({
      ticker:   c.ticker as string,
      name:     c.name as string,
      industry: (c.industry as string | null) ?? null,
    })),
  };
}
