import * as React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Spinner ──────────────────────────────────────────────────────────────────

export interface SpinnerProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "sm" | "default" | "lg";
  variant?: "brand" | "alex" | "jordan" | "white";
}

function Spinner({
  size = "default",
  variant = "brand",
  className,
  ...props
}: SpinnerProps) {
  const colorMap = {
    brand: "text-brand",
    alex: "text-agent-alex-primary",
    jordan: "text-agent-jordan-primary",
    white: "text-white",
  };

  return (
    <div
      className={cn("flex items-center justify-center", className)}
      {...props}
    >
      <Loader2
        className={cn(
          "animate-spin",
          colorMap[variant],
          size === "sm" && "h-4 w-4",
          size === "default" && "h-6 w-6",
          size === "lg" && "h-8 w-8"
        )}
      />
    </div>
  );
}

// ─── Page Loading ─────────────────────────────────────────────────────────────

function PageLoading({ variant = "brand" }: { variant?: SpinnerProps["variant"] }) {
  return (
    <div className="flex h-64 w-full items-center justify-center">
      <Spinner size="lg" variant={variant} />
    </div>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "light" | "obsidian";
}

function Skeleton({
  className,
  variant = "light",
  ...props
}: SkeletonProps) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md",
        variant === "obsidian" ? "bg-white/10" : "bg-border",
        className
      )}
      {...props}
    />
  );
}

// ─── Card Skeleton ────────────────────────────────────────────────────────────

function CardSkeleton({ variant = "light" }: { variant?: "light" | "obsidian" }) {
  const isObsidian = variant === "obsidian";
  return (
    <div
      className={cn(
        "rounded-xl p-5 flex flex-col gap-3",
        isObsidian
          ? "bg-obsidian-900 border border-obsidian-border"
          : "bg-surface border border-border"
      )}
    >
      <div className="flex items-center gap-3">
        <Skeleton variant={variant} className="h-10 w-10 rounded-full" />
        <div className="flex flex-col gap-2 flex-1">
          <Skeleton variant={variant} className="h-4 w-2/3" />
          <Skeleton variant={variant} className="h-3 w-1/3" />
        </div>
      </div>
      <Skeleton variant={variant} className="h-3 w-full" />
      <Skeleton variant={variant} className="h-3 w-4/5" />
      <div className="flex gap-2 pt-1">
        <Skeleton variant={variant} className="h-6 w-16 rounded-full" />
        <Skeleton variant={variant} className="h-6 w-16 rounded-full" />
      </div>
    </div>
  );
}

// ─── Transcript Row Skeleton ──────────────────────────────────────────────────

function SkeletonTranscriptRow() {
  return (
    <div className="space-y-2 p-3 rounded-lg bg-white/5 border border-white/5">
      <div className="flex items-center gap-2">
        <Skeleton variant="obsidian" className="h-3 w-14 rounded-full" />
        <Skeleton variant="obsidian" className="h-2.5 w-10 rounded-full" />
      </div>
      <Skeleton variant="obsidian" className="h-3.5 w-full" />
      <Skeleton variant="obsidian" className="h-3.5 w-4/5" />
    </div>
  );
}

// ─── Kanban Column Skeleton ───────────────────────────────────────────────────

function SkeletonKanbanColumn() {
  return (
    <div className="flex flex-col gap-3 p-3 bg-slate-100/80 rounded-xl min-w-[280px]">
      <div className="flex items-center justify-between pb-2 border-b border-border">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-5 w-6 rounded-full" />
      </div>
      <CardSkeleton />
      <CardSkeleton />
    </div>
  );
}

// ─── Table Row Skeleton ───────────────────────────────────────────────────────

function TableRowSkeleton({ cols = 5 }: { cols?: number }) {
  return (
    <tr className="border-b border-border">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full max-w-[120px]" />
        </td>
      ))}
    </tr>
  );
}

// ─── Legacy alias (for backward compatibility) ────────────────────────────────

/** @deprecated Use Spinner instead */
function LoadingSpinner({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center py-16", className)}>
      <Loader2 className="h-6 w-6 animate-spin text-brand" />
    </div>
  );
}

export {
  Spinner,
  PageLoading,
  Skeleton,
  CardSkeleton,
  SkeletonTranscriptRow,
  SkeletonKanbanColumn,
  TableRowSkeleton,
  LoadingSpinner,
};
