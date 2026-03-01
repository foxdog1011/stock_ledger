"use client";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { format, subMonths, subYears, startOfYear } from "date-fns";

export type Range = "1M" | "3M" | "6M" | "YTD" | "1Y" | "ALL";

export interface RangeParams {
  start: string;
  end: string;
  freq: string;
}

// ── freq selection ──────────────────────────────────────────────────────────
// Short windows: daily gives enough granularity without too many points.
// Medium windows: weekly keeps the chart readable.
// Long windows: monthly is sufficient and keeps the series short.
const FREQ_MAP: Record<Range, string> = {
  "1M": "D",
  "3M": "D",
  "6M": "W",
  "YTD": "W",
  "1Y": "ME",
  "ALL": "ME",
};

export function toParams(range: Range): RangeParams {
  const today = new Date();
  const end = format(today, "yyyy-MM-dd");
  let start: string;
  switch (range) {
    case "1M":
      start = format(subMonths(today, 1), "yyyy-MM-dd");
      break;
    case "3M":
      start = format(subMonths(today, 3), "yyyy-MM-dd");
      break;
    case "6M":
      start = format(subMonths(today, 6), "yyyy-MM-dd");
      break;
    case "YTD":
      start = format(startOfYear(today), "yyyy-MM-dd");
      break;
    case "1Y":
      start = format(subYears(today, 1), "yyyy-MM-dd");
      break;
    case "ALL":
      start = "2000-01-01";
      break;
  }
  return { start, end, freq: FREQ_MAP[range] };
}

interface Props {
  value: Range;
  onChange: (range: Range, params: RangeParams) => void;
}

const RANGES: Range[] = ["1M", "3M", "6M", "YTD", "1Y", "ALL"];

export function TimeRangePicker({ value, onChange }: Props) {
  return (
    <div className="flex gap-1 flex-wrap">
      {RANGES.map((r) => (
        <Button
          key={r}
          size="sm"
          variant={value === r ? "default" : "outline"}
          className={cn("h-7 px-2.5 text-xs")}
          onClick={() => onChange(r, toParams(r))}
        >
          {r}
        </Button>
      ))}
    </div>
  );
}
