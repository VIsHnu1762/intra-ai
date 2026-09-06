"use client";

import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";
import { cn } from "@/lib/utils";

export interface ProgressProps
  extends React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> {
  value?: number;
  showLabel?: boolean;
}

const Progress = React.forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  ProgressProps
>(({ className, value = 0, showLabel = false, ...props }, ref) => {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div className="flex items-center gap-3">
      <ProgressPrimitive.Root
        ref={ref}
        className={cn(
          "relative h-2 w-full overflow-hidden rounded-full bg-border",
          className
        )}
        value={clamped}
        {...props}
      >
        <ProgressPrimitive.Indicator
          className="h-full rounded-full bg-brand transition-all duration-500 ease-out"
          style={{ transform: `translateX(-${100 - clamped}%)` }}
        />
      </ProgressPrimitive.Root>
      {showLabel && (
        <span className="w-9 shrink-0 text-right text-xs font-medium text-text-muted">
          {clamped}%
        </span>
      )}
    </div>
  );
});

Progress.displayName = "Progress";

export { Progress };
