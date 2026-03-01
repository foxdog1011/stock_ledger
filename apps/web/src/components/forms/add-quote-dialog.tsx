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
import { useAddQuote } from "@/hooks/use-queries";

const schema = z.object({
  symbol: z.string().min(1, "Symbol required"),
  date: z.string().min(1, "Date required"),
  close: z.coerce.number().positive("Must be positive"),
});

type FormData = z.infer<typeof schema>;

export function AddQuoteDialog({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const mutation = useAddQuote();

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
    try {
      await mutation.mutateAsync({ ...data, symbol: data.symbol.toUpperCase() });
      toast.success(`Quote saved: ${data.symbol.toUpperCase()} @ ${data.close}`);
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
          <DialogTitle>Add Manual Quote</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 pt-2">
          <div className="space-y-1">
            <Label>Symbol</Label>
            <Input placeholder="e.g. AAPL" {...register("symbol")} className="uppercase" />
            {errors.symbol && <p className="text-xs text-destructive">{errors.symbol.message}</p>}
          </div>
          <div className="space-y-1">
            <Label>Date</Label>
            <Input type="date" {...register("date")} />
            {errors.date && <p className="text-xs text-destructive">{errors.date.message}</p>}
          </div>
          <div className="space-y-1">
            <Label>Close Price</Label>
            <Input type="number" step="0.0001" placeholder="150.00" {...register("close")} />
            {errors.close && <p className="text-xs text-destructive">{errors.close.message}</p>}
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save Quote"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
