"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  urls,
  fetcher,
  post,
  patch,
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
  type Raw,
} from "@/lib/api";
import type {
  CashTx, Trade, Position, EquitySnapshot, EquityCurvePoint, LastPrice,
  DailyPoint, PositionDetailItem, LotsResponse,
  QuoteTodo, PerfSummary, RiskMetrics, RebalanceCheck, ImportResult,
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
