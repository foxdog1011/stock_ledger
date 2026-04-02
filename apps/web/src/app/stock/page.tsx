"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Search, Clock, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { useResearchSearch } from "@/hooks/use-queries";

const RECENT_KEY = "deep_dive_recent";
const MAX_RECENT = 6;

function getRecent(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

export default function StockSearchPage() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<string[]>([]);

  useEffect(() => {
    setRecent(getRecent());
  }, []);

  const { data: searchData, isLoading } = useResearchSearch(query, 10);

  const handleResultClick = useCallback(
    (ticker: string) => {
      const prev = getRecent().filter((t) => t !== ticker);
      const next = [ticker, ...prev].slice(0, MAX_RECENT);
      localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      router.push(`/stock/${ticker}`);
    },
    [router],
  );

  return (
    <div className="min-h-screen bg-zinc-900 text-zinc-100">
      <div className="max-w-2xl mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold tracking-tight mb-2">個股深度研究</h1>
          <p className="text-zinc-400 text-sm">輸入股票代號或公司名稱以開始深度分析</p>
        </div>

        {/* Search input */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-zinc-500 pointer-events-none" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜尋股票代號或公司名稱..."
            className={cn(
              "w-full bg-zinc-800 border border-zinc-700 rounded-xl",
              "pl-10 pr-4 py-3 text-sm text-zinc-100 placeholder:text-zinc-500",
              "focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50",
              "transition-all duration-150",
            )}
            autoFocus
          />
        </div>

        {/* Search results */}
        {query.length >= 2 && (
          <div className="mb-8">
            {isLoading ? (
              <div className="text-center text-zinc-500 py-8 text-sm">搜尋中...</div>
            ) : searchData && searchData.results.length > 0 ? (
              <div className="rounded-xl border border-zinc-700/80 bg-zinc-800/60 divide-y divide-zinc-700/60 overflow-hidden">
                {searchData.results.map((r) => (
                  <button
                    key={r.ticker}
                    onClick={() => handleResultClick(r.ticker)}
                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-zinc-700/50 transition-colors duration-100 text-left"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-xs font-mono font-semibold text-blue-400 bg-blue-950/60 border border-blue-800/50 px-2 py-0.5 rounded flex-shrink-0">
                        {r.ticker}
                      </span>
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-zinc-100 truncate">{r.name}</div>
                        {r.industry && (
                          <div className="text-xs text-zinc-500 truncate">{r.industry}</div>
                        )}
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-zinc-500 flex-shrink-0" />
                  </button>
                ))}
              </div>
            ) : (
              <div className="text-center text-zinc-500 py-8 text-sm">
                找不到符合「{query}」的結果
              </div>
            )}
          </div>
        )}

        {/* Recent searches */}
        {recent.length > 0 && query.length < 2 && (
          <div>
            <div className="flex items-center gap-2 mb-3 text-xs text-zinc-500 uppercase tracking-wider">
              <Clock className="h-3.5 w-3.5" />
              最近查看
            </div>
            <div className="flex flex-wrap gap-2">
              {recent.map((ticker) => (
                <Link
                  key={ticker}
                  href={`/stock/${ticker}`}
                  className={cn(
                    "text-xs font-mono font-semibold px-3 py-1.5 rounded-lg",
                    "bg-zinc-800 border border-zinc-700 text-zinc-300",
                    "hover:bg-zinc-700 hover:text-zinc-100 hover:border-zinc-600",
                    "transition-all duration-100",
                  )}
                >
                  {ticker}
                </Link>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
