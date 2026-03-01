/**
 * Frontend domain types — always camelCase.
 * Mappers in api.ts handle snake_case ↔ camelCase conversion.
 */

export type TxType = "deposit" | "withdrawal" | "buy" | "sell";
export type Side = "buy" | "sell";
export type PriceSource = "quote" | "trade_fallback";

// ── Cash ─────────────────────────────────────────────────────────────────────

export interface CashBalance {
  asOf: string;
  balance: number;
}

export interface CashTx {
  id: number | null;
  date: string;
  type: TxType;
  amount: number;
  symbol: string | null;
  note: string;
  balance: number;
  isVoid: boolean;
}

// ── Trades ────────────────────────────────────────────────────────────────────

export interface Trade {
  id: number;
  date: string;
  symbol: string;
  side: Side;
  qty: number;
  price: number;
  commission: number;
  tax: number;
  note: string;
  isVoid: boolean;
  createdAt: string;
}

// ── Positions ─────────────────────────────────────────────────────────────────

export interface Position {
  symbol: string;
  qty: number;
  avgCost: number | null;
  realizedPnl: number;
  unrealizedPnl: number | null;
  lastPrice: number | null;
  priceSource: PriceSource | null;
  marketValue: number | null;
}

// ── Equity ────────────────────────────────────────────────────────────────────

export interface PositionDetail {
  qty: number;
  price: number | null;
  marketValue: number;
}

export interface EquitySnapshot {
  date: string;
  cash: number;
  marketValue: number;
  totalEquity: number;
  positions: Record<string, PositionDetail>;
}

export interface EquityCurvePoint {
  date: string;
  cash: number;
  marketValue: number;
  totalEquity: number;
  returnPct: number | null;
  cumReturnPct: number | null;
}

// ── Quotes ────────────────────────────────────────────────────────────────────

export interface LastPrice {
  symbol: string;
  price: number | null;
  priceSource: PriceSource | null;
}

// ── Daily Equity ─────────────────────────────────────────────────────────────

export interface DailyPoint {
  date: string;
  cash: number;
  marketValue: number;
  totalEquity: number;
  externalCashflow: number;
  dailyChange: number;
  dailyPnl: number;
  dailyReturnPct: number | null;
  priceStalenessDay: number | null;
  usedQuoteDateMap: Record<string, string | null>;
}

// ── Position Detail ───────────────────────────────────────────────────────────

export interface CostSummary {
  buyCount: number;
  buyQtyTotal: number;
  buyCostTotalIncludingFees: number;
  minBuyPrice: number;
  maxBuyPrice: number;
  firstBuyDate: string;
  lastBuyDate: string;
}

export interface RunningWacEntry {
  tradeId: number;
  date: string;
  side: string;
  qty: number;
  price: number;
  commission: number;
  tax: number;
  qtyAfter: number;
  avgCostAfter: number | null;
}

export interface WacSeriesEntry {
  date: string;
  avgCost: number;
}

export interface PositionDetailItem extends Position {
  pnlPct: number | null;
  costSummary: CostSummary | null;
  runningWac: RunningWacEntry[];
  wacSeries: WacSeriesEntry[];
}

// ── Lots ─────────────────────────────────────────────────────────────────────

export interface LotRecord {
  lotId: number;
  buyTradeId: number;
  buyDate: string;
  qtyRemaining: number;
  buyPrice: number;
  commission: number;
  tax: number;
  costPerShare: number;
  totalCost: number;
  marketPrice: number | null;
  marketValue: number | null;
  unrealizedPnl: number | null;
}

export interface LotAllocation {
  lotId: number;
  qty: number;
  buyPrice: number;
  costPerShare: number;
  realizedPnlPiece: number;
}

export interface RealizedBreakdown {
  sellTradeId: number;
  sellDate: string;
  sellQty: number;
  sellPrice: number;
  commission: number;
  tax: number;
  allocations: LotAllocation[];
}

export interface LotsResponse {
  symbol: string;
  method: string;
  asOf: string;
  positionQty: number;
  avgCostWac: number | null;
  lots: LotRecord[];
  realizedBreakdown: RealizedBreakdown[];
}

// ── Quotes To-Do ──────────────────────────────────────────────────────────────

export interface QuoteTodo {
  symbol: string;
  qty: number;
  lastQuoteDate: string | null;
  stalenessDays: number | null;
  lastPrice: number | null;
  missing: boolean;
  stale: boolean;
}

// ── Performance Summary ───────────────────────────────────────────────────────

export interface PerfSummary {
  startEquity: number | null;
  endEquity: number | null;
  externalCashflowSum: number;
  pnlExCashflow: number | null;
  realizedPnl: number | null;
  unrealizedPnl: number | null;
  feesTotal: number | null;
  feesCommission: number | null;
  feesTax: number | null;
}

// ── Risk Metrics ──────────────────────────────────────────────────────────────

export interface RiskMetrics {
  sharpeRatio: number | null;
  positiveDayRatio: number | null;
  worstDayPct: number | null;
  bestDayPct: number | null;
  tradingDays: number;
  avgDailyReturnPct: number | null;
  volatilityPct: number | null;
}

// ── Rebalance Alerts ──────────────────────────────────────────────────────────

export interface RebalanceAlert {
  type: string;
  severity: "warning" | "info" | "error";
  message: string;
  data: Record<string, unknown>;
}

export interface RebalanceCheck {
  alerts: RebalanceAlert[];
  metrics: {
    cashPct: number;
    top1Pct: number;
    top3Pct: number;
  };
}

// ── Import Result ─────────────────────────────────────────────────────────────

export interface ImportResult {
  ok: boolean;
  inserted: number;
  skipped: number;
  errors: { row: number; message: string; raw: string }[];
  dry_run: boolean;
}
