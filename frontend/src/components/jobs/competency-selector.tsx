/**
Intra AI — Competency Selector Component (P3-05).

Provides categorized selection of canonical M1 focal competencies for Alex (Technical)
and Jordan (Product), plus custom competency tagging into round.focus_areas.
 */

import React, { useState } from "react";
import { Shield, Plus, X, Cpu, Compass, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export const TECHNICAL_COMPETENCIES = [
  { id: "system_design", label: "System Design", category: "Architecture" },
  { id: "software_architecture", label: "Software Architecture", category: "Architecture" },
  { id: "coding_problem_solving", label: "Coding & Problem Solving", category: "Execution" },
  { id: "scalability", label: "Scalability & Distributed Systems", category: "Systems" },
  { id: "technical_decision_making", label: "Technical Decision Making", category: "Strategy" },
  { id: "debugging", label: "Debugging & Reasoning", category: "Execution" },
  { id: "technical_depth", label: "Technical Depth", category: "Core" },
  { id: "distributed_systems", label: "Distributed Systems", category: "Systems" },
  { id: "database_optimization", label: "Database Optimization", category: "Data" },
];

export const PRODUCT_COMPETENCIES = [
  { id: "product_sense", label: "Product Sense", category: "Design" },
  { id: "customer_impact", label: "Customer Impact", category: "Strategy" },
  { id: "trade_off_analysis", label: "Strategic Trade-offs", category: "Strategy" },
  { id: "metrics_and_roi", label: "Metrics & ROI", category: "Analytics" },
  { id: "user_empathy", label: "User Empathy", category: "Design" },
  { id: "prioritization", label: "Prioritization & Roadmapping", category: "Execution" },
  { id: "stakeholder_management", label: "Stakeholder Management", category: "Collaboration" },
];

export interface CompetencySelectorProps {
  selectedCompetencies: string[];
  onChange: (competencies: string[]) => void;
  preferredAgent?: "alex" | "jordan" | string;
  className?: string;
}

export function CompetencySelector({
  selectedCompetencies = [],
  onChange,
  preferredAgent,
  className,
}: CompetencySelectorProps) {
  const [customTag, setCustomTag] = useState("");

  const toggleCompetency = (id: string) => {
    if (selectedCompetencies.includes(id)) {
      onChange(selectedCompetencies.filter((c) => c !== id));
    } else {
      onChange([...selectedCompetencies, id]);
    }
  };

  const addCustomTag = () => {
    const trimmed = customTag.trim().toLowerCase().replace(/\s+/g, "_");
    if (trimmed && !selectedCompetencies.includes(trimmed)) {
      onChange([...selectedCompetencies, trimmed]);
      setCustomTag("");
    }
  };

  const removeCompetency = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(selectedCompetencies.filter((c) => c !== id));
  };

  // Determine standard vs custom
  const allStandardIds = new Set([
    ...TECHNICAL_COMPETENCIES.map((c) => c.id),
    ...PRODUCT_COMPETENCIES.map((c) => c.id),
  ]);
  const customCompetencies = selectedCompetencies.filter((c) => !allStandardIds.has(c));

  return (
    <div className={cn("space-y-4", className)}>
      {/* Active Selected Summary */}
      <div className="flex flex-wrap items-center gap-1.5 min-h-[32px] p-2.5 rounded-lg border border-border bg-bg/40">
        <span className="text-[11px] font-medium text-text-muted mr-1">
          Active ({selectedCompetencies.length}):
        </span>
        {selectedCompetencies.length === 0 ? (
          <span className="text-xs text-text-muted italic">
            No competencies selected yet. Click pills below or add custom tags.
          </span>
        ) : (
          selectedCompetencies.map((comp) => (
            <span
              key={comp}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-brand/10 border border-brand/20 text-xs font-medium text-brand capitalize shadow-xs"
            >
              {comp.replace(/_/g, " ")}
              <button
                type="button"
                onClick={(e) => removeCompetency(comp, e)}
                className="text-brand/70 hover:text-danger rounded p-0.5"
                title={`Remove ${comp}`}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))
        )}
      </div>

      {/* Technical Competencies (Alex) */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Cpu className="h-3.5 w-3.5 text-blue-500" />
            <span className="text-xs font-semibold text-text-secondary">
              Technical Competencies (Alex)
            </span>
          </div>
          {preferredAgent === "alex" && (
            <Badge variant="outline" className="text-[10px] text-blue-500 border-blue-500/30">
              Recommended for Technical Round
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {TECHNICAL_COMPETENCIES.map((c) => {
            const isSelected = selectedCompetencies.includes(c.id);
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => toggleCompetency(c.id)}
                className={cn(
                  "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 border",
                  isSelected
                    ? "bg-blue-500/15 border-blue-500/40 text-blue-600 dark:text-blue-400 shadow-xs font-semibold"
                    : "bg-card border-border text-text-secondary hover:border-blue-500/30 hover:text-text-primary"
                )}
              >
                {isSelected && <Check className="h-3 w-3 text-blue-500" />}
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Product Competencies (Jordan) */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Compass className="h-3.5 w-3.5 text-amber-500" />
            <span className="text-xs font-semibold text-text-secondary">
              Product & Behavioral Competencies (Jordan)
            </span>
          </div>
          {preferredAgent === "jordan" && (
            <Badge variant="outline" className="text-[10px] text-amber-500 border-amber-500/30">
              Recommended for Product/Behavioral Round
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {PRODUCT_COMPETENCIES.map((c) => {
            const isSelected = selectedCompetencies.includes(c.id);
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => toggleCompetency(c.id)}
                className={cn(
                  "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all duration-150 border",
                  isSelected
                    ? "bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400 shadow-xs font-semibold"
                    : "bg-card border-border text-text-secondary hover:border-amber-500/30 hover:text-text-primary"
                )}
              >
                {isSelected && <Check className="h-3 w-3 text-amber-500" />}
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Custom Competency Input */}
      <div className="flex items-center gap-2 pt-1 border-t border-border">
        <input
          type="text"
          value={customTag}
          onChange={(e) => setCustomTag(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addCustomTag();
            }
          }}
          placeholder="Add custom competency (e.g. cloud_security)..."
          className="flex-1 h-8 text-xs rounded-md border border-border bg-bg px-2.5 text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-brand"
        />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={addCustomTag}
          className="h-8 text-xs gap-1"
        >
          <Plus className="h-3 w-3" />
          Add Tag
        </Button>
      </div>
    </div>
  );
}
