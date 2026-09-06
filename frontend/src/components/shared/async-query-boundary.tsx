"use client";

/**
 * Intra AI — Async Query Boundary
 *
 * Declarative component that binds TanStack Query state (isLoading, isError, isEmpty)
 * with Phase 1 design system loading skeletons, empty states, and ErrorBoundaries.
 */

import * as React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { CardSkeleton, PageLoading, TableRowSkeleton } from "@/components/ui/loading";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { ErrorBoundary } from "./error-boundary";
import { formatApiErrorMessage } from "@/lib/api/error-handler";
import { cn } from "@/lib/utils";

export interface AsyncQueryBoundaryProps {
  isLoading: boolean;
  isError?: boolean;
  error?: unknown;
  isEmpty?: boolean;
  onRetry?: () => void;
  skeletonType?: "card" | "table" | "page";
  skeletonCount?: number;
  loadingFallback?: React.ReactNode;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: React.ReactNode;
  emptyFallback?: React.ReactNode;
  variant?: "light" | "obsidian";
  className?: string;
  children: React.ReactNode;
}

export function AsyncQueryBoundary({
  isLoading,
  isError = false,
  error,
  isEmpty = false,
  onRetry,
  skeletonType = "card",
  skeletonCount = 3,
  loadingFallback,
  emptyTitle = "No data available",
  emptyDescription = "There are no records to display at this time.",
  emptyAction,
  emptyFallback,
  variant = "light",
  className,
  children,
}: AsyncQueryBoundaryProps) {
  const isObsidian = variant === "obsidian";

  // 1. Loading State
  if (isLoading) {
    if (loadingFallback) {
      return <>{loadingFallback}</>;
    }

    if (skeletonType === "page") {
      return <PageLoading variant={isObsidian ? "alex" : "brand"} />;
    }

    if (skeletonType === "table") {
      return (
        <div className={cn("w-full overflow-hidden rounded-lg border border-border", className)}>
          <table className="w-full text-sm">
            <tbody>
              {Array.from({ length: skeletonCount }).map((_, idx) => (
                <TableRowSkeleton key={idx} />
              ))}
            </tbody>
          </table>
        </div>
      );
    }

    return (
      <div className={cn("grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4", className)}>
        {Array.from({ length: skeletonCount }).map((_, idx) => (
          <CardSkeleton key={idx} variant={variant} />
        ))}
      </div>
    );
  }

  // 2. Error State
  if (isError) {
    const errorMsg = formatApiErrorMessage(error, "Failed to load data.");

    return (
      <div
        className={cn(
          "flex flex-col items-center justify-center p-8 text-center rounded-xl border my-4",
          isObsidian
            ? "border-red-500/20 bg-red-950/20 text-red-300"
            : "border-error/20 bg-error/5 text-text-primary",
          className
        )}
      >
        <div
          className={cn(
            "flex h-12 w-12 items-center justify-center rounded-xl mb-3",
            isObsidian ? "bg-red-500/10 text-red-400" : "bg-error/10 text-error"
          )}
        >
          <AlertCircle className="h-6 w-6" />
        </div>
        <p className="text-sm font-semibold mb-1">Unable to Load Data</p>
        <p className="text-xs text-text-muted max-w-md mb-4">{errorMsg}</p>
        {onRetry && (
          <Button
            size="sm"
            variant="secondary"
            onClick={onRetry}
            className="flex items-center gap-1.5 text-xs"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Try Again
          </Button>
        )}
      </div>
    );
  }

  // 3. Empty State
  if (isEmpty) {
    if (emptyFallback) {
      return <>{emptyFallback}</>;
    }

    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        action={emptyAction}
        variant={variant}
        className={className}
      />
    );
  }

  // 4. Success State (wrapped in ErrorBoundary for runtime protection)
  return (
    <ErrorBoundary>
      <div className={className}>{children}</div>
    </ErrorBoundary>
  );
}
