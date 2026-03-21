"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAddCash } from "@/hooks/use-queries";

const schema = z.object({
  date: z.string().min(1, "Date required"),
  amount: z.coerce.number().positive("Amount must be greater than 0"),
  note: z.string().optional(),
});

type FormData = z.infer<typeof schema>;

export function AddCashDialog({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [txType, setTxType] = useState<"deposit" | "withdrawal">("deposit");
  const mutation = useAddCash();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { date: new Date().toISOString().slice(0, 10) },
  });

  const onSubmit = async (data: FormData) => {
    const amount = txType === "withdrawal" ? -Math.abs(data.amount) : Math.abs(data.amount);
    try {
      await mutation.mutateAsync({ ...data, amount });
      toast.success(`${txType === "deposit" ? "Deposited" : "Withdrew"} ${data.amount.toFixed(2)}`);
      reset({ date: new Date().toISOString().slice(0, 10) });
      setOpen(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{children}</DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Add Cash Entry</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 pt-2">
          {/* Deposit / Withdrawal toggle */}
          <div className="grid grid-cols-2 gap-1 rounded-md border p-1">
            <button
              type="button"
              onClick={() => setTxType("deposit")}
              className={`rounded py-1.5 text-sm font-medium transition-colors ${
                txType === "deposit"
                  ? "bg-emerald-600 text-white"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Deposit
            </button>
            <button
              type="button"
              onClick={() => setTxType("withdrawal")}
              className={`rounded py-1.5 text-sm font-medium transition-colors ${
                txType === "withdrawal"
                  ? "bg-red-600 text-white"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Withdrawal
            </button>
          </div>

          <div className="space-y-1">
            <Label>Date</Label>
            <Input type="date" {...register("date")} />
            {errors.date && <p className="text-xs text-destructive">{errors.date.message}</p>}
          </div>
          <div className="space-y-1">
            <Label>Amount</Label>
            <Input
              type="number"
              step="0.01"
              min="0"
              placeholder="e.g. 10000"
              {...register("amount")}
            />
            {errors.amount && <p className="text-xs text-destructive">{errors.amount.message}</p>}
          </div>
          <div className="space-y-1">
            <Label>Note (optional)</Label>
            <Input placeholder="e.g. Monthly salary" {...register("note")} />
          </div>
          <Button
            type="submit"
            className={`w-full ${txType === "withdrawal" ? "bg-red-600 hover:bg-red-700" : ""}`}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Saving…" : txType === "deposit" ? "Save Deposit" : "Save Withdrawal"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
