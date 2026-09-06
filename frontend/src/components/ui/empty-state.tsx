import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface EmptyStateProps extends React.HTMLAttributes<HTMLDivElement> {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  variant?: "light" | "obsidian";
}

function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  variant = "light",
  className,
  ...props
}: EmptyStateProps) {
  const isObsidian = variant === "obsidian";

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-16 px-6 text-center select-none",
        isObsidian ? "text-obsidian-text" : "text-text-primary",
        className
      )}
      {...props}
    >
      {Icon && (
        <div
          className={cn(
            "flex h-14 w-14 items-center justify-center rounded-2xl border",
            isObsidian
              ? "bg-white/5 border-white/10 text-cyan-400"
              : "bg-border/60 border-border text-text-muted"
          )}
        >
          <Icon className="h-7 w-7" strokeWidth={1.5} />
        </div>
      )}
      <div className="flex flex-col gap-1 max-w-sm">
        <p
          className={cn(
            "text-base font-semibold",
            isObsidian ? "text-white" : "text-text-primary"
          )}
        >
          {title}
        </p>
        {description && (
          <p
            className={cn(
              "text-xs leading-relaxed",
              isObsidian ? "text-slate-400" : "text-text-muted"
            )}
          >
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export { EmptyState };
