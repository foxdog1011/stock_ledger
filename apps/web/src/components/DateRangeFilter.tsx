"use client";

interface DateRangeFilterProps {
  start: string;
  end: string;
  onStartChange: (v: string) => void;
  onEndChange: (v: string) => void;
  /** If true, render a "Generate" submit button instead of auto-filtering. */
  onSubmit?: () => void;
  submitLabel?: string;
}

export function DateRangeFilter({
  start,
  end,
  onStartChange,
  onEndChange,
  onSubmit,
  submitLabel = "Generate",
}: DateRangeFilterProps) {
  const clear = () => {
    onStartChange("");
    onEndChange("");
  };

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">
          Start date
        </label>
        <input
          type="date"
          value={start}
          onChange={(e) => onStartChange(e.target.value)}
          className="input w-40"
        />
      </div>

      <div>
        <label className="block text-xs font-medium text-slate-500 mb-1">
          End date
        </label>
        <input
          type="date"
          value={end}
          onChange={(e) => onEndChange(e.target.value)}
          className="input w-40"
        />
      </div>

      {onSubmit && (
        <button onClick={onSubmit} className="btn-primary">
          {submitLabel}
        </button>
      )}

      {(start || end) && (
        <button onClick={clear} className="btn-ghost text-xs">
          Clear
        </button>
      )}
    </div>
  );
}
