"use client";

import { useState } from "react";
import { Plus, DollarSign, ArrowLeftRight, BarChart3 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { AddCashDialog } from "@/components/forms/add-cash-dialog";
import { AddTradeDialog } from "@/components/forms/add-trade-dialog";
import { AddQuoteDialog } from "@/components/forms/add-quote-dialog";

export function Fab() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col-reverse items-end gap-3">
      {/* Main toggle button */}
      <Button
        size="icon"
        className="h-14 w-14 rounded-full shadow-xl"
        onClick={() => setExpanded((v) => !v)}
        aria-label={expanded ? "關閉快速操作" : "開啟快速操作"}
      >
        <Plus
          className={cn(
            "h-6 w-6 transition-transform duration-200",
            expanded ? "rotate-45" : "rotate-0",
          )}
        />
      </Button>

      {/* Speed-dial items */}
      <div
        className={cn(
          "flex flex-col-reverse items-end gap-2 transition-all duration-200",
          expanded
            ? "opacity-100 translate-y-0 pointer-events-auto"
            : "opacity-0 translate-y-4 pointer-events-none",
        )}
      >
        <AddCashDialog>
          <SpeedDialItem icon={<DollarSign className="h-4 w-4" />} label="新增現金" />
        </AddCashDialog>

        <AddTradeDialog>
          <SpeedDialItem icon={<ArrowLeftRight className="h-4 w-4" />} label="新增交易" />
        </AddTradeDialog>

        <AddQuoteDialog>
          <SpeedDialItem icon={<BarChart3 className="h-4 w-4" />} label="新增報價" />
        </AddQuoteDialog>
      </div>
    </div>
  );
}

function SpeedDialItem({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 rounded-full bg-card border shadow-md px-4 py-2 text-sm font-medium transition-all hover:shadow-lg active:scale-95"
    >
      {icon}
      <span className="whitespace-nowrap">{label}</span>
    </button>
  );
}
