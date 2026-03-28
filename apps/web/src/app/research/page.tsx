"use client";

import { useState } from "react";
import {
  useResearchThemes,
  useResearchTheme,
  useResearchSearch,
  useResearchCompany,
} from "@/hooks/use-queries";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, ArrowUpRight, ArrowDownRight, Layers, ChevronRight, X, TrendingUp, Building2, Link2, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchCompany, ResearchThemeSummary, ResearchSearchResult } from "@/lib/types";
import { useDebounce } from "@/hooks/use-debounce";

// ── Theme color map ──────────────────────────────────────────────────────────

const THEME_ACCENT: Record<string, { bar: string; badge: string }> = {
  "AI_伺服器": { bar: "bg-violet-500", badge: "bg-violet-500/15 text-violet-300 border-violet-500/30" },
  "HBM":       { bar: "bg-purple-500", badge: "bg-purple-500/15 text-purple-300 border-purple-500/30" },
  "CoWoS":     { bar: "bg-indigo-500", badge: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30" },
  "ABF_載板":  { bar: "bg-blue-500",   badge: "bg-blue-500/15 text-blue-300 border-blue-500/30" },
  "NVIDIA":    { bar: "bg-green-500",  badge: "bg-green-500/15 text-green-300 border-green-500/30" },
  "Apple":     { bar: "bg-slate-400",  badge: "bg-slate-400/15 text-slate-300 border-slate-400/30" },
  "5G":        { bar: "bg-cyan-500",   badge: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30" },
  "CPO":       { bar: "bg-teal-500",   badge: "bg-teal-500/15 text-teal-300 border-teal-500/30" },
  "EUV":       { bar: "bg-orange-500", badge: "bg-orange-500/15 text-orange-300 border-orange-500/30" },
  "電動車":    { bar: "bg-emerald-500",badge: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" },
};
const DEFAULT_ACCENT = { bar: "bg-primary/70", badge: "bg-primary/15 text-primary border-primary/30" };

function themeAccent(name: string) {
  return THEME_ACCENT[name] ?? DEFAULT_ACCENT;
}

// ── Stats bar ────────────────────────────────────────────────────────────────

function StatsBar({ total, themeCount }: { total?: number; themeCount?: number }) {
  return (
    <div className="grid grid-cols-3 gap-3 mb-4">
      {[
        { label: "覆蓋公司", value: total?.toLocaleString() ?? "—", icon: Building2, color: "text-tv-blue" },
        { label: "投資主題", value: themeCount?.toString() ?? "—", icon: Layers, color: "text-violet-400" },
        { label: "供應鏈節點", value: "8,313", icon: Link2, color: "text-tv-up" },
      ].map(({ label, value, icon: Icon, color }) => (
        <div key={label} className="flex items-center gap-3 rounded-xl border border-border/40 bg-secondary/20 px-4 py-3">
          <Icon className={cn("h-5 w-5 shrink-0", color)} />
          <div>
            <p className={cn("text-lg font-bold tabular-nums leading-none", color)}>{value}</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Left sidebar — theme list ────────────────────────────────────────────────

function ThemeSidebar({
  themes,
  loading,
  selected,
  onSelect,
  maxCount,
}: {
  themes: ResearchThemeSummary[];
  loading: boolean;
  selected: string | null;
  onSelect: (t: string | null) => void;
  maxCount: number;
}) {
  return (
    <aside className="w-64 shrink-0 flex flex-col gap-1.5 overflow-y-auto max-h-[calc(100vh-180px)] pr-1">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1 mb-1">
        投資主題
      </p>
      {loading
        ? Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-xl" />
          ))
        : themes.map((t) => {
            const accent = themeAccent(t.themeName);
            const pct = maxCount > 0 ? (t.companyCount / maxCount) * 100 : 0;
            const active = selected === t.themeName;
            return (
              <button
                key={t.themeName}
                onClick={() => onSelect(active ? null : t.themeName)}
                className={cn(
                  "group relative w-full text-left rounded-xl border px-3 py-2.5 transition-all duration-150 overflow-hidden",
                  active
                    ? "border-primary/60 bg-primary/10 shadow-sm"
                    : "border-border/40 bg-secondary/20 hover:border-border hover:bg-secondary/40",
                )}
              >
                {/* color bar */}
                <span
                  className={cn("absolute left-0 top-0 h-full w-1 rounded-l-xl transition-opacity", accent.bar, active ? "opacity-100" : "opacity-40 group-hover:opacity-70")}
                />
                <div className="pl-2">
                  <div className="flex items-center justify-between">
                    <span className={cn("text-sm font-medium leading-tight", active ? "text-foreground" : "text-foreground/80")}>
                      {t.themeName}
                    </span>
                    <span className="text-xs tabular-nums text-muted-foreground">{t.companyCount}</span>
                  </div>
                  {/* mini bar chart */}
                  <div className="mt-1.5 h-1 w-full rounded-full bg-muted/40">
                    <div
                      className={cn("h-full rounded-full transition-all", accent.bar, "opacity-60")}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </button>
            );
          })}
    </aside>
  );
}

// ── Company card ─────────────────────────────────────────────────────────────

function CompanyCard({
  company,
  onClick,
  active,
}: {
  company: { ticker: string; name: string; industry?: string | null; descriptionSnippet?: string | null; sector?: string | null };
  onClick: () => void;
  active: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-xl border p-4 transition-all duration-150 group",
        active
          ? "border-primary/60 bg-primary/10 shadow-sm"
          : "border-border/40 bg-secondary/20 hover:border-border/70 hover:bg-secondary/40",
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="font-mono text-sm font-bold text-tv-blue tabular-nums">{company.ticker}</span>
        {company.industry && (
          <Badge variant="outline" className="text-[10px] shrink-0">{company.industry}</Badge>
        )}
      </div>
      <p className="font-semibold text-sm leading-snug text-foreground/90 mb-1">{company.name}</p>
      {company.descriptionSnippet && (
        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
          {company.descriptionSnippet}
        </p>
      )}
      <div className={cn("mt-2 flex items-center gap-1 text-xs", active ? "text-primary" : "text-muted-foreground group-hover:text-foreground/60")}>
        <ChevronRight className="h-3 w-3" />
        <span>查看詳情</span>
      </div>
    </button>
  );
}

// ── Supply chain flow visualization ──────────────────────────────────────────

function SupplyChainFlow({ company }: { company: ResearchCompany }) {
  const upstream = company.supplyChain.filter((s) => s.direction === "upstream").slice(0, 6);
  const downstream = company.supplyChain.filter((s) => s.direction === "downstream").slice(0, 6);

  return (
    <div className="rounded-xl border border-border/40 bg-secondary/10 p-4">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">供應鏈位置</p>
      <div className="flex items-stretch gap-3">
        {/* Upstream */}
        <div className="flex-1 space-y-1.5">
          <div className="flex items-center gap-1 text-xs font-medium text-amber-400 mb-2">
            <ArrowUpRight className="h-3.5 w-3.5" />
            上游 ({upstream.length})
          </div>
          {upstream.length === 0 ? (
            <p className="text-xs text-muted-foreground/50 italic">無資料</p>
          ) : upstream.map((s, i) => (
            <div key={i} className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-2.5 py-1.5">
              <p className="text-xs font-medium text-foreground/80 leading-snug">{s.entity}</p>
              {s.roleNote && <p className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{s.roleNote}</p>}
            </div>
          ))}
        </div>

        {/* Center arrow + company */}
        <div className="flex flex-col items-center justify-center gap-2 shrink-0">
          <div className="h-px w-8 bg-muted-foreground/20" />
          <div className="rounded-xl border-2 border-primary/50 bg-primary/10 px-3 py-3 text-center min-w-[80px]">
            <p className="text-xs font-bold text-primary tabular-nums">{company.ticker}</p>
            <p className="text-[10px] font-semibold text-foreground/80 mt-0.5 leading-tight">{company.name}</p>
          </div>
          <div className="h-px w-8 bg-muted-foreground/20" />
        </div>

        {/* Downstream */}
        <div className="flex-1 space-y-1.5">
          <div className="flex items-center gap-1 text-xs font-medium text-blue-400 mb-2">
            <ArrowDownRight className="h-3.5 w-3.5" />
            下游 ({downstream.length})
          </div>
          {downstream.length === 0 ? (
            <p className="text-xs text-muted-foreground/50 italic">無資料</p>
          ) : downstream.map((s, i) => (
            <div key={i} className="rounded-lg border border-blue-500/20 bg-blue-500/5 px-2.5 py-1.5">
              <p className="text-xs font-medium text-foreground/80 leading-snug">{s.entity}</p>
              {s.roleNote && <p className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{s.roleNote}</p>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Company detail panel ──────────────────────────────────────────────────────

function CompanyDetailPanel({
  ticker,
  onClose,
}: {
  ticker: string;
  onClose: () => void;
}) {
  const { data: company, isLoading } = useResearchCompany(ticker);
  const customers = company?.customers.filter((c) => c.isCustomer) ?? [];
  const suppliers = company?.customers.filter((c) => !c.isCustomer) ?? [];

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        {isLoading || !company ? (
          <div className="space-y-2 flex-1">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-7 w-48" />
          </div>
        ) : (
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-mono text-base font-bold text-tv-blue tabular-nums">{company.ticker}</span>
              {company.sector && <Badge variant="outline" className="text-xs">{company.sector}</Badge>}
              {company.industry && <Badge variant="secondary" className="text-xs">{company.industry}</Badge>}
            </div>
            <h2 className="text-xl font-bold leading-tight">{company.name}</h2>
          </div>
        )}
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 hover:bg-secondary/60 text-muted-foreground hover:text-foreground transition-colors shrink-0"
          aria-label="關閉"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {isLoading || !company ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-xl" />)}
        </div>
      ) : (
        <>
          {/* Market cap cards */}
          {(company.marketCapMillionTwd || company.evMillionTwd) && (
            <div className="grid grid-cols-2 gap-3">
              {company.marketCapMillionTwd && (
                <div className="rounded-xl border border-border/40 bg-secondary/20 px-4 py-3">
                  <p className="text-[11px] text-muted-foreground mb-1 flex items-center gap-1">
                    <TrendingUp className="h-3 w-3" /> 市值
                  </p>
                  <p className="text-lg font-bold tabular-nums text-foreground">
                    {(company.marketCapMillionTwd / 1000).toFixed(0)}
                    <span className="text-xs font-normal text-muted-foreground ml-1">億 TWD</span>
                  </p>
                </div>
              )}
              {company.evMillionTwd && (
                <div className="rounded-xl border border-border/40 bg-secondary/20 px-4 py-3">
                  <p className="text-[11px] text-muted-foreground mb-1 flex items-center gap-1">
                    <BarChart3 className="h-3 w-3" /> 企業價值
                  </p>
                  <p className="text-lg font-bold tabular-nums text-foreground">
                    {(company.evMillionTwd / 1000).toFixed(0)}
                    <span className="text-xs font-normal text-muted-foreground ml-1">億 TWD</span>
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Description */}
          {company.description && (
            <p className="text-sm text-muted-foreground leading-relaxed border-l-2 border-primary/40 pl-3">
              {company.description}
            </p>
          )}

          {/* Themes */}
          {company.themes.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">投資主題</p>
              <div className="flex flex-wrap gap-1.5">
                {company.themes.map((t) => {
                  const accent = themeAccent(t);
                  return (
                    <span key={t} className={cn("text-xs px-2 py-0.5 rounded-md border font-medium", accent.badge)}>
                      {t}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Supply chain flow */}
          <SupplyChainFlow company={company} />

          {/* Customers / Suppliers */}
          {(customers.length > 0 || suppliers.length > 0) && (
            <div className="grid grid-cols-2 gap-3">
              {customers.length > 0 && (
                <div className="rounded-xl border border-border/40 bg-secondary/10 p-3">
                  <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    主要客戶
                  </p>
                  <div className="space-y-1">
                    {customers.slice(0, 5).map((c, i) => (
                      <div key={i} className="flex items-center justify-between text-xs py-0.5">
                        <span className="text-foreground/80 truncate flex-1">{c.counterpart}</span>
                        {c.note && <span className="text-muted-foreground ml-2 shrink-0 text-[10px]">{c.note}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {suppliers.length > 0 && (
                <div className="rounded-xl border border-border/40 bg-secondary/10 p-3">
                  <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                    主要供應商
                  </p>
                  <div className="space-y-1">
                    {suppliers.slice(0, 5).map((s, i) => (
                      <div key={i} className="flex items-center justify-between text-xs py-0.5">
                        <span className="text-foreground/80 truncate flex-1">{s.counterpart}</span>
                        {s.note && <span className="text-muted-foreground ml-2 shrink-0 text-[10px]">{s.note}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Search results ────────────────────────────────────────────────────────────

function SearchResults({
  results,
  loading,
  total,
  onSelect,
  selectedTicker,
}: {
  results: ResearchSearchResult[];
  loading: boolean;
  total: number;
  onSelect: (t: string) => void;
  selectedTicker: string | null;
}) {
  return (
    <div className="flex-1 overflow-y-auto">
      <p className="text-xs text-muted-foreground mb-3">
        搜尋結果 · <span className="text-foreground font-medium">{total}</span> 筆
      </p>
      {loading ? (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}
        </div>
      ) : results.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
          <Search className="h-8 w-8 opacity-30" />
          <p className="text-sm">找不到相關公司</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
          {results.map((r) => (
            <CompanyCard
              key={r.ticker}
              company={r}
              onClick={() => onSelect(r.ticker)}
              active={selectedTicker === r.ticker}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ResearchPage() {
  const [selectedTheme, setSelectedTheme] = useState<string | null>(null);
  const [searchQ, setSearchQ] = useState("");
  const debouncedQ = useDebounce(searchQ, 350);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  const { data: themesData, isLoading: themesLoading } = useResearchThemes();
  const { data: themeCompanies, isLoading: themeLoading } = useResearchTheme(selectedTheme);
  const { data: searchData, isLoading: searchLoading } = useResearchSearch(debouncedQ);

  const isSearching = debouncedQ.length >= 2;
  const maxThemeCount = themesData ? Math.max(...themesData.themes.map((t) => t.companyCount), 1) : 1;

  const handleThemeSelect = (t: string | null) => {
    setSelectedTheme(t);
    setSelectedTicker(null);
  };
  const handleTickerSelect = (t: string) => setSelectedTicker(t);
  const handleTickerClose = () => setSelectedTicker(null);

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Page header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Layers className="h-5 w-5 text-violet-400" />
            研究資料庫
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Taiwan Stock Coverage · AI 供應鏈知識圖譜
          </p>
        </div>
        {/* Search */}
        <div className="relative w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="搜尋代號、公司名稱、產業..."
            value={searchQ}
            onChange={(e) => { setSearchQ(e.target.value); setSelectedTicker(null); }}
            className="pl-9"
          />
          {searchQ && (
            <button
              onClick={() => setSearchQ("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <StatsBar total={themesData?.themes.reduce((s, t) => s + t.companyCount, 0)} themeCount={themesData?.total} />

      {/* Body: sidebar + main content */}
      <div className="flex gap-5 flex-1 min-h-0">
        {/* Left sidebar — themes (hidden during search) */}
        {!isSearching && (
          <ThemeSidebar
            themes={themesData?.themes ?? []}
            loading={themesLoading}
            selected={selectedTheme}
            onSelect={handleThemeSelect}
            maxCount={maxThemeCount}
          />
        )}

        {/* Main content area */}
        <div className={cn("flex flex-1 gap-4 min-w-0", selectedTicker ? "items-start" : "")}>
          {/* Company list / search results */}
          <div className={cn("flex flex-col flex-1 min-w-0 overflow-y-auto max-h-[calc(100vh-260px)]", selectedTicker ? "max-w-sm" : "")}>
            {isSearching ? (
              <SearchResults
                results={searchData?.results ?? []}
                loading={searchLoading}
                total={searchData?.total ?? 0}
                onSelect={handleTickerSelect}
                selectedTicker={selectedTicker}
              />
            ) : !selectedTheme ? (
              /* Empty state */
              <div className="flex flex-col items-center justify-center h-full text-center py-24 text-muted-foreground gap-3">
                <Layers className="h-10 w-10 opacity-20" />
                <p className="text-sm font-medium">選擇左側主題</p>
                <p className="text-xs opacity-60">或使用搜尋框找公司</p>
              </div>
            ) : themeLoading ? (
              <div className="grid grid-cols-2 gap-3">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)}
              </div>
            ) : (
              <>
                <div className="flex items-center gap-2 mb-3">
                  <span className={cn("inline-block h-3 w-3 rounded-full", themeAccent(selectedTheme).bar)} />
                  <span className="font-semibold text-sm">{selectedTheme}</span>
                  <span className="text-xs text-muted-foreground">· {themeCompanies?.total ?? 0} 家公司</span>
                </div>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                  {themeCompanies?.companies.map((c) => (
                    <CompanyCard
                      key={c.ticker}
                      company={c}
                      onClick={() => handleTickerSelect(c.ticker)}
                      active={selectedTicker === c.ticker}
                    />
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Company detail panel */}
          {selectedTicker && (
            <div className="w-[420px] xl:w-[480px] shrink-0 rounded-2xl border border-border/50 bg-secondary/10 p-5 overflow-y-auto max-h-[calc(100vh-260px)]">
              <CompanyDetailPanel ticker={selectedTicker} onClose={handleTickerClose} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
