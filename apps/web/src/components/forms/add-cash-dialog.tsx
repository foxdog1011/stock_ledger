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
  amount: z.coerce.number().refine((v) => v !== 0, "Amount cannot be 0"),
  note: z.string().optional(),
});

type FormData = z.infer<typeof schema>;

export function AddCashDialog({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
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
    try {
      await mutation.mutateAsync(data);
      toast.success(
        `${data.amount >= 0 ? "Deposited" : "Withdrew"} ${Math.abs(data.amount).toFixed(2)}`,
      );
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
          <div className="space-y-1">
            <Label>Date</Label>
            <Input type="date" {...register("date")} />
            {errors.date && <p className="text-xs text-destructive">{errors.date.message}</p>}
          </div>
          <div className="space-y-1">
            <Label>Amount (negative = withdrawal)</Label>
            <Input
              type="number"
              step="0.01"
              placeholder="e.g. 10000 or -5000"
              {...register("amount")}
            />
            {errors.amount && <p className="text-xs text-destructive">{errors.amount.message}</p>}
          </div>
          <div className="space-y-1">
            <Label>Note (optional)</Label>
            <Input placeholder="e.g. Initial deposit" {...register("note")} />
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
