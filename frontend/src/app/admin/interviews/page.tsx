"use client";

import Link from "next/link";
import { FileText, Video } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn, formatDate } from "@/lib/utils";
import type { InterviewStatus } from "@/types";

import { useInterviews } from "@/hooks/queries/useScheduling";

import { EmptyState } from "@/components/ui/empty-state";

interface InterviewItem {
  id: string;
  candidateId?: string;
  candidate: string;
  job: string;
  date: string; // "YYYY-MM-DD"
  time: string; // "10:00"
  duration: number;
  status: InterviewStatus;
}

const STATUS_COLORS: Record<InterviewStatus, string> = {
  scheduled: "bg-brand-light border-brand text-brand",
  in_progress: "bg-warning-light border-warning text-warning",
  completed: "bg-success-light border-success text-success",
  cancelled: "bg-error-light border-error text-error",
};

export default function InterviewsPage() {
  const { data, isLoading } = useInterviews();
  const rawList = data?.interviews ?? [];
  const realInterviews: InterviewItem[] = rawList.map((iv) => {
    const d = new Date(iv.scheduled_at);
    const hour = isNaN(d.getHours()) ? 10 : d.getHours();
    const hoursStr = String(hour).padStart(2, "0");
    const minsStr = String(d.getMinutes()).padStart(2, "0");
    const isoDate = Number.isNaN(d.getTime()) ? "" : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return {
      id: iv.id,
      candidateId: iv.candidate?.id || iv.id,
      candidate: iv.candidate?.name || "Candidate",
      job: iv.job?.title || "Role Interview",
      date: isoDate,
      time: `${hoursStr}:${minsStr}`,
      duration: iv.duration_minutes || 60,
      status: (iv.status || "scheduled") as InterviewStatus,
    };
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Interviews</h1>
          <p className="text-sm text-text-muted mt-0.5">
            {isLoading
              ? "Loading interviews..."
              : `${realInterviews.length} ${realInterviews.length === 1 ? "interview" : "interviews"} scheduled.`}
          </p>
        </div>
      </div>

      <nav className="flex gap-4 border-b border-border text-sm" aria-label="Interview views">
        <span aria-current="page" className="border-b-2 border-brand pb-3 font-semibold text-brand">Scheduled Interviews</span>
        <Link href="/admin/interviews/templates" className="pb-3 text-text-muted hover:text-brand">Interview Templates</Link>
      </nav>

      {isLoading ? (
        <div className="p-12 text-center text-sm text-text-muted animate-pulse">
          Loading interview schedules...
        </div>
      ) : (
        /* ── LIST VIEW ── */
        realInterviews.length === 0 ? (
          <EmptyState
            icon={Video}
            title="No interviews scheduled"
            description="No candidate interviews have been scheduled yet."
          />
        ) : (
          <div className="space-y-3">
            {realInterviews.map((iv) => (
              <Card key={iv.id} className="p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <Avatar size="sm" name={iv.candidate} />
                    <div>
                      <p className="text-sm font-semibold text-text-primary">
                        {iv.candidate}
                      </p>
                      <p className="text-xs text-text-muted mt-0.5">{iv.job}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <div className="text-right">
                      <p className="text-sm text-text-primary">
                        {formatDate(iv.date)}
                      </p>
                      <p className="text-xs text-text-muted">
                        {iv.time} · {iv.duration} min
                      </p>
                    </div>
                    <StatusBadge status={iv.status} />
                    <Link
                      href={`/interview/${iv.id}/prep`}
                      className="inline-flex items-center gap-1 text-xs text-brand hover:text-brand-hover font-medium"
                    >
                      <Video className="h-3.5 w-3.5" />
                      Open Room
                    </Link>
                    {iv.status === "completed" && (
                      <Link href={`/admin/reports/${iv.id}`} className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:text-brand-hover">
                        <FileText className="h-3.5 w-3.5" /> Open Report
                      </Link>
                    )}
                    {iv.candidateId ? (
                      <Link
                        href={`/admin/candidates/${iv.candidateId}`}
                        className="text-xs text-text-muted hover:text-text-primary font-medium"
                      >
                        Candidate
                      </Link>
                    ) : null}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )
      )}

      {/* Legend */}
      <div className="flex flex-wrap gap-4 pt-2">
        {(["scheduled", "in_progress", "completed", "cancelled"] as InterviewStatus[]).map((s) => (
          <div key={s} className="flex items-center gap-1.5">
            <div className={cn("h-3 w-3 rounded border", STATUS_COLORS[s])} />
            <StatusBadge status={s} />
          </div>
        ))}
      </div>
    </div>
  );
}
