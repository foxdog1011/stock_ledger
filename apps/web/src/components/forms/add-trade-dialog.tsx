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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAddTrade } from "@/hooks/use-queries";

const schema = z.object({
  date: z.string().min(1, "Date required"),
  symbol: z.string().min(1, "Symbol required").toUpperCase(),
  side: z.enum(["buy", "sell"]),
  qty: z.coerce.number().positive("Must be positive"),
  price: z.coerce.number().positive("Must be positive"),
  commission: z.coerce.number().min(0).default(0),
  tax: z.coerce.number().min(0).default(0),
  note: z.string().optional(),
});

type FormData = z.infer<typeof schema>;

export function AddTradeDialog({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const mutation = useAddTrade();

  const {
    register,
    handleSubmit,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      date: new Date().toISOString().slice(0, 10),
      side: "buy",
      commission: 0,
      tax: 0,
    },
  });

  const onSubmit = async (data: FormData) => {
    try {
      await mutation.mutateAsync(data);
      toast.success(`${data.side.toUpperCase()} ${data.qty} ${data.symbol} @ ${data.price}`);
      toast.info(`Fetching latest price for ${data.symbol}…`, { duration: 3000 });
      reset({ date: new Date().toISOString().slice(0, 10), side: "buy", commission: 0, tax: 0 });
      setSide("buy");
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
          <DialogTitle>Add Trade</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 pt-2">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Date</Label>
              <Input type="date" {...register("date")} />
              {errors.date && <p className="text-xs text-destructive">{errors.date.message}</p>}
            </div>
            <div className="space-y-1">
              <Label>Side</Label>
              <Select
                value={side}
                onValueChange={(v: "buy" | "sell") => {
                  setSide(v);
                  setValue("side", v);
                }}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="buy">Buy</SelectItem>
                  <SelectItem value="sell">Sell</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label>Symbol</Label>
            <Input placeholder="e.g. AAPL" {...register("symbol")} className="uppercase" />
            {errors.symbol && <p className="text-xs text-destructive">{errors.symbol.message}</p>}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Qty (shares)</Label>
              <Input type="number" step="0.0001" placeholder="100" {...register("qty")} />
              {errors.qty && <p className="text-xs text-destructive">{errors.qty.message}</p>}
            </div>
            <div className="space-y-1">
              <Label>Price</Label>
              <Input type="number" step="0.0001" placeholder="150.00" {...register("price")} />
              {errors.price && <p className="text-xs text-destructive">{errors.price.message}</p>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Commission</Label>
              <Input type="number" step="0.01" placeholder="0" {...register("commission")} />
            </div>
            <div className="space-y-1">
              <Label>Tax</Label>
              <Input type="number" step="0.01" placeholder="0" {...register("tax")} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Note (optional)</Label>
            <Input {...register("note")} />
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Saving…" : "Save Trade"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
