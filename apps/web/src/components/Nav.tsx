"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { TrendingUp, ChevronDown } from "lucide-react";
import { useState, useRef, useEffect } from "react";

const primaryLinks = [
  { href: "/overview",    label: "總覽" },
  { href: "/portfolio",   label: "投資組合" },
  { href: "/rolling",     label: "滾動分析" },
  { href: "/monitor",     label: "監控" },
  { href: "/chip",        label: "籌碼" },
  { href: "/positions",   label: "持倉" },
  { href: "/research",    label: "研究" },
  { href: "/chat",        label: "J.A.R.V.I.S." },
] as const;

const secondaryLinks = [
  { href: "/allocation",  label: "資產配置" },
  { href: "/revenue",     label: "月營收" },
  { href: "/screener",    label: "選股篩選" },
  { href: "/ledger",      label: "帳務紀錄" },
  { href: "/universe",    label: "股票池 / 觀察清單" },
  { href: "/catalyst",    label: "催化劑" },
  { href: "/offsetting",  label: "對沖試算" },
  { href: "/digest",      label: "日報" },
  { href: "/operations",  label: "操作中心" },
] as const;

export function Nav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  const anySecondaryActive = secondaryLinks.some((l) => isActive(l.href));

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <header className="sticky top-0 z-30 border-b border-border/60 bg-background/90 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-12 items-center gap-4">
        {/* Logo */}
        <Link
          href="/overview"
          className="flex-shrink-0 flex items-center gap-1.5 group"
        >
          <div className="p-1 rounded bg-primary/10 group-hover:bg-primary/20 transition-colors duration-150">
            <TrendingUp className="h-4 w-4 text-tv-blue" />
          </div>
          <span className="hidden sm:inline text-sm font-semibold tracking-tight">
            Stock Ledger
          </span>
        </Link>

        {/* Divider */}
        <div className="h-5 w-px bg-border hidden sm:block" />

        {/* Primary nav */}
        <nav className="flex items-center gap-0.5 overflow-x-auto flex-1 min-w-0 scrollbar-none">
          {primaryLinks.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "relative px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 whitespace-nowrap",
                isActive(href)
                  ? "text-foreground bg-secondary"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/50",
              )}
            >
              {label}
              {isActive(href) && (
                <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-3 h-0.5 bg-tv-blue rounded-full" />
              )}
            </Link>
          ))}
        </nav>

        {/* More dropdown */}
        <div className="relative flex-shrink-0" ref={moreRef}>
          <button
            onClick={() => setMoreOpen((v) => !v)}
            className={cn(
              "flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 whitespace-nowrap",
              anySecondaryActive || moreOpen
                ? "text-foreground bg-secondary"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/50",
            )}
          >
            更多
            <ChevronDown
              className={cn(
                "h-3 w-3 transition-transform duration-200",
                moreOpen && "rotate-180",
              )}
            />
          </button>

          {moreOpen && (
            <div className="absolute right-0 top-full mt-1.5 w-44 rounded-lg border border-border/80 bg-popover shadow-xl shadow-black/40 z-50 py-1 animate-scale-in">
              {secondaryLinks.map(({ href, label }) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setMoreOpen(false)}
                  className={cn(
                    "flex items-center px-3 py-2 text-xs transition-colors duration-100",
                    isActive(href)
                      ? "text-foreground bg-secondary font-medium"
                      : "text-muted-foreground hover:text-foreground hover:bg-secondary/60",
                  )}
                >
                  {label}
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
