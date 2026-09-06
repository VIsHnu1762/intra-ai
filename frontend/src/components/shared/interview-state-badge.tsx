"use client";

import * as React from "react";
import { Mic, Sparkles, Volume2, ArrowRightLeft, CheckCircle2, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import type { InterviewTurnState, AgentId } from "@/types/intra-ai";

export interface InterviewStateBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  state: InterviewTurnState;
  activeAgent?: AgentId;
  size?: "sm" | "default" | "lg";
}

interface StateConfig {
  label: string;
  dotColor: string;
  borderClass: string;
  icon: typeof Mic;
  ariaAnnouncement: string;
}

const STATE_CONFIGS: Record<InterviewTurnState, StateConfig> = {
  idle: {
    label: "Ready",
    dotColor: "bg-slate-400",
    borderClass: "bg-slate-900/80 border-slate-700 text-slate-300",
    icon: Clock,
    ariaAnnouncement: "Interview is ready.",
  },
  listening: {
    label: "Listening to You",
    dotColor: "bg-emerald-400 animate-pulse",
    borderClass: "bg-emerald-950/70 border-emerald-500/50 text-emerald-300 glow-listening",
    icon: Mic,
    ariaAnnouncement: "AI is listening to your answer.",
  },
  thinking: {
    label: "Analyzing Response",
    dotColor: "bg-amber-400 animate-pulse",
    borderClass: "bg-amber-950/70 border-amber-500/50 text-amber-300 glow-thinking",
    icon: Sparkles,
    ariaAnnouncement: "AI is analyzing your response.",
  },
  speaking: {
    label: "Speaking",
    dotColor: "bg-cyan-400 animate-ping",
    borderClass: "bg-cyan-950/70 border-cyan-500/50 text-cyan-300 glow-alex",
    icon: Volume2,
    ariaAnnouncement: "AI interviewer is speaking.",
  },
  handoff: {
    label: "Agent Handoff",
    dotColor: "bg-purple-400 animate-pulse",
    borderClass: "bg-purple-950/70 border-purple-500/50 text-purple-300 glow-jordan animate-handoff",
    icon: ArrowRightLeft,
    ariaAnnouncement: "Switching interviewers.",
  },
  completed: {
    label: "Interview Concluded",
    dotColor: "bg-emerald-400",
    borderClass: "bg-emerald-950/80 border-emerald-500/60 text-emerald-300",
    icon: CheckCircle2,
    ariaAnnouncement: "Interview has concluded.",
  },
};

export function InterviewStateBadge({
  state,
  activeAgent,
  size = "default",
  className,
  ...props
}: InterviewStateBadgeProps) {
  const config = STATE_CONFIGS[state] ?? STATE_CONFIGS.idle;
  const Icon = config.icon;

  let dynamicLabel = config.label;
  if (state === "speaking" && activeAgent) {
    dynamicLabel = `${activeAgent === "alex" ? "Alex" : "Jordan"} Speaking`;
  }

  return (
    <span
      role="status"
      aria-live="polite"
      className={cn(
        "inline-flex items-center gap-2 rounded-full font-medium border select-none transition-all duration-300",
        config.borderClass,
        size === "sm" && "px-2.5 py-0.5 text-xs",
        size === "default" && "px-3 py-1 text-xs",
        size === "lg" && "px-4 py-1.5 text-sm",
        className
      )}
      {...props}
    >
      <span className={cn("h-2 w-2 rounded-full shrink-0", config.dotColor)} />
      <Icon className="h-3.5 w-3.5 shrink-0 opacity-80" />
      <span className="font-semibold tracking-wide">{dynamicLabel}</span>
      <span className="sr-only">{config.ariaAnnouncement}</span>
    </span>
  );
}
