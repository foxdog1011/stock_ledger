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

export interface LastBuy {
  tradeId: number;
  date: string;
  qty: number;
  price: number;
  commission: number;
  tax: number;
}

export interface CostImpact {
  prevQty: number;
  prevAvgCost: number | null;
  buyQty: number;
  buyPrice: number;
  buyFees: number;
  newQty: number;
  newAvgCost: number;
  deltaAvgCost: number;
  deltaAvgCostPct: number | null;
  impactUnrealizedPnl: number | null;
}

export interface PositionDetailItem extends Position {
  pnlPct: number | null;
  costSummary: CostSummary | null;
  runningWac: RunningWacEntry[];
  wacSeries: WacSeriesEntry[];
  lastBuy: LastBuy | null;
  costImpact: CostImpact | null;
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
  unrealizedPct: number | null;
  underwaterPct: number | null;
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

// ── Attribution ───────────────────────────────────────────────────────────────

export interface AttributionItem {
  symbol: string;
  contribution: number;
  contributionPct: number | null;
  unrealizedChange: number;
  realizedChange: number;
  endQty: number;
  endPrice: number | null;
  endMarketValue: number | null;
}

export interface Attribution {
  start: string;
  end: string;
  totalPnl: number;
  items: AttributionItem[];
  topGainers: AttributionItem[];
  topLosers: AttributionItem[];
}

// ── Daily Digest ──────────────────────────────────────────────────────────────

export interface DigestItem {
  symbol: string;
  contribution: number;
  contributionPct: number | null;
  unrealizedChange: number;
  realizedChange: number;
}

export interface DigestAlert {
  type: string;
  severity: "warning" | "info" | "error";
  message: string;
}

export interface DigestRecord {
  id: number;
  date: string;
  createdAt: string;
  totalEquity: number | null;
  dailyPnl: number | null;
  dailyReturnPct: number | null;
  externalCashflow: number | null;
  marketValue: number | null;
  cash: number | null;
  topContributors: DigestItem[] | null;
  topLosers: DigestItem[] | null;
  alerts: DigestAlert[] | null;
  notes: string | null;
}

export interface DigestSummary {
  date: string;
  totalEquity: number | null;
  dailyPnl: number | null;
  dailyReturnPct: number | null;
  notes: string | null;
}

// ── Quote Refresh ─────────────────────────────────────────────────────────────

export interface RefreshPriceItem {
  symbol: string;
  date: string;
  close: number;
}

export interface RefreshErrorItem {
  symbol: string;
  message: string;
}

export interface RefreshResult {
  asOf: string;
  provider: string;
  requested: number;
  inserted: number;
  skipped: number;
  errors: RefreshErrorItem[];
  prices: RefreshPriceItem[];
}

export interface RefreshStatus {
  lastRunAt: string | null;
  provider: string | null;
  asOf: string | null;
  inserted: number | null;
  skipped: number | null;
  errorsCount: number | null;
  message: string | null;
}

export interface ProviderInfo {
  configured: string;
  effective: string;
  finmindTokenSet: boolean;
}

// ── Benchmark ─────────────────────────────────────────────────────────────────

export interface BenchmarkPoint {
  date: string;
  close: number;
  cumReturnPct: number | null;
}

export interface BenchmarkSeries {
  bench: string;
  freq: string;
  start: string;
  end: string;
  records: BenchmarkPoint[];
  missingDays: number | null;
  lastQuoteDate: string | null;
}

export interface BenchmarkComparePoint {
  date: string;
  portfolioCumReturnPct: number | null;
  benchCumReturnPct: number | null;
  excessCumReturnPct: number | null;
}

export interface BenchmarkMetrics {
  excessReturnPct: number | null;
  trackingErrorAnnualized: number | null;
  correlation: number | null;
  informationRatio: number | null;
}

export interface BenchmarkCompare {
  bench: string;
  freq: string;
  start: string;
  end: string;
  records: BenchmarkComparePoint[];
  metrics: BenchmarkMetrics | null;
}

export interface BenchmarkBootstrapError {
  bench: string;
  message: string;
}

export interface BenchmarkBootstrapResult {
  benches: string[];
  start: string;
  end: string;
  provider: string;
  inserted: number;
  skipped: number;
  errors: BenchmarkBootstrapError[];
}

export interface BenchmarkBootstrapStatus {
  lastRunAt: string | null;
  provider: string | null;
  from: string | null;
  to: string | null;
  inserted: number | null;
  skipped: number | null;
  errorsCount: number | null;
}

// ── Catalyst + Scenario ───────────────────────────────────────────────────────

export type CatalystEventType = "company" | "macro" | "sector";
export type CatalystStatus    = "pending" | "passed" | "cancelled";

export interface Catalyst {
  id: number;
  eventType: CatalystEventType;
  symbol: string | null;
  title: string;
  eventDate: string | null;
  status: CatalystStatus;
  notes: string;
  createdAt: string;
  updatedAt: string;
}

export interface CatalystScenario {
  id: number;
  catalystId: number;
  planA: string;
  planB: string;
  planC: string;
  planD: string;
  priceTarget: number | null;
  stopLoss: number | null;
  createdAt: string;
  updatedAt: string;
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

export interface Watchlist {
  id: number;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
}

export type WatchlistItemStatus = "watching" | "monitoring" | "archived";

export interface WatchlistItem {
  id: number;
  watchlistId: number;
  symbol: string;
  status: WatchlistItemStatus;
  thesisSummary: string;
  addedAt: string;
  updatedAt: string;
}

export interface WatchlistGaps {
  watchlistId: number;
  watchlistName: string;
  activePositionCount: number;
  requiredWatchlistCount: number;
  currentActiveItemCount: number;
  coverageSufficient: boolean;
  gap: number;
  positionsNotInWatchlist: string[];
  positionsInWatchlist: string[];
}

// ── Overview / Dashboard ──────────────────────────────────────────────────────

export interface OverviewPortfolio {
  totalEquity: number;
  cash: number;
  marketValue: number;
  totalCost: number;
  unrealizedPnl: number | null;
  unrealizedPct: number | null;
  realizedPnl: number;
  positionCount: number;
  asOf: string;
}

export interface OverviewRiskPosition {
  symbol: string;
  positionState: "risk_free" | "at_risk";
  netAtRisk: number | null;
  pctRecovered: number | null;
}

export interface OverviewRisk {
  atRiskCount: number;
  riskFreeCount: number;
  totalNetAtRisk: number | null;
  positions: OverviewRiskPosition[];
}

export interface OverviewWatchlistItem {
  watchlistId: number;
  watchlistName: string;
  activePositionCount: number;
  requiredWatchlistCount: number;
  currentActiveItemCount: number;
  coverageSufficient: boolean;
  gap: number;
}

export interface OverviewWatchlistCoverage {
  watchlists: OverviewWatchlistItem[];
  anyInsufficient: boolean;
}

export interface OverviewCatalystItem {
  id: number;
  eventType: string;
  symbol: string | null;
  title: string;
  eventDate: string;
  hasScenario: boolean;
}

export interface OverviewUpcomingCatalysts {
  daysWindow: number;
  count: number;
  items: OverviewCatalystItem[];
}

export interface OverviewOffsetting {
  losingCount: number;
  totalUnrealizedLoss: number;
  profitAvailable: number;
  netOffsetCapacity: number;
}

export interface OverviewData {
  portfolio: OverviewPortfolio;
  risk: OverviewRisk;
  watchlistCoverage: OverviewWatchlistCoverage;
  upcomingCatalysts: OverviewUpcomingCatalysts;
  offsetting: OverviewOffsetting;
  generatedAt: string;
  asOf: string;
}

// ── Universe ──────────────────────────────────────────────────────────────────

export type ThesisType = "bull" | "bear" | "operation_focus" | "risk_factor";
export type RelationshipType = "competitor" | "supplier" | "customer" | "partner";

export interface UniverseCompany {
  symbol: string;
  name: string;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  businessModel: string | null;
  country: string | null;
  currency: string | null;
  note: string;
  createdAt: string;
  updatedAt: string;
}

export interface CompanyThesis {
  id: number;
  symbol: string;
  thesisType: ThesisType;
  content: string;
  createdAt: string;
  isActive: boolean;
}

export interface CompanyRelationship {
  id: number;
  symbol: string;
  relatedSymbol: string;
  relationshipType: RelationshipType;
  note: string;
}

export interface CompanyDetail extends UniverseCompany {
  thesis: CompanyThesis[];
  relationships: CompanyRelationship[];
}

// ── Offsetting ────────────────────────────────────────────────────────────────

export interface LosingPositionItem {
  symbol: string;
  qty: number;
  avgCost: number | null;
  lastPrice: number | null;
  unrealizedPnl: number;
  unrealizedPct: number | null;
  lossIfFullExit: number;
}

export interface ProfitInventorySummary {
  grossRealizedPnl: number;
  positiveRealizedPnl: number;
  availableToOffset: number;
}

export interface ProfitInventoryBySymbol {
  symbol: string;
  realizedPnl: number;
  qty: number;
}

export interface ProfitInventory {
  summary: ProfitInventorySummary;
  bySymbol: ProfitInventoryBySymbol[];
}

export type OffsetGuardrailReason =
  | "no_price"
  | "qty_exceeds_position"
  | "not_a_loss"
  | "over_offset"
  | null;

export interface OffsetGuardrail {
  passed: boolean;
  reason: OffsetGuardrailReason;
  warnings: string[];
}

export interface OffsetSimulation {
  symbol: string;
  simQty: number;
  simPrice: number | null;
  simRealizedLoss: number | null;
  matchedAmount: number | null;
  projectedGrossRealizedPnl: number | null;
  commissionNotIncluded: boolean;
}

export interface OffsetSimulateResult {
  asOf: string;
  losingPosition: LosingPositionItem | null;
  profitInventory: ProfitInventory;
  simulation: OffsetSimulation;
  guardrail: OffsetGuardrail;
}

// ── Import Result ─────────────────────────────────────────────────────────────

export interface ImportResult {
  ok: boolean;
  inserted: number;
  skipped: number;
  errors: { row: number; message: string; raw: string }[];
  dry_run: boolean;
}
