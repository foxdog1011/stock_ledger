"use client";

import { ErrorFallback } from "../error";

export default function TrumpPutError({
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
      title="Trump Put 載入失敗"
      description="無法載入 S&P/10Y/VIX 資料，請稍後再試。"
    />
  );
}
