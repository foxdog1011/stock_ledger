/**
 * Shared loading / error / empty state components.
 * Every data-fetching page renders exactly one of these three states.
 */

// ── Loading ───────────────────────────────────────────────────────────────────

export function LoadingState() {
  return (
    <div className="flex items-center justify-center gap-3 py-24 text-slate-400">
      <div className="h-6 w-6 animate-spin rounded-full border-[3px] border-slate-200 border-t-indigo-600" />
      <span className="text-sm">Loading…</span>
    </div>
  );
}

// ── Error ─────────────────────────────────────────────────────────────────────

interface ErrorStateProps {
  error?: Error | { message?: string } | string | null;
}

export function ErrorState({ error }: ErrorStateProps) {
  const message =
    typeof error === "string"
      ? error
      : (error as { message?: string } | null)?.message ?? "Something went wrong";

  const isNetwork =
    message.toLowerCase().includes("failed to fetch") ||
    message.toLowerCase().includes("network") ||
    message.includes("ECONNREFUSED");

  return (
    <div className="card border-red-200 bg-red-50 p-8 text-center">
      <p className="font-semibold text-red-700">
        {isNetwork ? "Cannot reach the API server" : "Something went wrong"}
      </p>
      <p className="mt-1 text-sm text-red-500">{message}</p>
      {isNetwork && (
        <p className="mt-3 text-xs text-red-400">
          Make sure the API is running and{" "}
          <code className="rounded bg-red-100 px-1 py-0.5">API_URL</code> is
          correctly configured.
        </p>
      )}
    </div>
  );
}

// ── Empty ─────────────────────────────────────────────────────────────────────

interface EmptyStateProps {
  message?: string;
  hint?: string;
}

export function EmptyState({
  message = "No data found",
  hint,
}: EmptyStateProps) {
  return (
    <div className="card py-20 text-center">
      <p className="text-3xl text-slate-300">—</p>
      <p className="mt-3 text-sm font-medium text-slate-400">{message}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

// ── Skeleton row ──────────────────────────────────────────────────────────────

export function SkeletonRow({ cols = 6 }: { cols?: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="h-4 rounded bg-slate-100 animate-pulse" />
        </td>
      ))}
    </tr>
  );
}
