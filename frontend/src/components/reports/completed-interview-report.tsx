"use client";

import Link from "next/link";
import { useReportStatus } from "@/hooks/queries/useReports";
import { formatDate } from "@/lib/utils";
import type { BackendScheduledInterviewResponse } from "@/types/api";

/** Completed interviews remain discoverable even before a report is published. */
export function CompletedInterviewReport({ interview }: { interview: BackendScheduledInterviewResponse }) {
  const query = useReportStatus(interview.id);
  const state = query.data;
  const labels = {
    ready: "Ready",
    generating: "Preparing report…",
    failed: state?.retryable ? "Preparation failed — retry available" : "Preparation failed — review details",
    not_started: "Ready to prepare",
    not_completed: "Interview completion pending",
  };
  return <li className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-3 last:border-0">
    <div className="min-w-0">
      <p className="text-sm font-semibold text-text-primary">{interview.candidate?.name || "Candidate"}</p>
      <p className="mt-0.5 text-xs text-text-muted">{interview.job?.title || "Interview assessment"} · {formatDate(interview.scheduled_at)}</p>
      <p className={`mt-1 text-xs ${state?.status === "failed" || query.error ? "text-error" : "text-text-muted"}`}>
        {query.error ? "Report status could not be loaded." : state ? labels[state.status] : "Checking report…"}
      </p>
    </div>
    <Link href={`/admin/reports/${interview.id}`} className="text-sm font-medium text-brand hover:text-brand-hover">
      {state?.status === "ready" ? "View Report" : state?.status === "failed" && state.retryable ? "Review & Retry" : "Open Report"}
    </Link>
  </li>;
}
