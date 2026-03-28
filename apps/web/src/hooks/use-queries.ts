"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  urls,
  fetcher,
  post,
  patch,
  put,
  del,
  uploadCsv,
  mapCashTx,
  mapTrade,
  mapPosition,
  mapEquitySnapshot,
  mapEquityCurvePoint,
  mapLastPrice,
  mapDailyPoint,
  mapPositionDetail,
  mapLotsResponse,
  mapQuoteTodo,
  mapPerfSummary,
  mapRiskMetrics,
  mapRebalanceCheck,
  mapImportResult,
  mapRefreshResult,
  mapRefreshStatus,
  mapProviderInfo,
  mapAttribution,
  mapDigestRecord,
  mapDigestSummary,
  mapBenchmarkSeries,
  mapBenchmarkCompare,
  mapBenchmarkBootstrapResult,
  mapBenchmarkBootstrapStatus,
  mapOverview,
  mapCatalyst,
  mapCatalystScenario,
  mapWatchlist,
  mapWatchlistItem,
  mapWatchlistGaps,
  mapLosingPosition,
  mapProfitInventory,
  mapOffsetSimulateResult,
  mapUniverseCompany,
  mapCompanyDetail,
  type Raw,
} from "@/lib/api";
import type {
  CashTx, Trade, Position, EquitySnapshot, EquityCurvePoint, LastPrice,
  DailyPoint, PositionDetailItem, LotsResponse,
  QuoteTodo, PerfSummary, RiskMetrics, RebalanceCheck, ImportResult,
  RefreshResult, RefreshStatus, ProviderInfo,
  Attribution, DigestRecord, DigestSummary,
  BenchmarkSeries, BenchmarkCompare, BenchmarkBootstrapResult, BenchmarkBootstrapStatus,
  OverviewData,
  Catalyst, CatalystScenario,
  Watchlist, WatchlistItem, WatchlistGaps,
  LosingPositionItem, ProfitInventory, OffsetSimulateResult,
  UniverseCompany, CompanyDetail,
} from "@/lib/types";

// ── Cash ──────────────────────────────────────────────────────────────────────

export function useCashBalance(asOf?: string) {
  return useQuery({
    queryKey: ["cashBalance", asOf],
    queryFn: () => fetcher(urls.cashBalance(asOf)).then((d) => d as { balance: number; as_of: string }),
  });
}

export function useCashTx(p?: { start?: string; end?: string; includeVoid?: boolean }) {
  return useQuery({
    queryKey: ["cashTx", p],
    queryFn: () =>
      fetcher(urls.cashTx(p)).then((d) => (d as Raw[]).map(mapCashTx)) as Promise<CashTx[]>,
  });
}

export function useAddCash() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { date: string; amount: number; note?: string }) =>
      post("/api/cash", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cashBalance"] });
      qc.invalidateQueries({ queryKey: ["cashTx"] });
      qc.invalidateQueries({ queryKey: ["equitySnapshot"] });
      qc.invalidateQueries({ queryKey: ["equityCurve"] });
    },
  });
}

export function useVoidCash() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cashId: number) => patch(`/api/cash/${cashId}/void`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cashBalance"] });
      qc.invalidateQueries({ queryKey: ["cashTx"] });
      qc.invalidateQueries({ queryKey: ["equitySnapshot"] });
      qc.invalidateQueries({ queryKey: ["equityCurve"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
    },
  });
}

// ── Trades ────────────────────────────────────────────────────────────────────

export function useTrades(p?: {
  symbol?: string;
  start?: string;
  end?: string;
  includeVoid?: boolean;
}) {
  return useQuery({
    queryKey: ["trades", p],
    queryFn: () =>
      fetcher(urls.trades(p)).then((d) => (d as Raw[]).map(mapTrade)) as Promise<Trade[]>,
  });
}

export function useVoidTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tradeId: number) => patch(`/api/trades/${tradeId}/void`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["trades"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({ queryKey: ["cashBalance"] });
      qc.invalidateQueries({ queryKey: ["cashTx"] });
      qc.invalidateQueries({ queryKey: ["equitySnapshot"] });
      qc.invalidateQueries({ queryKey: ["equityCurve"] });
    },
  });
}

export function useAddTrade() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      date: string;
      symbol: string;
      side: "buy" | "sell";
      qty: number;
      price: number;
      commission?: number;
      tax?: number;
      note?: string;
    }) => post("/api/trades", body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["trades"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({ queryKey: ["cashBalance"] });
      qc.invalidateQueries({ queryKey: ["cashTx"] });
      qc.invalidateQueries({ queryKey: ["equitySnapshot"] });
      qc.invalidateQueries({ queryKey: ["equityCurve"] });
      // Background refresh triggered server-side — re-fetch quotes after a
      // short delay so the UI picks up the new price_source="quote"
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["lastPrice", vars.symbol] });
        qc.invalidateQueries({ queryKey: ["positions"] });
        qc.invalidateQueries({ queryKey: ["quotesTodo"] });
        qc.invalidateQueries({ queryKey: ["refreshStatus"] });
      }, 3000);
    },
  });
}

// ── Positions ─────────────────────────────────────────────────────────────────

export function usePositions(p?: { asOf?: string; includeClosed?: boolean }) {
  return useQuery({
    queryKey: ["positions", p],
    queryFn: () =>
      fetcher(urls.positions(p)).then((d) => (d as Raw[]).map(mapPosition)) as Promise<Position[]>,
  });
}

// ── Equity ────────────────────────────────────────────────────────────────────

export function useEquitySnapshot(asOf?: string) {
  return useQuery({
    queryKey: ["equitySnapshot", asOf],
    queryFn: () =>
      fetcher(urls.equitySnapshot(asOf)).then((d) => mapEquitySnapshot(d as Record<string, unknown>)) as Promise<EquitySnapshot>,
  });
}

export function useEquityCurve(p: { start: string; end: string; freq?: string }) {
  return useQuery({
    queryKey: ["equityCurve", p],
    queryFn: () =>
      fetcher(urls.equityCurve(p)).then((d) =>
        (d as Raw[]).map(mapEquityCurvePoint),
      ) as Promise<EquityCurvePoint[]>,
    enabled: !!p.start && !!p.end,
  });
}

// ── Quotes ────────────────────────────────────────────────────────────────────

export function useLastPrice(symbol: string, asOf?: string) {
  return useQuery({
    queryKey: ["lastPrice", symbol, asOf],
    queryFn: () =>
      fetcher(urls.lastPrice(symbol, asOf)).then((d) =>
        mapLastPrice(d as Record<string, unknown>),
      ) as Promise<LastPrice>,
    enabled: !!symbol,
  });
}

export function useAddQuote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { symbol: string; date: string; close: number }) =>
      post("/api/quotes/manual", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lastPrice"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({ queryKey: ["equitySnapshot"] });
      qc.invalidateQueries({ queryKey: ["equityCurve"] });
    },
  });
}

// ── Daily Equity ──────────────────────────────────────────────────────────────

export function useEquityDaily(p: { start: string; end: string; mode?: string; freq?: string }) {
  return useQuery({
    queryKey: ["equityDaily", p],
    queryFn: () =>
      fetcher(urls.equityDaily(p)).then((d) => (d as Raw[]).map(mapDailyPoint)) as Promise<DailyPoint[]>,
    enabled: !!p.start && !!p.end,
  });
}

// ── Positions Detail ───────────────────────────────────────────────────────────

export function usePositionsDetail(asOf?: string) {
  return useQuery({
    queryKey: ["positionsDetail", asOf],
    queryFn: () =>
      fetcher(urls.positionsDetail(asOf)).then((d) =>
        (d as Raw[]).map(mapPositionDetail),
      ) as Promise<PositionDetailItem[]>,
  });
}

// ── Lots ──────────────────────────────────────────────────────────────────────

export function useLots(p: { symbol: string; asOf?: string; method?: string }) {
  return useQuery({
    queryKey: ["lots", p],
    queryFn: () =>
      fetcher(urls.lots(p)).then((d) => mapLotsResponse(d as Raw)) as Promise<LotsResponse>,
    enabled: !!p.symbol,
  });
}

// ── Quotes To-Do ──────────────────────────────────────────────────────────────

export function useQuotesTodo(p?: { asOf?: string; staleDays?: number }) {
  return useQuery({
    queryKey: ["quotesTodo", p],
    queryFn: () =>
      fetcher(urls.quotesTodo(p)).then((d) => (d as Raw[]).map(mapQuoteTodo)) as Promise<QuoteTodo[]>,
  });
}

// ── Performance Summary ───────────────────────────────────────────────────────

export function usePerfSummary(p: { start: string; end: string }) {
  return useQuery({
    queryKey: ["perfSummary", p],
    queryFn: () =>
      fetcher(urls.perfSummary(p)).then((d) => mapPerfSummary(d as Raw)) as Promise<PerfSummary>,
    enabled: !!p.start && !!p.end,
  });
}

// ── Risk Metrics ──────────────────────────────────────────────────────────────

export function useRiskMetrics(p: { start: string; end: string }) {
  return useQuery({
    queryKey: ["riskMetrics", p],
    queryFn: () =>
      fetcher(urls.riskMetrics(p)).then((d) => mapRiskMetrics(d as Raw)) as Promise<RiskMetrics>,
    enabled: !!p.start && !!p.end,
  });
}

// ── Rebalance Check ───────────────────────────────────────────────────────────

export function useRebalanceCheck(asOf?: string) {
  return useQuery({
    queryKey: ["rebalanceCheck", asOf],
    queryFn: () =>
      fetcher(urls.rebalanceCheck(asOf)).then((d) =>
        mapRebalanceCheck(d as Raw),
      ) as Promise<RebalanceCheck>,
  });
}

// ── CSV Import ────────────────────────────────────────────────────────────────

export function useImportCsv(type: "trades" | "cash" | "quotes") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, dryRun }: { file: File; dryRun: boolean }) =>
      uploadCsv<ImportResult>(`/api/import/${type}.csv`, file, dryRun).then(
        (d) => mapImportResult(d as Raw),
      ),
    onSuccess: (_data, vars) => {
      if (!vars.dryRun) {
        qc.invalidateQueries();
      }
    },
  });
}

// ── Attribution ───────────────────────────────────────────────────────────────

export function useAttribution(p: { start: string; end: string; topN?: number }) {
  return useQuery({
    queryKey: ["attribution", p],
    queryFn: () =>
      fetcher(urls.attribution(p)).then((d) => mapAttribution(d as Raw)) as Promise<Attribution>,
    enabled: !!p.start && !!p.end,
  });
}

// ── Daily Digest ──────────────────────────────────────────────────────────────

export function useDigestList(p?: { start?: string; end?: string; limit?: number }) {
  return useQuery({
    queryKey: ["digestList", p],
    queryFn: () =>
      fetcher(urls.digestList(p)).then((d) =>
        (d as Raw[]).map(mapDigestSummary),
      ) as Promise<DigestSummary[]>,
  });
}

export function useDigest(date: string) {
  return useQuery({
    queryKey: ["digest", date],
    queryFn: () =>
      fetcher(urls.digest(date)).then((d) => mapDigestRecord(d as Raw)) as Promise<DigestRecord>,
    enabled: !!date,
  });
}

export function useGenerateDigest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ date, overwrite }: { date?: string; overwrite?: boolean } = {}) => {
      const params = new URLSearchParams();
      if (date) params.set("date", date);
      if (overwrite) params.set("overwrite", "true");
      const qs = params.toString();
      return post<Raw>(`/api/digest/generate${qs ? `?${qs}` : ""}`, {}).then(
        (d) => mapDigestRecord(d as Raw),
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["digestList"] });
      qc.invalidateQueries({ queryKey: ["digest"] });
    },
  });
}

export function usePatchDigestNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ date, notes }: { date: string; notes: string }) =>
      patch<Raw>(`/api/digest/${date}/notes`, { notes }).then(
        (d) => mapDigestRecord(d as Raw),
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["digest", vars.date] });
      qc.invalidateQueries({ queryKey: ["digestList"] });
    },
  });
}

// ── Quote Refresh ─────────────────────────────────────────────────────────────

export function useRefreshQuotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { symbols?: string[]; as_of?: string; provider?: string } = {}) =>
      post<Raw>("/api/quotes/refresh", body).then((d) => mapRefreshResult(d as Raw)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quotesTodo"] });
      qc.invalidateQueries({ queryKey: ["equityDaily"] });
      qc.invalidateQueries({ queryKey: ["equitySnapshot"] });
      qc.invalidateQueries({ queryKey: ["positions"] });
      qc.invalidateQueries({ queryKey: ["equityCurve"] });
      qc.invalidateQueries({ queryKey: ["lastPrice"] });
      qc.invalidateQueries({ queryKey: ["rebalanceCheck"] });
    },
  });
}

export function useRefreshStatus() {
  return useQuery({
    queryKey: ["refreshStatus"],
    queryFn: () =>
      fetcher(urls.quotesRefreshStatus()).then((d) =>
        mapRefreshStatus(d as Raw),
      ) as Promise<RefreshStatus>,
    refetchInterval: 30_000,
  });
}

export function useProviderInfo() {
  return useQuery({
    queryKey: ["providerInfo"],
    queryFn: () =>
      fetcher(urls.quotesProvider()).then((d) =>
        mapProviderInfo(d as Raw),
      ) as Promise<ProviderInfo>,
  });
}

// ── Benchmark ─────────────────────────────────────────────────────────────────

type BenchParams = { bench: string; start: string; end: string; freq?: string };

export function useBenchmarkSeries(params: BenchParams | null) {
  return useQuery({
    queryKey: ["benchmarkSeries", params],
    queryFn: () =>
      fetcher(urls.benchmarkSeries(params!)).then((d) =>
        mapBenchmarkSeries(d as Raw),
      ) as Promise<BenchmarkSeries>,
    enabled: !!params?.bench,
  });
}

export function useBenchmarkCompare(params: BenchParams | null) {
  return useQuery({
    queryKey: ["benchmarkCompare", params],
    queryFn: () =>
      fetcher(urls.benchmarkCompare(params!)).then((d) =>
        mapBenchmarkCompare(d as Raw),
      ) as Promise<BenchmarkCompare>,
    enabled: !!params?.bench,
  });
}

export function useBenchmarkBootstrapStatus() {
  return useQuery({
    queryKey: ["benchmarkBootstrapStatus"],
    queryFn: () =>
      fetcher(urls.benchmarkBootstrapStatus()).then((d) =>
        mapBenchmarkBootstrapStatus(d as Raw),
      ) as Promise<BenchmarkBootstrapStatus>,
  });
}

export function useBootstrapBenchmark() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { benches?: string[]; start?: string; end?: string } = {}) =>
      post<Raw>("/api/benchmark/bootstrap", body).then(
        (d) => mapBenchmarkBootstrapResult(d as Raw),
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["benchmarkBootstrapStatus"] });
      qc.invalidateQueries({ queryKey: ["benchmarkSeries"] });
      qc.invalidateQueries({ queryKey: ["benchmarkCompare"] });
    },
  });
}

// ── Catalyst ──────────────────────────────────────────────────────────────────

export function useCatalysts(p?: { status?: string; eventType?: string }) {
  return useQuery({
    queryKey: ["catalysts", p?.status, p?.eventType],
    queryFn: () =>
      fetcher(urls.catalysts(p)).then((d) => (d as Raw[]).map(mapCatalyst)) as Promise<Catalyst[]>,
  });
}

export function useCatalystScenario(catalystId: number) {
  return useQuery({
    queryKey: ["catalystScenario", catalystId],
    queryFn: () =>
      fetcher(urls.catalystScenario(catalystId)).then((d) => mapCatalystScenario(d as Raw)) as Promise<CatalystScenario>,
    retry: false,
  });
}

export function useCreateCatalyst() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      event_type: string; title: string;
      symbol?: string; event_date?: string; notes?: string;
    }) => post<Catalyst>("/api/catalysts", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalysts"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useUpdateCatalyst() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; status?: string; notes?: string; event_date?: string }) =>
      patch<Catalyst>(`/api/catalysts/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalysts"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useUpsertScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ catalystId, ...body }: {
      catalystId: number;
      plan_a?: string; plan_b?: string; plan_c?: string; plan_d?: string;
      price_target?: number | null; stop_loss?: number | null;
    }) => put<CatalystScenario>(`/api/catalysts/${catalystId}/scenario`, body),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["catalystScenario", vars.catalystId] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

export function useWatchlists() {
  return useQuery({
    queryKey: ["watchlists"],
    queryFn: () =>
      fetcher(urls.watchlistLists()).then((d) => (d as Raw[]).map(mapWatchlist)) as Promise<Watchlist[]>,
  });
}

export function useWatchlistItems(watchlistId: number, includeArchived = false) {
  return useQuery({
    queryKey: ["watchlistItems", watchlistId, includeArchived],
    queryFn: () =>
      fetcher(urls.watchlistItems(watchlistId, includeArchived))
        .then((d) => (d as Raw[]).map(mapWatchlistItem)) as Promise<WatchlistItem[]>,
  });
}

export function useWatchlistGaps(watchlistId: number) {
  return useQuery({
    queryKey: ["watchlistGaps", watchlistId],
    queryFn: () =>
      fetcher(urls.watchlistGaps(watchlistId)).then((d) => mapWatchlistGaps(d as Raw)) as Promise<WatchlistGaps>,
  });
}

export function useCreateWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string }) =>
      post<Watchlist>("/api/watchlist/lists", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["watchlists"] }); },
  });
}

export function useAddWatchlistItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ watchlistId, symbol }: { watchlistId: number; symbol: string }) =>
      post<WatchlistItem>(`/api/watchlist/lists/${watchlistId}/items`, { symbol }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["watchlistItems", vars.watchlistId] });
      qc.invalidateQueries({ queryKey: ["watchlistGaps", vars.watchlistId] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useArchiveWatchlistItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ watchlistId, itemId }: { watchlistId: number; itemId: number }) =>
      patch<WatchlistItem>(`/api/watchlist/lists/${watchlistId}/items/${itemId}`, { status: "archived" }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["watchlistItems", vars.watchlistId] });
      qc.invalidateQueries({ queryKey: ["watchlistGaps", vars.watchlistId] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useUpdateWatchlistItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      watchlistId,
      itemId,
      data,
    }: {
      watchlistId: number;
      itemId: number;
      data: Partial<{ industry_position: string; operation_focus: string; thesis_summary: string; primary_catalyst: string; status: string }>;
    }) => patch<WatchlistItem>(`/api/watchlist/lists/${watchlistId}/items/${itemId}`, data),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["watchlistItems", vars.watchlistId] });
    },
  });
}

// ── Universe ──────────────────────────────────────────────────────────────────

export function useUniverseCompanies() {
  return useQuery({
    queryKey: ["universeCompanies"],
    queryFn: () =>
      fetcher(urls.universeCompanies())
        .then((d) => (d as Raw[]).map(mapUniverseCompany)) as Promise<UniverseCompany[]>,
  });
}

export function useCompanyDetail(symbol: string) {
  return useQuery({
    queryKey: ["companyDetail", symbol],
    queryFn: () =>
      fetcher(urls.universeCompany(symbol))
        .then((d) => mapCompanyDetail(d as Raw)) as Promise<CompanyDetail>,
    enabled: !!symbol,
  });
}

export function useAddUniverseCompany() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      symbol: string; name: string;
      exchange?: string; sector?: string; industry?: string;
      business_model?: string; country?: string; currency?: string; note?: string;
    }) => post<Raw>("/api/universe/companies", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["universeCompanies"] }); },
  });
}

export function useAddThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ symbol, thesis_type, content }: {
      symbol: string; thesis_type: string; content: string;
    }) => post<Raw>(`/api/universe/companies/${symbol}/thesis`, { thesis_type, content }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["companyDetail", vars.symbol] });
    },
  });
}

export function useDeactivateThesis() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ thesisId, symbol: _symbol }: { thesisId: number; symbol: string }) =>
      del(`/api/universe/thesis/${thesisId}`),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["companyDetail", vars.symbol] });
    },
  });
}

// ── Offsetting ────────────────────────────────────────────────────────────────

export function useLosingPositions(asOf?: string) {
  return useQuery({
    queryKey: ["losingPositions", asOf],
    queryFn: () =>
      fetcher(urls.offsetLosing(asOf))
        .then((d) => (d as Raw[]).map(mapLosingPosition)) as Promise<LosingPositionItem[]>,
  });
}

export function useProfitInventory(asOf?: string) {
  return useQuery({
    queryKey: ["profitInventory", asOf],
    queryFn: () =>
      fetcher(urls.offsetProfitInventory(asOf))
        .then((d) => mapProfitInventory(d as Raw)) as Promise<ProfitInventory>,
  });
}

export function useOffsetSimulate(
  p: { symbol: string; qty?: number; price?: number; asOf?: string } | null,
) {
  return useQuery({
    queryKey: ["offsetSimulate", p],
    queryFn: () =>
      fetcher(urls.offsetSimulate(p!))
        .then((d) => mapOffsetSimulateResult(d as Raw)) as Promise<OffsetSimulateResult>,
    enabled: !!p?.symbol,
  });
}

// ── Overview ──────────────────────────────────────────────────────────────────

export function useOverview(p?: { asOf?: string; catalystDays?: number }) {
  return useQuery({
    queryKey: ["overview", p?.asOf, p?.catalystDays],
    queryFn: () =>
      fetcher(urls.overview(p)).then((d) => mapOverview(d as Raw)) as Promise<OverviewData>,
  });
}

// ── Demo ──────────────────────────────────────────────────────────────────────

export function useSeedDemo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => post("/api/demo/seed", {}),
    onSuccess: () => {
      // Invalidate everything so all pages refresh with new demo data
      qc.invalidateQueries();
    },
  });
}

// ── Alerts ────────────────────────────────────────────────────────────────────
import {
  mapPriceAlert, mapAlertCheckResult,
  mapChipData, mapChipRangeResult,
  mapRollingLog, mapRollingLogSummary, mapSectorCheck,
} from "@/lib/api";
import type {
  PriceAlert, AlertCheckResult,
  ChipData, ChipRangeResult,
  RollingLog, RollingLogSummary, SectorCheck,
} from "@/lib/types";

export function useAlerts(includeTriggered = false) {
  return useQuery({
    queryKey: ["alerts", includeTriggered],
    queryFn: () =>
      fetcher(urls.alerts(includeTriggered)).then((d) => (d as Raw[]).map(mapPriceAlert)) as Promise<PriceAlert[]>,
  });
}

export function useCheckAlerts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => fetcher(urls.alertsCheck()) as Promise<AlertCheckResult>,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

export function useCreateAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { symbol: string; alert_type: string; price: number; note?: string }) =>
      post<PriceAlert>("/api/alerts", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

export function useDeleteAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del(urls.alert(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
}

// ── Chip ──────────────────────────────────────────────────────────────────────

export function useChip(symbol: string, date?: string) {
  return useQuery({
    queryKey: ["chip", symbol, date],
    queryFn: () => fetcher(urls.chip(symbol, date)).then((d) => mapChipData(d as Raw)) as Promise<ChipData>,
    enabled: !!symbol,
  });
}

export function useChipRange(symbol: string, start: string, end: string) {
  return useQuery({
    queryKey: ["chipRange", symbol, start, end],
    queryFn: () => fetcher(urls.chipRange(symbol, start, end)).then((d) => mapChipRangeResult(d as Raw)) as Promise<ChipRangeResult>,
    enabled: !!symbol && !!start && !!end,
  });
}

export function usePortfolioChip(date?: string) {
  return useQuery({
    queryKey: ["chipPortfolio", date],
    queryFn: () =>
      fetcher(urls.chipPortfolio(date)).then((d) => {
        const raw = d as { date: string; holdings: Raw[] };
        return { date: raw.date, holdings: raw.holdings.map(mapChipData) };
      }),
  });
}

// ── Rolling ───────────────────────────────────────────────────────────────────

export function useRollingLog(p?: { symbol?: string; start?: string; end?: string; limit?: number }) {
  return useQuery({
    queryKey: ["rollingLog", p],
    queryFn: () =>
      fetcher(urls.rollingLog(p)).then((d) => (d as Raw[]).map(mapRollingLog)) as Promise<RollingLog[]>,
  });
}

export function useRollingLogSummary(symbol?: string) {
  return useQuery({
    queryKey: ["rollingLogSummary", symbol],
    queryFn: () =>
      fetcher(urls.rollingSummary(symbol)).then((d) => mapRollingLogSummary(d as Raw)) as Promise<RollingLogSummary>,
  });
}

export function useSectorCheck(asOf?: string) {
  return useQuery({
    queryKey: ["sectorCheck", asOf],
    queryFn: () =>
      fetcher(urls.sectorCheck(asOf)).then((d) => mapSectorCheck(d as Raw)) as Promise<SectorCheck>,
  });
}

export function useCreateRollingLog() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      date: string; symbol: string; action: string;
      shares?: number; sell_price?: number; buy_price?: number;
      profit_amount?: number; note?: string;
    }) => post<{ id: number }>("/api/rolling", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rollingLog"] });
      qc.invalidateQueries({ queryKey: ["rollingLogSummary"] });
    },
  });
}

export function useDeleteRollingLog() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => del(urls.rollingLog() + `/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rollingLog"] }),
  });
}

// ── Chart / Technical Indicators ──────────────────────────────────────────────
import type {
  ChartData, RevenueData, AllocationData, ScreenerResponse, AnomalyResult, AnomalyBatchResult,
  ResearchCompany, ResearchThemesResponse, ResearchThemeResponse, ResearchSearchResponse, ResearchSupplyChainResponse,
} from "@/lib/types";
import {
  mapResearchCompany, mapResearchThemes, mapResearchTheme, mapResearchSearch, mapResearchSupplyChain,
} from "@/lib/api";

export function useChart(symbol: string | null, days = 120) {
  return useQuery({
    queryKey: ["chart", symbol, days],
    queryFn: () => fetcher(urls.chart(symbol!, days)) as Promise<ChartData>,
    enabled: !!symbol,
  });
}

// ── Monthly Revenue ────────────────────────────────────────────────────────────

export function useRevenue(symbol: string | null, limit = 24) {
  return useQuery({
    queryKey: ["revenue", symbol, limit],
    queryFn: async () => {
      const raw = (await fetcher(urls.revenue(symbol!, limit))) as {
        symbol: string; count: number;
        data: { year_month: string; revenue: number; yoy_pct: number | null; mom_pct: number | null }[];
      };
      return {
        symbol: raw.symbol,
        count: raw.count,
        data: raw.data.map((r) => ({
          yearMonth: r.year_month,
          revenue: r.revenue,
          yoyPct: r.yoy_pct,
          momPct: r.mom_pct,
        })),
      } as RevenueData;
    },
    enabled: !!symbol,
  });
}

export function useFetchRevenue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) =>
      post<{ fetched: number }>(`/api/revenue/${symbol}/fetch`, {}),
    onSuccess: (_d, sym) => qc.invalidateQueries({ queryKey: ["revenue", sym] }),
  });
}

// ── Allocation ────────────────────────────────────────────────────────────────

export function useAllocation(asOf?: string) {
  return useQuery({
    queryKey: ["allocation", asOf],
    queryFn: () => fetcher(urls.allocation(asOf)) as Promise<AllocationData>,
  });
}

// ── Screener ──────────────────────────────────────────────────────────────────

export function useScreener(p?: {
  sector?: string; exchange?: string; country?: string;
  inPositions?: boolean; inWatchlist?: boolean;
  minYoyPct?: number; foreignNetPositive?: boolean; limit?: number;
}) {
  return useQuery({
    queryKey: ["screener", p],
    queryFn: () => fetcher(urls.screener(p)) as Promise<ScreenerResponse>,
  });
}

export function useAnomaly(
  symbol: string | null,
  p?: { days?: number; method?: string; zscoreThreshold?: number; aeThreshold?: number },
) {
  return useQuery({
    queryKey: ["anomaly", symbol, p],
    queryFn: () => fetcher(urls.anomaly(symbol!, p)) as Promise<AnomalyResult>,
    enabled: !!symbol,
  });
}

export function useAnomalyBatch(p?: { days?: number }) {
  return useQuery({
    queryKey: ["anomalyBatch", p],
    queryFn: () => fetcher(urls.anomalyBatch(p)) as Promise<AnomalyBatchResult>,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// ── Research hooks ────────────────────────────────────────────────────────────

export function useResearchCompany(ticker: string | null) {
  return useQuery({
    queryKey: ["research", "company", ticker],
    queryFn: () => fetcher(urls.researchCompany(ticker!)).then(mapResearchCompany) as Promise<ResearchCompany>,
    enabled: !!ticker,
    staleTime: 10 * 60 * 1000,
  });
}

export function useResearchSupplyChain(ticker: string | null) {
  return useQuery({
    queryKey: ["research", "supplyChain", ticker],
    queryFn: () => fetcher(urls.researchSupplyChain(ticker!)).then(mapResearchSupplyChain) as Promise<ResearchSupplyChainResponse>,
    enabled: !!ticker,
    staleTime: 10 * 60 * 1000,
  });
}

export function useResearchThemes() {
  return useQuery({
    queryKey: ["research", "themes"],
    queryFn: () => fetcher(urls.researchThemes()).then(mapResearchThemes) as Promise<ResearchThemesResponse>,
    staleTime: 30 * 60 * 1000,
  });
}

export function useResearchTheme(theme: string | null) {
  return useQuery({
    queryKey: ["research", "theme", theme],
    queryFn: () => fetcher(urls.researchTheme(theme!)).then(mapResearchTheme) as Promise<ResearchThemeResponse>,
    enabled: !!theme,
    staleTime: 10 * 60 * 1000,
  });
}

export function useResearchSearch(q: string, limit?: number) {
  return useQuery({
    queryKey: ["research", "search", q, limit],
    queryFn: () => fetcher(urls.researchSearch(q, limit)).then(mapResearchSearch) as Promise<ResearchSearchResponse>,
    enabled: q.length >= 2,
    staleTime: 5 * 60 * 1000,
  });
}
