/**
Intra AI — Pre-Flight Publish Validation Modal (P3-09).

Verifies opportunity completeness, round architecture, competency tagging,
persona assignment, and WebRTC session duration limits before publishing.
 */

import React from "react";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Send,
  Loader2,
  ShieldCheck,
  Clock,
  Bot,
  Layers,
  FileCheck,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { InterviewRoundConfig } from "@/types";

export interface PublishValidationModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: {
    title: string;
    department: string;
    location: string;
    description: string;
    skills: string[];
    rounds: InterviewRoundConfig[];
  };
  onConfirmPublish: () => void;
  isPublishing?: boolean;
}

interface ValidationCheck {
  id: string;
  label: string;
  description: string;
  passed: boolean;
  severity: "critical" | "warning";
}

export function PublishValidationModal({
  open,
  onOpenChange,
  data,
  onConfirmPublish,
  isPublishing = false,
}: PublishValidationModalProps) {
  const activeRounds = data.rounds.filter((r) => r.enabled);
  const totalDuration = activeRounds.reduce((sum, r) => sum + (r.duration_minutes || 0), 0);

  // Check items
  const checks: ValidationCheck[] = [
    {
      id: "basics",
      label: "Opportunity Information",
      description: "Title, Department, Location, and Description are complete",
      passed: Boolean(
        data.title.trim() &&
        data.department.trim() &&
        data.location.trim() &&
        data.description.trim()
      ),
      severity: "critical",
    },
    {
      id: "skills",
      label: "Required Skills",
      description: `At least 1 required skill specified (${data.skills.length} configured)`,
      passed: data.skills.length > 0,
      severity: "critical",
    },
    {
      id: "rounds",
      label: "Active Interview Rounds",
      description: `At least 1 active round configured (${activeRounds.length} active)`,
      passed: activeRounds.length > 0,
      severity: "critical",
    },
    {
      id: "personas",
      label: "Agent Persona Assignment",
      description: "At least one interviewer persona assigned to every active round",
      passed:
        activeRounds.length > 0 &&
        activeRounds.every((r) => (r.agent_ids?.length || (r.agent_id ? 1 : 0)) > 0),
      severity: "critical",
    },
    {
      id: "competencies",
      label: "Focal Competencies",
      description: "At least 1 focal competency assigned to each active round",
      passed:
        activeRounds.length > 0 &&
        activeRounds.every((r) => r.focus_areas && r.focus_areas.length > 0),
      severity: "critical",
    },
    {
      id: "duration_max",
      label: "WebRTC Max Session Constraint",
      description: `Total duration (${totalDuration} min) does not exceed Agora 60-minute token limit`,
      passed: totalDuration <= 60,
      severity: "critical",
    },
    {
      id: "duration_min",
      label: "Minimum Recommended Duration",
      description: `Total duration (${totalDuration} min) meets 15-minute comprehensive assessment baseline`,
      passed: totalDuration >= 15,
      severity: "warning",
    },
  ];

  const criticalFailed = checks.filter((c) => c.severity === "critical" && !c.passed);
  const warningFailed = checks.filter((c) => c.severity === "warning" && !c.passed);
  const canPublish = criticalFailed.length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-lg bg-brand/10 text-brand flex items-center justify-center">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle>Pre-Flight Publish Validation</DialogTitle>
              <DialogDescription className="text-xs">
                Verifying opportunity requirements before opening candidate evaluation
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Status Summary Banner */}
        <div
          className={cn(
            "p-3 rounded-lg border text-xs flex items-center justify-between",
            canPublish
              ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-700 dark:text-emerald-400"
              : "bg-danger/10 border-danger/30 text-danger"
          )}
        >
          <div className="flex items-center gap-2">
            {canPublish ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <XCircle className="h-4 w-4 shrink-0 text-danger" />
            )}
            <span className="font-semibold">
              {canPublish
                ? "All critical requirements passed — Ready to publish"
                : `${criticalFailed.length} blocking ${criticalFailed.length === 1 ? "issue" : "issues"} detected`}
            </span>
          </div>
          <Badge
            variant="outline"
            className={cn(
              "text-[10px] font-bold uppercase",
              canPublish
                ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                : "border-danger/40 text-danger"
            )}
          >
            {canPublish ? "Verified" : "Blocked"}
          </Badge>
        </div>

        {/* Verification Checklist */}
        <div className="space-y-2 py-1 max-h-72 overflow-y-auto pr-1">
          {checks.map((check) => (
            <div
              key={check.id}
              className={cn(
                "flex items-start gap-2.5 p-2.5 rounded-lg border transition-colors",
                check.passed
                  ? "bg-card border-border/80"
                  : check.severity === "critical"
                  ? "bg-danger/5 border-danger/30"
                  : "bg-amber-500/5 border-amber-500/30"
              )}
            >
              <div className="mt-0.5 shrink-0">
                {check.passed ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                ) : check.severity === "critical" ? (
                  <XCircle className="h-4 w-4 text-danger" />
                ) : (
                  <AlertTriangle className="h-4 w-4 text-amber-500" />
                )}
              </div>
              <div className="flex-1">
                <p
                  className={cn(
                    "text-xs font-semibold",
                    check.passed
                      ? "text-text-primary"
                      : check.severity === "critical"
                      ? "text-danger"
                      : "text-amber-600 dark:text-amber-400"
                  )}
                >
                  {check.label}
                </p>
                <p className="text-[11px] text-text-muted mt-0.5 leading-normal">
                  {check.description}
                </p>
              </div>
            </div>
          ))}
        </div>

        <DialogFooter className="gap-2 sm:gap-0 pt-2 border-t border-border">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isPublishing}
          >
            Return to Edit
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={onConfirmPublish}
            disabled={!canPublish || isPublishing}
            className="bg-brand hover:bg-brand-hover text-white gap-1.5 shadow-sm"
          >
            {isPublishing ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Publishing...
              </>
            ) : (
              <>
                <Send className="h-3.5 w-3.5" />
                Confirm & Publish Opportunity
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
