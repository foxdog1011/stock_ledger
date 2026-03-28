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
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, ArrowUpRight, ArrowDownRight, Layers, Building2, Link2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResearchCompany, ResearchThemeSummary } from "@/lib/types";
import { useDebounce } from "@/hooks/use-debounce";

// ── Company research sheet ────────────────────────────────────────────────────

function CompanySheet({
  ticker,
  open,
  onClose,
}: {
  ticker: string | null;
  open: boolean;
  onClose: () => void;
}) {
  const { data, isLoading } = useResearchCompany(ticker);

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full sm:max-w-xl overflow-y-auto">
        {isLoading || !data ? (
          <div className="space-y-3 mt-6">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-64" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <CompanyResearchContent company={data} />
        )}
      </SheetContent>
    </Sheet>
  );
}

function CompanyResearchContent({ company }: { company: ResearchCompany }) {
  const upstream = company.supplyChain.filter((s) => s.direction === "upstream");
  const downstream = company.supplyChain.filter((s) => s.direction === "downstream");
  const customers = company.customers.filter((c) => c.isCustomer);
  const suppliers = company.customers.filter((c) => !c.isCustomer);

  return (
    <div className="space-y-5 mt-2">
      <SheetHeader className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-muted-foreground">{company.ticker}</span>
          {company.sector && (
            <Badge variant="outline" className="text-xs">{company.sector}</Badge>
          )}
        </div>
        <SheetTitle className="text-xl leading-tight">{company.name}</SheetTitle>
        {company.industry && (
          <p className="text-sm text-muted-foreground">{company.industry}</p>
        )}
      </SheetHeader>

      {/* Financials */}
      {(company.marketCapMillionTwd || company.evMillionTwd) && (
        <div className="grid grid-cols-2 gap-3">
          {company.marketCapMillionTwd && (
            <div className="rounded-lg border px-4 py-3">
              <p className="text-xs text-muted-foreground mb-0.5">市值</p>
              <p className="font-semibold text-sm">
                {(company.marketCapMillionTwd / 1000).toFixed(0)} 億
              </p>
            </div>
          )}
          {company.evMillionTwd && (
            <div className="rounded-lg border px-4 py-3">
              <p className="text-xs text-muted-foreground mb-0.5">企業價值</p>
              <p className="font-semibold text-sm">
                {(company.evMillionTwd / 1000).toFixed(0)} 億
              </p>
            </div>
          )}
        </div>
      )}

      {/* Description */}
      {company.description && (
        <p className="text-sm text-muted-foreground leading-relaxed border-l-2 border-muted pl-3">
          {company.description}
        </p>
      )}

      {/* Themes */}
      {company.themes.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">投資主題</p>
          <div className="flex flex-wrap gap-1.5">
            {company.themes.map((t) => (
              <Badge key={t} variant="secondary" className="text-xs">{t}</Badge>
            ))}
          </div>
        </div>
      )}

      {/* Supply chain + customers tabs */}
      <Tabs defaultValue="supply">
        <TabsList className="w-full">
          <TabsTrigger value="supply" className="flex-1 text-xs">
            供應鏈 ({upstream.length + downstream.length})
          </TabsTrigger>
          <TabsTrigger value="customers" className="flex-1 text-xs">
            客戶供應商 ({customers.length + suppliers.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="supply" className="mt-3 space-y-3">
          {upstream.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-amber-600">
                <ArrowUpRight className="h-3.5 w-3.5" />
                上游 ({upstream.length})
              </div>
              <div className="space-y-1">
                {upstream.map((s, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm py-1 border-b border-dashed last:border-0">
                    <span className="flex-1">{s.entity}</span>
                    {s.roleNote && (
                      <span className="text-xs text-muted-foreground shrink-0">{s.roleNote}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {downstream.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-medium text-blue-600">
                <ArrowDownRight className="h-3.5 w-3.5" />
                下游 ({downstream.length})
              </div>
              <div className="space-y-1">
                {downstream.map((s, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm py-1 border-b border-dashed last:border-0">
                    <span className="flex-1">{s.entity}</span>
                    {s.roleNote && (
                      <span className="text-xs text-muted-foreground shrink-0">{s.roleNote}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {upstream.length === 0 && downstream.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">無供應鏈資料</p>
          )}
        </TabsContent>

        <TabsContent value="customers" className="mt-3 space-y-3">
          {customers.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">主要客戶</p>
              <div className="space-y-1">
                {customers.map((c, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm py-1 border-b border-dashed last:border-0">
                    <span className="flex-1">{c.counterpart}</span>
                    {c.note && <span className="text-xs text-muted-foreground">{c.note}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {suppliers.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">主要供應商</p>
              <div className="space-y-1">
                {suppliers.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm py-1 border-b border-dashed last:border-0">
                    <span className="flex-1">{s.counterpart}</span>
                    {s.note && <span className="text-xs text-muted-foreground">{s.note}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
          {customers.length === 0 && suppliers.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">無客戶/供應商資料</p>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Theme card ────────────────────────────────────────────────────────────────

const THEME_COLORS: Record<string, string> = {
  "AI_伺服器": "border-violet-200 bg-violet-50 text-violet-700",
  "HBM":       "border-purple-200 bg-purple-50 text-purple-700",
  "CoWoS":     "border-indigo-200 bg-indigo-50 text-indigo-700",
  "ABF_載板":  "border-blue-200 bg-blue-50 text-blue-700",
  "NVIDIA":    "border-green-200 bg-green-50 text-green-700",
  "Apple":     "border-slate-200 bg-slate-50 text-slate-700",
  "5G":        "border-cyan-200 bg-cyan-50 text-cyan-700",
  "CPO":       "border-teal-200 bg-teal-50 text-teal-700",
  "EUV":       "border-orange-200 bg-orange-50 text-orange-700",
  "電動車":    "border-emerald-200 bg-emerald-50 text-emerald-700",
};

function ThemeCard({
  theme,
  selected,
  onClick,
}: {
  theme: ResearchThemeSummary;
  selected: boolean;
  onClick: () => void;
}) {
  const color = THEME_COLORS[theme.themeName] ?? "border-zinc-200 bg-zinc-50 text-zinc-700";

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left rounded-xl border-2 px-4 py-3 transition-all",
        selected
          ? "border-primary bg-primary/5 shadow-sm"
          : cn("hover:shadow-sm", color),
      )}
    >
      <p className="font-semibold text-sm leading-tight">{theme.themeName}</p>
      <p className={cn("text-xs mt-0.5", selected ? "text-muted-foreground" : "opacity-60")}>
        {theme.companyCount} 家公司
      </p>
    </button>
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Layers className="h-6 w-6 text-violet-500" />
          研究資料庫
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          1,735 家台股 · 99 個產業 · 供應鏈知識圖譜
        </p>
      </div>

      {/* Search bar */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="搜尋公司名稱、產業、關鍵字..."
          value={searchQ}
          onChange={(e) => setSearchQ(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* Search results */}
      {isSearching && (
        <div className="rounded-xl border overflow-hidden">
          <div className="px-4 py-2.5 bg-muted/30 border-b">
            <p className="text-xs font-medium text-muted-foreground">
              搜尋結果 {searchData ? `· ${searchData.total} 筆` : ""}
            </p>
          </div>
          {searchLoading ? (
            <div className="p-4 space-y-2">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
            </div>
          ) : !searchData || searchData.results.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">找不到相關公司</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">代號</TableHead>
                  <TableHead>名稱</TableHead>
                  <TableHead className="hidden sm:table-cell">產業</TableHead>
                  <TableHead className="hidden md:table-cell">簡介</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {searchData.results.map((r) => (
                  <TableRow
                    key={r.ticker}
                    className="cursor-pointer hover:bg-muted/40"
                    onClick={() => setSelectedTicker(r.ticker)}
                  >
                    <TableCell className="font-mono font-semibold">{r.ticker}</TableCell>
                    <TableCell className="font-medium">{r.name}</TableCell>
                    <TableCell className="hidden sm:table-cell">
                      {r.industry && <Badge variant="outline" className="text-xs">{r.industry}</Badge>}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-xs text-muted-foreground max-w-xs truncate">
                      {r.descriptionSnippet}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      {/* Theme browser (hidden during search) */}
      {!isSearching && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Theme list */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">投資主題</h2>
              {themesData && (
                <span className="text-xs text-muted-foreground">({themesData.total})</span>
              )}
            </div>
            {themesLoading ? (
              <div className="grid grid-cols-2 gap-2">
                {[0,1,2,3,4,5].map((i) => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {themesData?.themes.map((t) => (
                  <ThemeCard
                    key={t.themeName}
                    theme={t}
                    selected={selectedTheme === t.themeName}
                    onClick={() => setSelectedTheme(
                      selectedTheme === t.themeName ? null : t.themeName
                    )}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Theme companies */}
          <div className="lg:col-span-2">
            {!selectedTheme ? (
              <div className="h-full flex flex-col items-center justify-center text-center py-20 text-muted-foreground space-y-2">
                <Layers className="h-8 w-8 opacity-30" />
                <p className="text-sm">選擇左側主題查看相關公司</p>
              </div>
            ) : (
              <div className="rounded-xl border overflow-hidden">
                <div className="px-4 py-3 bg-muted/30 border-b flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-sm">{selectedTheme}</p>
                    {themeCompanies && (
                      <p className="text-xs text-muted-foreground">{themeCompanies.total} 家公司</p>
                    )}
                  </div>
                  <Link2 className="h-4 w-4 text-muted-foreground" />
                </div>

                {themeLoading ? (
                  <div className="p-4 space-y-2">
                    {[0,1,2,3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
                  </div>
                ) : (
                  <div className="max-h-[520px] overflow-y-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="w-20">代號</TableHead>
                          <TableHead>名稱</TableHead>
                          <TableHead className="hidden sm:table-cell">產業</TableHead>
                          <TableHead className="w-10"></TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {themeCompanies?.companies.map((c) => (
                          <TableRow
                            key={c.ticker}
                            className="cursor-pointer hover:bg-muted/40"
                            onClick={() => setSelectedTicker(c.ticker)}
                          >
                            <TableCell className="font-mono font-semibold">{c.ticker}</TableCell>
                            <TableCell className="font-medium">{c.name}</TableCell>
                            <TableCell className="hidden sm:table-cell">
                              {c.industry && (
                                <Badge variant="outline" className="text-xs">{c.industry}</Badge>
                              )}
                            </TableCell>
                            <TableCell>
                              <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Company detail sheet */}
      <CompanySheet
        ticker={selectedTicker}
        open={!!selectedTicker}
        onClose={() => setSelectedTicker(null)}
      />
    </div>
  );
}
