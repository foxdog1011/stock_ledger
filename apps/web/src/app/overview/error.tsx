"use client";

import { ErrorFallback } from "../error";

export default function OverviewError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <ErrorFallback
      error={error}
      reset={reset}
      title="總覽載入失敗"
      description="無法載入總覽資料，請檢查網路連線後再試。"
    />
  );
}
