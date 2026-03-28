import { cn } from "@/lib/utils";

interface StatCardProps {
  title: string;
  value: string;
  sub?: string;
  accent?: "default" | "up" | "down" | "blue";
  animate?: boolean;
}

const accentMap = {
  default: "text-foreground",
  up:      "text-tv-up",
  down:    "text-tv-down",
  blue:    "text-tv-blue",
} as const;

export function StatCard({ title, value, sub, accent = "default", animate = false }: StatCardProps) {
  return (
    <div className={cn(
      "rounded-lg border border-border/60 bg-card px-4 py-3",
      "hover:border-border transition-colors duration-150",
      "hover:bg-secondary/30",
    )}>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider truncate">
        {title}
      </p>
      <p className={cn(
        "mt-1 text-xl font-bold font-mono tabular-nums leading-tight",
        accentMap[accent],
        animate && "animate-number-up",
      )}>
        {value}
      </p>
      {sub && (
        <p className="mt-0.5 text-xs text-muted-foreground truncate">{sub}</p>
      )}
    </div>
  );
}
