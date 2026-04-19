"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ErrorBoundaryProps {
  error: Error & { digest?: string };
  reset: () => void;
  title?: string;
  description?: string;
}

export function ErrorFallback({
  error,
  reset,
  title = "發生錯誤",
  description = "頁面載入時發生未預期的錯誤，請稍後再試。",
}: ErrorBoundaryProps) {
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    console.error("[ErrorBoundary]", error);
  }, [error]);

  return (
    <div className="flex items-center justify-center min-h-[50vh] px-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-red-500">
            <AlertTriangle className="h-5 w-5" />
            {title}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">{description}</p>

          <Button onClick={reset} variant="outline" size="sm">
            <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
            重試
          </Button>

          {/* Collapsible error details */}
          <div className="pt-2 border-t">
            <button
              type="button"
              onClick={() => setShowDetails((prev) => !prev)}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showDetails ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
              錯誤詳情
            </button>
            {showDetails && (
              <pre className="mt-2 text-xs bg-muted rounded-md p-3 overflow-x-auto whitespace-pre-wrap break-all max-h-40">
                {error.message}
                {error.digest && `\n\nDigest: ${error.digest}`}
              </pre>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <ErrorFallback error={error} reset={reset} />;
}
