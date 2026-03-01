/**
 * Display formatting helpers
 */

export function fmt(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function fmtMoney(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function fmtPct(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(decimals)}%`;
}

export function fmtDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  return dateStr.slice(0, 10);
}

export function pnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) return "text-muted-foreground";
  return value > 0 ? "text-emerald-600" : "text-red-500";
}

// Keep old exports for any existing usage
export const formatMoney = fmtMoney;
export const formatPct = fmtPct;
export const formatDate = fmtDate;
