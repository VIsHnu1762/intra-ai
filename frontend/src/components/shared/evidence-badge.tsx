"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, ShieldAlert, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentId } from "@/types/intra-ai";

export interface EvidenceBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  competency: string;
  score?: number;
  level?: "foundational" | "proficient" | "advanced" | "expert";
  isContradiction?: boolean;
  sourceAgent?: AgentId;
  size?: "sm" | "default" | "lg";
}

export function EvidenceBadge({
  competency,
  score,
  level,
  isContradiction = false,
  sourceAgent,
  size = "default",
  className,
  ...props
}: EvidenceBadgeProps) {
  const displayCompetency = competency.replace(/_/g, " ");

  if (isContradiction) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full font-medium border bg-red-950/80 border-red-500/50 text-red-300 select-none",
          size === "sm" ? "px-2 py-0.5 text-[10px]" : "px-3 py-1 text-xs",
          className
        )}
        title="Contradiction flagged in candidate statement"
        {...props}
      >
        <ShieldAlert className="h-3 w-3 text-red-400 shrink-0" />
        <span className="capitalize">{displayCompetency}</span>
        <span className="rounded bg-red-500/20 px-1 py-0.2 text-[9px] font-bold text-red-200">
          Contradiction
        </span>
      </span>
    );
  }

  const agentBorder =
    sourceAgent === "alex"
      ? "border-cyan-500/40 bg-cyan-950/40 text-cyan-200"
      : sourceAgent === "jordan"
      ? "border-purple-500/40 bg-purple-950/40 text-purple-200"
      : "border-slate-700 bg-slate-900/80 text-slate-200";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium border select-none transition-colors",
        agentBorder,
        size === "sm" ? "px-2.5 py-0.5 text-[11px]" : "px-3 py-1 text-xs",
        className
      )}
      {...props}
    >
      <CheckCircle2 className="h-3 w-3 shrink-0 opacity-70" />
      <span className="capitalize">{displayCompetency}</span>
      {score !== undefined && (
        <span className="rounded-full bg-white/10 px-1.5 py-0.2 text-[10px] font-semibold tabular-nums text-white">
          {Math.round(score)}
        </span>
      )}
      {level && (
        <span className="text-[10px] uppercase tracking-wider opacity-60">
          • {level}
        </span>
      )}
    </span>
  );
}
