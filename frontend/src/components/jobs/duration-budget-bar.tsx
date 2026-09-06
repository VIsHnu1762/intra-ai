/**
Intra AI — Interview Duration Budget Manager (P3-07).

Visual timeline component calculating cumulative session duration across active rounds
and validating against the 15–60 minute WebRTC / Agora constraints.
 */

import React from "react";
import { Clock, AlertTriangle, AlertCircle, CheckCircle2, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";
import type { InterviewRoundConfig } from "@/types";

export interface DurationBudgetBarProps {
  rounds: InterviewRoundConfig[];
  maxMinutes?: number;
  minMinutes?: number;
  className?: string;
}

const ROUND_TYPE_NAMES: Record<string, string> = {
  introduction: "Intro",
  technical: "Technical",
  behavioral: "Behavioral",
  hr_culture: "Culture/HR",
};

const ROUND_COLORS: Record<string, string> = {
  introduction: "bg-emerald-500",
  technical: "bg-blue-500",
  behavioral: "bg-amber-500",
  hr_culture: "bg-purple-500",
};

export function DurationBudgetBar({
  rounds,
  maxMinutes = 60,
  minMinutes = 15,
  className,
}: DurationBudgetBarProps) {
  const activeRounds = rounds.filter((r) => r.enabled);
  const totalMinutes = activeRounds.reduce((sum, r) => sum + (r.duration_minutes || 0), 0);
  const remainingMinutes = maxMinutes - totalMinutes;
  const isOverBudget = totalMinutes > maxMinutes;
  const isUnderBudget = totalMinutes > 0 && totalMinutes < minMinutes;
  const isOptimal = totalMinutes >= minMinutes && totalMinutes <= maxMinutes;

  return (
    <div className={cn("space-y-2.5 p-4 rounded-xl border bg-card shadow-xs", className)}>
      {/* Header with Metrics */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-brand" />
          <span className="text-xs font-semibold text-text-primary">
            Interview Session Budget
          </span>
          <span className="text-xs text-text-muted">
            ({activeRounds.length} active {activeRounds.length === 1 ? "round" : "rounds"})
          </span>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-xs">
            <span className="text-text-muted">Total: </span>
            <span
              className={cn(
                "font-bold font-mono",
                isOverBudget ? "text-danger" : isUnderBudget ? "text-amber-500" : "text-brand"
              )}
            >
              {totalMinutes} min
            </span>
            <span className="text-text-muted"> / {maxMinutes} min max</span>
          </div>
          {remainingMinutes > 0 && !isOverBudget && (
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-surface border border-border text-text-muted">
              {remainingMinutes} min available
            </span>
          )}
        </div>
      </div>

      {/* Segmented Timeline Bar */}
      <div className="relative h-3 w-full rounded-full bg-surface overflow-hidden border border-border flex">
        {totalMinutes === 0 ? (
          <div className="w-full h-full bg-border/40" />
        ) : (
          activeRounds.map((round, idx) => {
            const widthPct = Math.min((round.duration_minutes / maxMinutes) * 100, 100);
            const colorClass = ROUND_COLORS[round.type] || "bg-brand";

            return (
              <div
                key={idx}
                style={{ width: `${widthPct}%` }}
                className={cn(
                  "h-full relative group transition-all duration-300 border-r border-card last:border-r-0",
                  colorClass
                )}
                title={`${ROUND_TYPE_NAMES[round.type] || round.type}: ${round.duration_minutes} min`}
              />
            );
          })
        )}
      </div>

      {/* Segment Legend */}
      {activeRounds.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 pt-1 text-[11px] text-text-secondary">
          {activeRounds.map((r, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span
                className={cn("h-2 w-2 rounded-full", ROUND_COLORS[r.type] || "bg-brand")}
              />
              <span>
                {ROUND_TYPE_NAMES[r.type] || r.type}: {r.duration_minutes}m
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Validation Status Alerts */}
      {isOverBudget && (
        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-danger/10 border border-danger/30 text-danger text-xs animate-in fade-in">
          <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold">WebRTC Session Limit Exceeded: </span>
            Total duration ({totalMinutes} min) exceeds the 60-minute limit. Agora RTC tokens expire after 60 minutes. Reduce round duration by {totalMinutes - maxMinutes} min to publish.
          </div>
        </div>
      )}

      {isUnderBudget && (
        <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs animate-in fade-in">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-semibold">Sub-optimal Duration: </span>
            Total duration ({totalMinutes} min) is under the 15-minute recommended minimum for candidate evaluation.
          </div>
        </div>
      )}

      {isOptimal && (
        <div className="flex items-center gap-2 text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span>Optimal session budget within Agora 60-minute runtime envelope.</span>
        </div>
      )}
    </div>
  );
}
