/**
Intra AI — Agent Round Mapper Component (P3-06).

Provides interactive persona selection cards for Alex (Technical Manager)
and Jordan (Product Lead) for assigning interviewers to rounds.
 */

import React from "react";
import { Check, Volume2, Sparkles, Cpu, Compass } from "lucide-react";
import { cn } from "@/lib/utils";
import { useInterviewAgents } from "@/hooks/queries/useInterviewTemplates";

export interface AgentPersona {
  id: string;
  name: string;
  role: string;
  voiceDescription: string;
  styleDescription: string;
  recommendedRounds: string[];
  primaryCompetencies: string[];
  theme: {
    borderActive: string;
    bgActive: string;
    badgeBg: string;
    badgeText: string;
    iconColor: string;
  };
}

export const AGENT_PERSONAS: Record<string, AgentPersona> = {
  alex: {
    id: "alex",
    name: "Alex",
    role: "Senior Technical Manager",
    voiceDescription: "Warm, authoritative, precise",
    styleDescription: "Deep technical probing, architectural trade-offs, and algorithmic reasoning.",
    recommendedRounds: ["technical", "introduction"],
    primaryCompetencies: ["System Design", "Architecture", "Coding", "Scalability", "Debugging"],
    theme: {
      borderActive: "border-blue-500 ring-2 ring-blue-500/20",
      bgActive: "bg-blue-500/5 dark:bg-blue-950/20",
      badgeBg: "bg-blue-500/10 border-blue-500/30",
      badgeText: "text-blue-600 dark:text-blue-400",
      iconColor: "text-blue-500",
    },
  },
  jordan: {
    id: "jordan",
    name: "Jordan",
    role: "Product Lead",
    voiceDescription: "Collaborative, inquisitive, structured",
    styleDescription: "Strategic vision, customer empathy, prioritization, and metric-driven execution.",
    recommendedRounds: ["behavioral", "hr_culture", "introduction"],
    primaryCompetencies: ["Product Sense", "Trade-Off Analysis", "Customer Impact", "Prioritization"],
    theme: {
      borderActive: "border-amber-500 ring-2 ring-amber-500/20",
      bgActive: "bg-amber-500/5 dark:bg-amber-950/20",
      badgeBg: "bg-amber-500/10 border-amber-500/30",
      badgeText: "text-amber-600 dark:text-amber-400",
      iconColor: "text-amber-500",
    },
  },
};

export function useAgentPersonas(): Record<string, AgentPersona> {
  const catalog = useInterviewAgents();
  if (!catalog.data) return AGENT_PERSONAS;
  return Object.fromEntries(catalog.data.map(agent => [agent.agent_id, {
    ...(AGENT_PERSONAS[agent.agent_id] || { recommendedRounds: [], theme: AGENT_PERSONAS.alex.theme, voiceDescription: "AI interviewer" }),
    id: agent.agent_id, name: agent.name, role: agent.role,
    voiceDescription: AGENT_PERSONAS[agent.agent_id]?.voiceDescription || "AI interviewer",
    styleDescription: agent.description || "Asks questions about this round's focus areas.",
    primaryCompetencies: (agent.focal_competencies || []).map(area => area.replaceAll("_", " ")),
  }]));
}

export interface AgentRoundMapperProps {
  selectedAgentIds?: string[];
  selectedAgentId?: "alex" | "jordan" | string;
  onSelectAgents?: (agentIds: string[]) => void;
  onSelectAgent?: (agentId: string) => void;
  roundType?: string;
  className?: string;
}

export function AgentRoundMapper({
  selectedAgentIds,
  selectedAgentId = "alex",
  onSelectAgents,
  onSelectAgent,
  roundType,
  className,
}: AgentRoundMapperProps) {
  const personas = useAgentPersonas();
  const normalizedSelected = Array.from(
    new Set((selectedAgentIds?.length ? selectedAgentIds : [selectedAgentId]).map((id) => id.toLowerCase()))
  );
  const selectAgents = (ids: string[]) => {
    if (onSelectAgents) onSelectAgents(ids);
    else if (onSelectAgent && ids[0]) onSelectAgent(ids[0]);
  };
  return (
    <div className={cn("grid grid-cols-1 sm:grid-cols-2 gap-3", className)}>
      {Object.values(personas).map((agent) => {
        const isSelected = normalizedSelected.includes(agent.id);
        const isRecommended = roundType ? agent.recommendedRounds.includes(roundType) : false;

        return (
          <div
            key={agent.id}
            role="button"
            tabIndex={0}
            aria-pressed={isSelected}
            onClick={() => {
              const next = isSelected
                ? normalizedSelected.filter((id) => id !== agent.id)
                : [...normalizedSelected, agent.id];
              // A round must always retain one interviewer.
              selectAgents((next.length ? next : [agent.id]));
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                const next = isSelected
                  ? normalizedSelected.filter((id) => id !== agent.id)
                  : [...normalizedSelected, agent.id];
                selectAgents((next.length ? next : [agent.id]));
              }
            }}
            className={cn(
              "relative text-left p-3.5 rounded-xl border transition-all duration-200 cursor-pointer outline-none",
              isSelected
                ? cn("border-2 shadow-sm", agent.theme.borderActive, agent.theme.bgActive)
                : "border-border hover:border-border-hover bg-card hover:bg-bg/40"
            )}
          >
            {/* Recommendation Tag */}
            {isRecommended && (
              <div className="absolute -top-2.5 right-3">
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand text-white shadow-xs">
                  <Sparkles className="h-2.5 w-2.5" />
                  Recommended
                </span>
              </div>
            )}

            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <div
                  className={cn(
                    "h-9 w-9 rounded-lg flex items-center justify-center shrink-0 border",
                    isSelected
                      ? cn(agent.theme.badgeBg, agent.theme.iconColor)
                      : "bg-surface border-border text-text-muted"
                  )}
                >
                  {agent.id === "alex" ? (
                    <Cpu className="h-5 w-5" />
                  ) : (
                    <Compass className="h-5 w-5" />
                  )}
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <h4 className="text-sm font-semibold text-text-primary">{agent.name}</h4>
                    <span className="text-xs text-text-muted">({agent.role})</span>
                  </div>
                  <div className="flex items-center gap-1 text-[11px] text-text-muted mt-0.5">
                    <Volume2 className="h-3 w-3" />
                    <span>{agent.voiceDescription}</span>
                  </div>
                </div>
              </div>

              {/* Selection Checkmark */}
              <div
                className={cn(
                  "h-5 w-5 rounded-full flex items-center justify-center border transition-colors shrink-0",
                  isSelected
                    ? "bg-brand text-white border-brand"
                    : "border-border text-transparent"
                )}
              >
                <Check className="h-3 w-3 stroke-[2.5]" />
              </div>
            </div>

            <p className="text-xs text-text-secondary mt-2.5 line-clamp-2 leading-relaxed">
              {agent.styleDescription}
            </p>

            {/* Competency Chips */}
            <div className="flex flex-wrap gap-1 mt-2.5 pt-2 border-t border-border/60">
              {agent.primaryCompetencies.slice(0, 3).map((comp) => (
                <span
                  key={comp}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border text-text-muted"
                >
                  {comp}
                </span>
              ))}
              {agent.primaryCompetencies.length > 3 && (
                <span className="text-[10px] px-1 py-0.5 text-text-muted">
                  +{agent.primaryCompetencies.length - 3} more
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
