interface StatCardProps {
  title: string;
  value: string;
  sub?: string;
  accent?: "default" | "green" | "red" | "indigo";
}

const accentMap = {
  default: "text-slate-900",
  green:   "text-emerald-600",
  red:     "text-red-600",
  indigo:  "text-indigo-600",
} as const;

export function StatCard({ title, value, sub, accent = "default" }: StatCardProps) {
  return (
    <div className="card p-5">
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        {title}
      </p>
      <p className={`mt-1.5 text-2xl font-bold font-mono ${accentMap[accent]}`}>
        {value}
      </p>
      {sub && <p className="mt-1 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}
