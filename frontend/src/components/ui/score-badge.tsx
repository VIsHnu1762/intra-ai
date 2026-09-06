import * as React from "react";
import { cn, getScoreBg } from "@/lib/utils";

export interface ScoreBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  score: number;
  showMax?: boolean;
  size?: "sm" | "default" | "lg";
}

function ScoreBadge({
  score,
  showMax = false,
  size = "default",
  className,
  ...props
}: ScoreBadgeProps) {
  const clamped = Math.min(100, Math.max(0, Math.round(score)));

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-full font-semibold tabular-nums",
        getScoreBg(clamped),
        size === "sm" && "h-6 min-w-6 px-1.5 text-xs",
        size === "default" && "h-7 min-w-7 px-2 text-xs",
        size === "lg" && "h-9 min-w-9 px-3 text-sm",
        className
      )}
      {...props}
    >
      {clamped}
      {showMax && <span className="opacity-60">/100</span>}
    </span>
  );
}

export { ScoreBadge };
