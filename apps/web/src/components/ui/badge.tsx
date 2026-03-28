import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:     "border-transparent bg-primary/20 text-primary hover:bg-primary/30",
        secondary:   "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive: "border-transparent bg-destructive/20 text-tv-down hover:bg-destructive/30",
        outline:     "border-border/60 text-muted-foreground",
        success:     "border-transparent bg-tv-up/15 text-tv-up",
        warning:     "border-transparent bg-yellow-500/15 text-yellow-400",
        up:          "border-transparent bg-tv-up/15 text-tv-up",
        down:        "border-transparent bg-tv-down/15 text-tv-down",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "up" | "down";
}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
