/**
Intra AI — Interview Round Sequencer Component (P3-04).

Manages dynamic interview rounds, ordering via order_index, enable toggling,
duration budgeting, competency configuration, and agent persona mapping.
 */

import React, { useState } from "react";
import {
  ChevronUp,
  ChevronDown,
  ChevronRight,
  Plus,
  Trash2,
  Clock,
  Shield,
  Bot,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { CompetencySelector } from "@/components/jobs/competency-selector";
import { AgentRoundMapper, AGENT_PERSONAS, useAgentPersonas } from "@/components/jobs/agent-round-mapper";
import type { InterviewRoundConfig, InterviewRoundType } from "@/types";

export interface RoundSequencerProps {
  rounds: InterviewRoundConfig[];
  onChange: (rounds: InterviewRoundConfig[]) => void;
  className?: string;
}

const ROUND_PRESETS: {
  type: InterviewRoundType;
  label: string;
  defaultDuration: number;
  defaultAgent: "alex" | "jordan";
  defaultFocus: string[];
}[] = [
  {
    type: "introduction",
    label: "Candidate Introduction",
    defaultDuration: 7,
    defaultAgent: "alex",
    defaultFocus: ["technical_depth", "user_empathy"],
  },
  {
    type: "technical",
    label: "Technical Architecture & Coding",
    defaultDuration: 20,
    defaultAgent: "alex",
    defaultFocus: ["system_design", "software_architecture", "coding_problem_solving", "scalability"],
  },
  {
    type: "behavioral",
    label: "Product & Behavioral Assessment",
    defaultDuration: 15,
    defaultAgent: "jordan",
    defaultFocus: ["product_sense", "customer_impact", "trade_off_analysis", "prioritization"],
  },
  {
    type: "hr_culture",
    label: "Culture & Collaboration",
    defaultDuration: 10,
    defaultAgent: "jordan",
    defaultFocus: ["stakeholder_management", "user_empathy"],
  },
];

const DURATION_OPTIONS = [5, 7, 10, 15, 20, 25, 30];

export function RoundSequencer({
  rounds,
  onChange,
  className,
}: RoundSequencerProps) {
  const personas = useAgentPersonas();
  const [expandedIndex, setExpandedIndex] = useState<number | null>(0);

  // Reorder rounds
  const moveRound = (index: number, direction: "up" | "down") => {
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= rounds.length) return;

    const newRounds = [...rounds];
    const temp = newRounds[index];
    newRounds[index] = newRounds[targetIndex];
    newRounds[targetIndex] = temp;

    // Normalize order_index
    const updated = newRounds.map((r, i) => ({
      ...r,
      order_index: i + 1,
    }));
    onChange(updated);
    if (expandedIndex === index) setExpandedIndex(targetIndex);
    else if (expandedIndex === targetIndex) setExpandedIndex(index);
  };

  const updateRound = (index: number, updates: Partial<InterviewRoundConfig>) => {
    const updated = rounds.map((r, i) => (i === index ? { ...r, ...updates } : r));
    onChange(updated);
  };

  const toggleRoundEnabled = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    updateRound(index, { enabled: !rounds[index].enabled });
  };

  const removeRound = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (rounds.length <= 1) return;
    const newRounds = rounds.filter((_, i) => i !== index).map((r, i) => ({
      ...r,
      order_index: i + 1,
    }));
    onChange(newRounds);
    if (expandedIndex === index) {
      setExpandedIndex(null);
    } else if (expandedIndex !== null && expandedIndex > index) {
      setExpandedIndex(expandedIndex - 1);
    }
  };

  const addPresetRound = (preset: typeof ROUND_PRESETS[0]) => {
    const newRound: InterviewRoundConfig = {
      type: preset.type,
      duration_minutes: preset.defaultDuration,
      focus_areas: [...preset.defaultFocus],
      enabled: true,
      order_index: rounds.length + 1,
      agent_ids: [preset.defaultAgent],
      agent_id: preset.defaultAgent,
    };
    onChange([...rounds, newRound]);
    setExpandedIndex(rounds.length);
  };

  const getRoundLabel = (type: string) => {
    switch (type) {
      case "introduction":
        return "Candidate Introduction";
      case "technical":
        return "Technical Assessment";
      case "behavioral":
        return "Behavioral & Leadership";
      case "hr_culture":
        return "Culture & Collaboration";
      default:
        return type.replace(/_/g, " ");
    }
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Rounds List */}
      <div className="space-y-3">
        {rounds.map((round, index) => {
          const isExpanded = expandedIndex === index;
          const agentIds = round.agent_ids?.length
            ? round.agent_ids
            : [round.agent_id || (round.type === "technical" ? "alex" : "jordan")];
          const assignedAgents = agentIds
            .map((id) => personas[id] || { ...AGENT_PERSONAS.alex, id, name: "Unavailable interviewer" })
            .filter(Boolean);
          const assignedAgent = assignedAgents[0] || AGENT_PERSONAS.alex;

          return (
            <div
              key={index}
              className={cn(
                "rounded-xl border transition-all duration-200 overflow-hidden bg-card",
                round.enabled ? "border-border" : "border-border/50 opacity-60 bg-bg/30",
                isExpanded && "border-brand/40 ring-1 ring-brand/20 shadow-sm"
              )}
            >
              {/* Header / Summary Bar */}
              <div
                role="button"
                tabIndex={0}
                onClick={() => setExpandedIndex(isExpanded ? null : index)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setExpandedIndex(isExpanded ? null : index);
                  }
                }}
                className="flex items-center justify-between p-3 sm:p-4 cursor-pointer hover:bg-bg/40 transition-colors select-none"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  {/* Order Controls */}
                  <div className="flex flex-col items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      disabled={index === 0}
                      onClick={() => moveRound(index, "up")}
                      className="p-1 rounded text-text-muted hover:text-text-primary disabled:opacity-20 disabled:hover:text-text-muted transition-colors"
                      title="Move round earlier"
                    >
                      <ChevronUp className="h-3.5 w-3.5" />
                    </button>
                    <span className="text-xs font-mono font-bold text-text-muted w-4 text-center">
                      {index + 1}
                    </span>
                    <button
                      type="button"
                      disabled={index === rounds.length - 1}
                      onClick={() => moveRound(index, "down")}
                      className="p-1 rounded text-text-muted hover:text-text-primary disabled:opacity-20 disabled:hover:text-text-muted transition-colors"
                      title="Move round later"
                    >
                      <ChevronDown className="h-3.5 w-3.5" />
                    </button>
                  </div>

                  {/* Round Identity */}
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h4 className="text-sm font-semibold text-text-primary capitalize">
                        {getRoundLabel(round.type)}
                      </h4>
                      {/* Assigned Agent Badge */}
                      <span
                        className={cn(
                          "inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border",
                          assignedAgent.theme.badgeBg,
                          assignedAgent.theme.badgeText
                        )}
                      >
                        <Bot className="h-3 w-3" />
                        {assignedAgents.map((agent) => agent.name).join(" + ")}
                      </span>
                      {/* Duration Chip */}
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-surface border border-border text-text-muted">
                        <Clock className="h-3 w-3" />
                        {round.duration_minutes} min
                      </span>
                    </div>

                    {/* Competency Summary */}
                    <div className="flex items-center gap-1.5 text-xs text-text-muted mt-1">
                      <span>
                        {round.focus_areas?.length || 0} focal{" "}
                        {round.focus_areas?.length === 1 ? "competency" : "competencies"}
                      </span>
                      {round.focus_areas && round.focus_areas.length > 0 && (
                        <>
                          <span>•</span>
                          <span className="text-text-secondary truncate max-w-xs capitalize">
                            {round.focus_areas.slice(0, 2).map((c) => c.replace(/_/g, " ")).join(", ")}
                            {round.focus_areas.length > 2 ? "..." : ""}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* Right Actions */}
                <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                  {/* Enable/Disable Toggle */}
                  <Button
                    type="button"
                    variant={round.enabled ? "secondary" : "ghost"}
                    size="sm"
                    onClick={(e) => toggleRoundEnabled(index, e)}
                    className={cn(
                      "text-xs h-7 px-2.5 rounded-full",
                      round.enabled
                        ? "text-brand border-brand/30 bg-brand/5 hover:bg-brand/10"
                        : "text-text-muted hover:text-text-primary"
                    )}
                  >
                    {round.enabled ? "Active" : "Disabled"}
                  </Button>

                  {/* Remove Round */}
                  {rounds.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={(e) => removeRound(index, e)}
                      className="h-7 w-7 p-0 text-text-muted hover:text-danger rounded-full"
                      title="Delete round"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}

                  {/* Expand Chevron */}
                  <div
                    className={cn(
                      "text-text-muted transition-transform duration-200 p-1",
                      isExpanded && "rotate-90 text-text-primary"
                    )}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </div>
                </div>
              </div>

              {/* Expandable Configuration Body */}
              {isExpanded && (
                <div className="border-t border-border p-4 sm:p-5 space-y-5 bg-card/60 animate-in fade-in-50 duration-200">
                  {/* Round Settings Row */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pb-2 border-b border-border">
                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-text-secondary">Round Type</label>
                      <select
                        value={round.type}
                        onChange={(e) =>
                          updateRound(index, { type: e.target.value as InterviewRoundType })
                        }
                        className="w-full h-9 rounded-md border border-border bg-bg px-3 py-1 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-brand"
                      >
                        <option value="introduction">Candidate Introduction</option>
                        <option value="technical">Technical Assessment</option>
                        <option value="behavioral">Behavioral & Product</option>
                        <option value="hr_culture">Culture & HR</option>
                      </select>
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-text-secondary">
                        Duration Allocation (Minutes)
                      </label>
                      <div className="flex items-center gap-1.5">
                        {DURATION_OPTIONS.map((dur) => (
                          <button
                            key={dur}
                            type="button"
                            onClick={() => updateRound(index, { duration_minutes: dur })}
                            className={cn(
                              "h-8 px-2.5 rounded-md text-xs font-medium transition-colors border",
                              round.duration_minutes === dur
                                ? "bg-brand text-white border-brand font-semibold shadow-xs"
                                : "bg-card border-border text-text-muted hover:text-text-primary hover:border-border-hover"
                            )}
                          >
                            {dur}m
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Persona Assignment */}
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
                      <Bot className="h-3.5 w-3.5 text-brand" />
                      Assigned Interviewer Persona
                    </label>
                    <AgentRoundMapper
                      selectedAgentIds={agentIds}
                      onSelectAgents={(agentIds) => updateRound(index, { agent_ids: agentIds, agent_id: agentIds[0] })}
                      roundType={round.type}
                    />
                  </div>

                  {/* Competency Mapping */}
                  <div className="space-y-2 pt-2 border-t border-border">
                    <label className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
                      <Shield className="h-3.5 w-3.5 text-brand" />
                      Round Competencies & Focus Areas
                    </label>
                    <CompetencySelector
                      selectedCompetencies={round.focus_areas || []}
                      onChange={(newFocus) => updateRound(index, { focus_areas: newFocus })}
                      preferredAgent={agentIds[0]}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Add Preset Round Toolbar */}
      <div className="flex flex-wrap items-center gap-2 pt-2">
        <span className="text-xs text-text-muted font-medium flex items-center gap-1">
          <Plus className="h-3.5 w-3.5" /> Add Round:
        </span>
        {ROUND_PRESETS.map((preset) => (
          <Button
            key={preset.type}
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => addPresetRound(preset)}
            className="text-xs h-8 gap-1.5 hover:border-brand/40"
          >
            <Plus className="h-3 w-3 text-brand" />
            {preset.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
