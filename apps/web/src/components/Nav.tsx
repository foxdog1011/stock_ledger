"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { TrendingUp, ChevronDown } from "lucide-react";
import { useState, useRef, useEffect } from "react";

const primaryLinks = [
  { href: "/overview",    label: "Overview" },
  { href: "/portfolio",   label: "Portfolio" },
  { href: "/universe",    label: "Universe" },
  { href: "/watchlist",   label: "Watchlist" },
  { href: "/catalyst",    label: "Catalyst" },
  { href: "/offsetting",  label: "Offsetting" },
] as const;

const secondaryLinks = [
  { href: "/cash",        label: "Cash" },
  { href: "/trades",      label: "Trades" },
  { href: "/positions",   label: "Positions" },
  { href: "/quotes",      label: "Quotes" },
  { href: "/digest",      label: "Digest" },
  { href: "/import",      label: "Import" },
  { href: "/settings",    label: "Settings" },
] as const;

export function Nav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const moreRef = useRef<HTMLDivElement>(null);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(href + "/");

  const anySecondaryActive = secondaryLinks.some((l) => isActive(l.href));

  // Close dropdown when clicking outside
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
    <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex h-14 items-center gap-6">
        <Link href="/overview" className="flex-shrink-0 flex items-center gap-2 font-semibold">
          <TrendingUp className="h-5 w-5 text-primary" />
          <span className="hidden sm:inline">Stock Ledger</span>
        </Link>
        <nav className="flex items-center gap-1 overflow-x-auto flex-1">
          {primaryLinks.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap",
                isActive(href)
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              {label}
            </Link>
          ))}

          {/* More dropdown */}
          <div className="relative" ref={moreRef}>
            <button
              onClick={() => setMoreOpen((v) => !v)}
              className={cn(
                "flex items-center gap-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap",
                anySecondaryActive || moreOpen
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              More
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", moreOpen && "rotate-180")} />
            </button>

            {moreOpen && (
              <div className="absolute left-0 top-full mt-1 w-40 rounded-md border bg-background shadow-md z-50 py-1">
                {secondaryLinks.map(({ href, label }) => (
                  <Link
                    key={href}
                    href={href}
                    onClick={() => setMoreOpen(false)}
                    className={cn(
                      "block px-4 py-2 text-sm transition-colors",
                      isActive(href)
                        ? "bg-secondary text-secondary-foreground font-medium"
                        : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                    )}
                  >
                    {label}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </nav>
      </div>
    </header>
  );
}
