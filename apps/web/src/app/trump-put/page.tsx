"use client";

export const dynamic = "force-dynamic";

import { useQuery } from "@tanstack/react-query";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { fmt } from "@/lib/format";
import { useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  Scatter,
} from "recharts";

// ── Types ────────────────────────────────────────────────────────────────────

interface Indicator {
  symbol: string;
  name: string;
  value: number;
  as_of: string;
  zone: string;
  score: number;
}

interface HistEvent {
  date: string;
  sp500: number | null;
  tnx: number | null;
  description: string;
  event_type: "reversal" | "escalation" | "marker";
}

interface BacktestPair {
  escalation_date: string;
  reversal_date: string;
  days: number;
  sp500_at_escalation: number | null;
  sp500_at_reversal: number | null;
  drawdown_pct: number | null;
}

interface BacktestData {
  pairs: BacktestPair[];
  avg_days_to_reversal: number;
  hit_rates: Record<string, { threshold: number; total_escalations: number; reversed_within_30d: number; hit_rate: number; avg_days: number }>;
  current_prediction: string | null;
}

interface TariffEvent {
  date: string;
  target: string;
  rate: number | null;
  prev_rate: number | null;
  status: string;
  category: string;
  source: string;
}

interface Report {
  timestamp: string;
  composite_score: number;
  composite_label: string;
  narrative: string;
  indicators: {
    sp500: Indicator | null;
    tnx: Indicator | null;
    vix: Indicator | null;
    dxy: Indicator | null;
    approval: Indicator | null;
  };
  nearby_events: HistEvent[];
  backtest: BacktestData | null;
}

interface ChartPoint {
  date: string;
  close: number;
}

interface ChartData {
  sp500: ChartPoint[];
  tnx: ChartPoint[];
  vix: ChartPoint[];
  dxy: ChartPoint[];
}

// ── Hooks ────────────────────────────────────────────────────────────────────

function useReport() {
  return useQuery<Report>({
    queryKey: ["trump-put-report"],
    queryFn: () => fetcher("/api/trump-put/report"),
    refetchInterval: 300_000,
  });
}

function useChartData() {
  return useQuery<ChartData>({
    queryKey: ["trump-put-chart"],
    queryFn: () => fetcher("/api/trump-put/chart-data?period=6mo"),
    refetchInterval: 300_000,
  });
}

function useHistory() {
  return useQuery<HistEvent[]>({
    queryKey: ["trump-put-history"],
    queryFn: () => fetcher("/api/trump-put/history"),
  });
}

function useTariffs() {
  return useQuery<{ events: TariffEvent[]; summary: Record<string, unknown> }>({
    queryKey: ["trump-put-tariffs"],
    queryFn: () => fetcher("/api/trump-put/tariffs"),
  });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function scoreColor(s: number): string {
  if (s <= 20) return "text-emerald-400";
  if (s <= 40) return "text-yellow-400";
  if (s <= 60) return "text-orange-400";
  return "text-red-400";
}

function scoreBg(s: number): string {
  if (s <= 20) return "bg-emerald-400/10 border-emerald-400/20";
  if (s <= 40) return "bg-yellow-400/10 border-yellow-400/20";
  if (s <= 60) return "bg-orange-400/10 border-orange-400/20";
  return "bg-red-400/10 border-red-400/20";
}

function scoreDot(s: number): string {
  if (s <= 20) return "bg-emerald-400";
  if (s <= 40) return "bg-yellow-400";
  if (s <= 60) return "bg-orange-400";
  return "bg-red-400";
}

function scoreBgSolid(s: number): string {
  if (s <= 20) return "bg-emerald-500";
  if (s <= 40) return "bg-yellow-500";
  if (s <= 60) return "bg-orange-500";
  return "bg-red-500";
}

function formatValue(symbol: string, value: number): string {
  if (symbol === "sp500") return fmt(value, 2);
  if (symbol === "tnx") return fmt(value, 3) + "%";
  if (symbol === "approval") return value.toFixed(1) + "%";
  return fmt(value, 2);
}

function eventIcon(type: string): string {
  if (type === "reversal") return "↩️";
  if (type === "escalation") return "⚠️";
  return "·";
}

function eventColor(type: string): string {
  if (type === "reversal") return "text-emerald-400";
  if (type === "escalation") return "text-red-400";
  return "text-yellow-400";
}

function statusLabel(label: string): string {
  const map: Record<string, string> = {
    "Dormant": "市場平穩",
    "Elevated": "風險升溫",
    "Active": "壓力上升",
    "Acute": "高度警戒",
    "Critical": "危機警報",
  };
  return map[label] ?? label;
}

function statusHeadline(score: number): string {
  if (score <= 20) return "川普不太可能介入市場，政策風向穩定";
  if (score <= 40) return "壓力正在醞釀中，留意政策動態";
  if (score <= 60) return "市場壓力升高，川普可能調整貿易/外交政策";
  if (score <= 80) return "高度警戒——歷史經驗顯示政策轉向機率大幅上升";
  return "極端壓力——預期即將出現重大政策逆轉";
}

const statusColor: Record<string, string> = {
  effective: "bg-red-500/20 text-red-400 border-red-500/30",
  announced: "bg-red-500/10 text-red-300 border-red-500/20",
  threatened: "bg-orange-500/10 text-orange-300 border-orange-500/20",
  paused: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  reduced: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  exempted: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  expired: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  struck_down: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
};

// ── Status Banner ───────────────────────────────────────────────────────────

function StatusBanner({ score, label }: { score: number; label: string }) {
  return (
    <div className={cn("rounded-xl border p-5", scoreBg(score))}>
      <div className="flex items-center gap-3 mb-3">
        <div className="relative flex-shrink-0">
          <div className={cn("w-3.5 h-3.5 rounded-full", scoreBgSolid(score))} />
          <div className={cn("absolute inset-0 w-3.5 h-3.5 rounded-full animate-ping opacity-40", scoreBgSolid(score))} />
        </div>
        <div className="flex items-baseline gap-2">
          <span className={cn("text-3xl font-extrabold tabular-nums", scoreColor(score))}>
            {score}
          </span>
          <span className="text-sm text-muted-foreground">/100</span>
          <Badge variant="outline" className={cn("ml-2", scoreColor(score))}>
            {statusLabel(label)}
          </Badge>
        </div>
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed">
        {statusHeadline(score)}
      </p>
    </div>
  );
}

// ── Hero Explainer ──────────────────────────────────────────────────────────

const ZONE_LEGEND = [
  { range: "0 – 20", label: "Dormant 市場平穩", color: "bg-emerald-400", desc: "政策穩定，川普不太可能介入" },
  { range: "21 – 40", label: "Elevated 風險升溫", color: "bg-yellow-400", desc: "壓力醞釀中，留意政策動向" },
  { range: "41 – 60", label: "Active 壓力上升", color: "bg-orange-400", desc: "政策可能軟化 (歷史先例)" },
  { range: "61 – 100", label: "Acute/Critical 警戒", color: "bg-red-400", desc: "極大機率出現政策逆轉" },
];

function HeroExplainer() {
  const [open, setOpen] = useState(false);

  return (
    <Card className="border-dashed">
      <CardContent className="pt-5 pb-4">
        <button
          onClick={() => setOpen(!open)}
          className="w-full text-left flex items-center justify-between"
        >
          <div>
            <h2 className="text-base font-semibold">
              什麼是「川普看跌期權」？
            </h2>
            <p className="text-sm text-muted-foreground mt-1">
              當市場下跌到一定程度，川普傾向主動軟化貿易或軍事政策來穩定股市。
              這個追蹤器量化目前市場壓力離「政策逆轉點」還有多遠。
            </p>
          </div>
          <span className="text-muted-foreground text-lg flex-shrink-0 ml-4">
            {open ? "▲" : "▼"}
          </span>
        </button>
        {open && (
          <div className="mt-4 space-y-4">
            <div className="text-xs text-muted-foreground space-y-1">
              <p><strong>理論來源：</strong>BofA (Hartnett) / Evercore (Emanuel) 2025 年研究</p>
              <p><strong>追蹤指標：</strong>S&P 500 (30%) · 10Y 殖利率 (25%) · VIX 恐慌指數 (15%) · 美元指數 (15%) · 支持率 (15%)</p>
              <p><strong>資料來源：</strong>Yahoo Finance · FRED · Polygon.io（有 API Key 時提供近即時數據）</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {ZONE_LEGEND.map((z) => (
                <div key={z.range} className="flex items-center gap-2 text-xs p-2 rounded-md bg-secondary/30">
                  <div className={cn("w-3 h-3 rounded-full flex-shrink-0", z.color)} />
                  <div>
                    <span className="font-medium">{z.range}</span>
                    <span className="text-muted-foreground ml-1.5">{z.label}</span>
                    <div className="text-muted-foreground/70 text-[10px] mt-0.5">{z.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Score Gauge Panel ───────────────────────────────────────────────────────

function ScoreGaugePanel({ report }: { report: Report }) {
  const indicators = [
    report.indicators.sp500,
    report.indicators.tnx,
    report.indicators.vix,
    report.indicators.dxy,
    report.indicators.approval,
  ].filter(Boolean) as Indicator[];

  const pct = Math.min(100, Math.max(0, report.composite_score));

  return (
    <div className="space-y-4">
      {/* Scale bar */}
      <div className="relative h-4 rounded-full bg-secondary/50 overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all duration-700"
          style={{
            width: `${pct}%`,
            background: pct <= 20 ? "#34d399" : pct <= 40 ? "#facc15" : pct <= 60 ? "#fb923c" : "#f87171",
          }}
        />
        <div className="absolute inset-0 flex items-center justify-between px-2 text-[9px] text-muted-foreground/60 font-medium">
          <span>0</span>
          <span>20</span>
          <span>40</span>
          <span>60</span>
          <span>80</span>
          <span>100</span>
        </div>
      </div>

      {/* Indicator chips */}
      <div className="flex flex-wrap gap-2">
        {indicators.map((ind) => (
          <div
            key={ind.symbol}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1.5 border text-xs",
              scoreBg(ind.score)
            )}
          >
            <div className={cn("w-2 h-2 rounded-full", scoreDot(ind.score))} />
            <span className="font-medium">{ind.name}</span>
            <span className="text-muted-foreground">{formatValue(ind.symbol, ind.value)}</span>
            <span className={cn("font-mono text-[10px]", scoreColor(ind.score))}>{ind.score}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Gauge Ring (kept for detail view) ───────────────────────────────────────

function GaugeRing({ score, label }: { score: number; label: string }) {
  const pct = Math.min(100, Math.max(0, score));
  const r = 72;
  const c = 2 * Math.PI * r;
  const half = c / 2;
  const filled = (pct / 100) * half;

  const color =
    pct <= 20 ? "#34d399" : pct <= 40 ? "#facc15" : pct <= 60 ? "#fb923c" : "#f87171";

  return (
    <div className="flex flex-col items-center">
      <svg width="200" height="120" viewBox="0 0 200 120">
        <path
          d="M 20 100 A 72 72 0 0 1 180 100"
          fill="none"
          stroke="currentColor"
          strokeWidth="10"
          className="text-muted/20"
        />
        <path
          d="M 20 100 A 72 72 0 0 1 180 100"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${c}`}
          style={{ transition: "stroke-dasharray 0.8s ease" }}
        />
      </svg>
      <div className="-mt-16 text-center">
        <div className="text-4xl font-extrabold tabular-nums" style={{ color }}>
          {score}
        </div>
        <div className="text-sm font-semibold mt-1" style={{ color }}>
          {label}
        </div>
      </div>
    </div>
  );
}

// ── Indicator Card ───────────────────────────────────────────────────────────

function IndicatorCard({ ind }: { ind: Indicator | null }) {
  if (!ind) return null;
  return (
    <div className={cn("rounded-lg border p-4", scoreBg(ind.score))}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground">{ind.name}</span>
        <div className={cn("w-2 h-2 rounded-full", scoreDot(ind.score))} />
      </div>
      <div className="text-2xl font-bold tabular-nums">
        {formatValue(ind.symbol, ind.value)}
      </div>
      <div className="flex items-center justify-between mt-2">
        <Badge variant="outline" className="text-[10px]">
          {ind.zone}
        </Badge>
        <span className={cn("text-xs font-medium", scoreColor(ind.score))}>
          {ind.score}/100
        </span>
      </div>
      <div className="text-[10px] text-muted-foreground mt-1">
        as of {ind.as_of}
      </div>
    </div>
  );
}

// ── Charts ───────────────────────────────────────────────────────────────────

interface EventMarker {
  date: string;
  close: number;
  event_type: string;
  description: string;
}

function SP500Chart({ data, events }: { data: ChartPoint[]; events: HistEvent[] }) {
  const [selectedEvent, setSelectedEvent] = useState<EventMarker | null>(null);

  const dateMap = new Map(data.map((d) => [d.date, d.close]));
  const markers: EventMarker[] = events
    .filter((e) => e.sp500 && dateMap.has(e.date))
    .map((e) => ({
      date: e.date,
      close: dateMap.get(e.date) ?? e.sp500!,
      event_type: e.event_type,
      description: e.description,
    }));

  const merged = data.map((d) => {
    const ev = markers.find((m) => m.date === d.date);
    return { ...d, eventClose: ev ? d.close : null, eventType: ev?.event_type };
  });

  return (
    <div>
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={merged} margin={{ top: 10, right: 10, bottom: 0, left: 10 }}>
          <defs>
            <linearGradient id="sp500Fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#818cf8" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#818cf8" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
          <XAxis dataKey="date" tick={{ fill: "#8b8fa3", fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} interval="preserveStartEnd" />
          <YAxis domain={["auto", "auto"]} tick={{ fill: "#8b8fa3", fontSize: 10 }} tickFormatter={(v: number) => v.toLocaleString()} />
          <Tooltip
            contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#8b8fa3" }}
          />
          <ReferenceLine y={5783} stroke="#eab30860" strokeDasharray="6 4" label={{ value: "5,783 Election", fill: "#eab30890", fontSize: 10, position: "insideTopLeft" }} />
          <ReferenceLine y={5400} stroke="#f9731660" strokeDasharray="6 4" label={{ value: "5,400 Nibble", fill: "#f9731690", fontSize: 10, position: "insideTopLeft" }} />
          <ReferenceLine y={5000} stroke="#ef444460" strokeDasharray="6 4" label={{ value: "5,000 PUT", fill: "#ef444490", fontSize: 10, position: "insideTopLeft" }} />
          <Area type="monotone" dataKey="close" stroke="#818cf8" fill="url(#sp500Fill)" strokeWidth={2} dot={false} name="S&P 500" />
          <Scatter
            dataKey="eventClose"
            fill="#fff"
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            shape={((props: any) => {
              const { cx, cy, payload } = props;
              if (!payload?.eventClose) return <></>;
              const color = payload.eventType === "reversal" ? "#34d399" : payload.eventType === "escalation" ? "#f87171" : "#facc15";
              return (
                <circle
                  cx={cx}
                  cy={cy}
                  r={5}
                  fill={color}
                  stroke="#1a1d27"
                  strokeWidth={2}
                  style={{ cursor: "pointer" }}
                  onClick={() =>
                    setSelectedEvent({
                      date: String(payload.date),
                      close: Number(payload.eventClose),
                      event_type: String(payload.eventType),
                      description: events.find((e: HistEvent) => e.date === payload.date)?.description ?? "",
                    })
                  }
                />
              );
            }) as unknown as undefined}
            name="Events"
          />
        </ComposedChart>
      </ResponsiveContainer>
      {selectedEvent && (
        <div className="mt-2 p-2 rounded-md bg-secondary/50 text-xs flex items-start gap-2">
          <span className={cn("flex-shrink-0 font-medium", eventColor(selectedEvent.event_type))}>
            {selectedEvent.date}
          </span>
          <span className="text-muted-foreground">{selectedEvent.description}</span>
          <button className="ml-auto text-muted-foreground hover:text-foreground" onClick={() => setSelectedEvent(null)}>×</button>
        </div>
      )}
    </div>
  );
}

function MiniChart({
  data,
  color,
  gradientId,
  name,
  refLines,
}: {
  data: ChartPoint[];
  color: string;
  gradientId: string;
  name: string;
  refLines?: { y: number; label: string }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <ComposedChart data={data} margin={{ top: 10, right: 10, bottom: 0, left: 10 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
        <XAxis dataKey="date" tick={{ fill: "#8b8fa3", fontSize: 10 }} tickFormatter={(d: string) => d.slice(5)} interval="preserveStartEnd" />
        <YAxis domain={["auto", "auto"]} tick={{ fill: "#8b8fa3", fontSize: 10 }} />
        <Tooltip
          contentStyle={{ background: "#1a1d27", border: "1px solid #2a2d3a", borderRadius: 8, fontSize: 12 }}
          labelStyle={{ color: "#8b8fa3" }}
        />
        {refLines?.map((rl) => (
          <ReferenceLine key={rl.y} y={rl.y} stroke="#ef444460" strokeDasharray="6 4" label={{ value: rl.label, fill: "#ef444490", fontSize: 10, position: "insideTopLeft" }} />
        ))}
        <Area type="monotone" dataKey="close" stroke={color} fill={`url(#${gradientId})`} strokeWidth={2} dot={false} name={name} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ── Event List ───────────────────────────────────────────────────────────────

function EventList({ events }: { events: HistEvent[] }) {
  const recent = [...events].reverse().slice(0, 12);
  return (
    <div className="space-y-1.5">
      {recent.map((ev, i) => (
        <div key={i} className="flex gap-2 text-xs py-1.5 border-b border-border/40 last:border-0">
          <span className="text-muted-foreground w-20 flex-shrink-0">{ev.date}</span>
          <span className={cn("w-4 flex-shrink-0", eventColor(ev.event_type))}>
            {eventIcon(ev.event_type)}
          </span>
          <span className="text-muted-foreground/80 leading-relaxed">
            {ev.description}
            {ev.sp500 && <span className="text-foreground ml-1">S&P {ev.sp500.toLocaleString()}</span>}
            {ev.tnx && <span className="text-foreground ml-1">10Y {ev.tnx}%</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Backtest Card ────────────────────────────────────────────────────────────

function BacktestCard({ data }: { data: BacktestData }) {
  return (
    <div className="space-y-4">
      {data.current_prediction && (
        <div className="p-3 rounded-md bg-yellow-400/10 border border-yellow-400/20 text-xs text-yellow-300">
          {data.current_prediction}
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        <div className="text-center">
          <div className="text-2xl font-bold tabular-nums">{data.avg_days_to_reversal}</div>
          <div className="text-[10px] text-muted-foreground">Avg days to reversal</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold tabular-nums">{data.pairs.length}</div>
          <div className="text-[10px] text-muted-foreground">Escalation-reversal pairs</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold tabular-nums">
            {data.hit_rates["40"]?.hit_rate ?? 0}%
          </div>
          <div className="text-[10px] text-muted-foreground">Reversed within 30d</div>
        </div>
      </div>
      <div className="space-y-1">
        {data.pairs.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs py-1 border-b border-border/30 last:border-0">
            <span className="text-red-400 w-24">{p.escalation_date}</span>
            <span className="text-muted-foreground">→</span>
            <span className="text-emerald-400 w-24">{p.reversal_date}</span>
            <span className="text-foreground font-medium w-16">{p.days}d</span>
            {p.drawdown_pct != null && (
              <span className={cn("text-xs", p.drawdown_pct >= 0 ? "text-emerald-400" : "text-red-400")}>
                {p.drawdown_pct >= 0 ? "+" : ""}{p.drawdown_pct}%
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tariff Timeline ──────────────────────────────────────────────────────────

function TariffTimeline({ events }: { events: TariffEvent[] }) {
  const sorted = [...events].reverse();
  return (
    <div className="space-y-1.5">
      {sorted.map((t, i) => (
        <div key={i} className="flex items-start gap-2 text-xs py-1.5 border-b border-border/40 last:border-0">
          <span className="text-muted-foreground w-20 flex-shrink-0">{t.date}</span>
          <Badge variant="outline" className={cn("text-[9px] px-1.5 py-0", statusColor[t.status] ?? "")}>
            {t.status}
          </Badge>
          <span className="text-foreground font-medium flex-shrink-0">{t.target}</span>
          <span className="text-muted-foreground/80 leading-relaxed">{t.category}</span>
          {t.rate != null && (
            <span className="text-foreground ml-auto flex-shrink-0">{t.rate}%</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────

export default function TrumpPutPage() {
  const { data: report, isLoading: reportLoading } = useReport();
  const { data: chart, isLoading: chartLoading } = useChartData();
  const { data: history } = useHistory();
  const { data: tariffData } = useTariffs();

  const indicators = report
    ? [report.indicators.sp500, report.indicators.tnx, report.indicators.vix, report.indicators.dxy, report.indicators.approval].filter(Boolean)
    : [];

  return (
    <div className="space-y-6">
      {/* ① Status Banner — instant verdict */}
      {reportLoading || !report ? (
        <Skeleton className="h-28 rounded-xl" />
      ) : (
        <StatusBanner score={report.composite_score} label={report.composite_label} />
      )}

      {/* ② Hero Explainer — collapsible 什麼是川普看跌期權 */}
      <HeroExplainer />

      {/* ③ Score Gauge Panel — scale bar + indicator chips */}
      {reportLoading || !report ? (
        <Skeleton className="h-20" />
      ) : (
        <ScoreGaugePanel report={report} />
      )}

      {/* ④ Detailed Indicators */}
      <div className="grid grid-cols-1 lg:grid-cols-6 gap-4">
        <Card className="lg:col-span-1">
          <CardContent className="pt-6 flex flex-col items-center">
            {reportLoading || !report ? (
              <Skeleton className="h-32 w-48" />
            ) : (
              <GaugeRing score={report.composite_score} label={report.composite_label} />
            )}
            <div className="text-[10px] text-muted-foreground mt-4 text-center leading-relaxed">
              S&P 30% · 10Y 25%<br />VIX 15% · DXY 15% · Approval 15%
            </div>
          </CardContent>
        </Card>

        <div className="lg:col-span-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {reportLoading || !report ? (
            Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-32" />)
          ) : (
            indicators.map((ind) => <IndicatorCard key={ind!.symbol} ind={ind} />)
          )}
        </div>
      </div>

      {/* Charts: 2x2 grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">S&P 500 — 6 Month</CardTitle>
          </CardHeader>
          <CardContent>
            {chartLoading || !chart ? (
              <Skeleton className="h-[340px]" />
            ) : (
              <SP500Chart data={chart.sp500} events={history ?? []} />
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground mt-2">
              <span><span className="inline-block w-3 h-0.5 bg-yellow-400/40 mr-1" />5,783 Election Day</span>
              <span><span className="inline-block w-3 h-0.5 bg-orange-400/40 mr-1" />5,400 Nibble Zone</span>
              <span><span className="inline-block w-3 h-0.5 bg-red-400/40 mr-1" />5,000 Trump Put</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-emerald-400 mr-1" />Reversal</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-red-400 mr-1" />Escalation</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">10Y Treasury Yield</CardTitle>
          </CardHeader>
          <CardContent>
            {chartLoading || !chart ? (
              <Skeleton className="h-[180px]" />
            ) : (
              <MiniChart data={chart.tnx} color="#f59e0b" gradientId="tnxFill" name="10Y Yield %" refLines={[{ y: 4.5, label: "4.5% Danger" }]} />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">VIX — Fear Index</CardTitle>
          </CardHeader>
          <CardContent>
            {chartLoading || !chart ? (
              <Skeleton className="h-[180px]" />
            ) : (
              <MiniChart
                data={chart.vix}
                color="#f87171"
                gradientId="vixFill"
                name="VIX"
                refLines={[
                  { y: 30, label: "30 Fear" },
                  { y: 45, label: "45 Extreme" },
                ]}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">DXY — US Dollar Index</CardTitle>
          </CardHeader>
          <CardContent>
            {chartLoading || !chart ? (
              <Skeleton className="h-[180px]" />
            ) : (
              <MiniChart
                data={chart.dxy}
                color="#a78bfa"
                gradientId="dxyFill"
                name="DXY"
                refLines={[
                  { y: 104, label: "104 Strong" },
                  { y: 107, label: "107 Extreme" },
                ]}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Analysis + Backtest + Events */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Analysis</CardTitle>
          </CardHeader>
          <CardContent>
            {reportLoading || !report ? (
              <Skeleton className="h-20" />
            ) : (
              <p className="text-sm text-muted-foreground leading-relaxed">
                {report.narrative}
              </p>
            )}
            <div className="mt-4 space-y-1.5 text-[10px] text-muted-foreground border-t border-border/40 pt-3">
              <p>Data: Yahoo Finance + FRED + Polygon.io</p>
              <p>Thresholds: BofA (Hartnett) / Evercore (Emanuel)</p>
              <p>Auto-refresh: 5 min</p>
              <p className="text-yellow-400/60">Not investment advice.</p>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Backtest — Escalation → Reversal</CardTitle>
          </CardHeader>
          <CardContent>
            {report?.backtest ? (
              <BacktestCard data={report.backtest} />
            ) : (
              <Skeleton className="h-40" />
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Historical Events
            </CardTitle>
          </CardHeader>
          <CardContent>
            {history ? (
              <EventList events={history} />
            ) : (
              <Skeleton className="h-40" />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tariff Timeline */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">
            Tariff &amp; Sanctions Timeline
            {tariffData?.summary && (
              <span className="ml-2 text-[10px] font-normal text-muted-foreground">
                {String(tariffData.summary.total_events)} events · {String(tariffData.summary.currently_active)} active
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {tariffData?.events ? (
            <TariffTimeline events={tariffData.events} />
          ) : (
            <Skeleton className="h-40" />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
