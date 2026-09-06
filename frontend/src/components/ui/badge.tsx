import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors select-none",
  {
    variants: {
      variant: {
        default: "bg-brand-light text-brand",
        success: "bg-success-light text-success",
        warning: "bg-warning-light text-warning",
        error: "bg-error-light text-error",
        outline: "border border-border text-text-muted bg-transparent",
        muted: "bg-border text-text-muted",
        alex: "bg-agent-alex-surface text-agent-alex-primary border border-agent-alex-border/60",
        jordan: "bg-agent-jordan-surface text-agent-jordan-primary border border-agent-jordan-border/60",
        listening: "bg-emerald-950/80 text-emerald-400 border border-emerald-500/40",
        thinking: "bg-amber-950/80 text-amber-400 border border-amber-500/40",
        speaking: "bg-cyan-950/80 text-cyan-400 border border-cyan-500/40",
        handoff: "bg-purple-950/80 text-purple-400 border border-purple-500/40",
        obsidian: "bg-obsidian-800 text-obsidian-text border border-obsidian-border",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
