"use client";

import { ErrorFallback } from "../error";

export default function PortfolioError({
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
      title="投資組合載入失敗"
      description="無法載入持倉資料，請檢查網路連線後再試。"
    />
  );
}
