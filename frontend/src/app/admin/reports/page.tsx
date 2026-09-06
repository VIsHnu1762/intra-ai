"use client";

import { useState } from "react";
import Link from "next/link";
import { Download, FileText, ArrowUpDown } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Avatar } from "@/components/ui/avatar";
import { ScoreBadge } from "@/components/ui/score-badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { cn, formatDate, getRecommendationLabel } from "@/lib/utils";
import type { Recommendation } from "@/types";

import { useReports } from "@/hooks/queries/useReports";
import { safeReportPdfUrl } from "@/lib/report-presentation";
import { useInterviews } from "@/hooks/queries/useScheduling";
import { CompletedInterviewReport } from "@/components/reports/completed-interview-report";

interface ReportItem {
  id: string;
  interviewId: string;
  candidate: string;
  job: string;
  score: number;
  recommendation: Recommendation;
  date: string;
  pdfUrl?: string | null;
}

const REC_FILTERS: { key: Recommendation | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "strong_hire", label: "Strong Hire" },
  { key: "hire", label: "Hire" },
  { key: "maybe", label: "Maybe" },
  { key: "no_hire", label: "No Hire" },
];

const REC_BADGE_STYLES: Record<Recommendation, string> = {
  strong_hire: "bg-success-light text-success",
  hire: "bg-brand-light text-brand",
  maybe: "bg-warning-light text-warning",
  no_hire: "bg-error-light text-error",
};

type SortField = "date" | "score";

export default function ReportsPage() {
  const [recFilter, setRecFilter] = useState<Recommendation | "all">("all");
  const [sort, setSort] = useState<SortField>("date");
  const [sortAsc, setSortAsc] = useState(false);

  const { data, isLoading, error, refetch } = useReports({
    recommendation: recFilter !== "all" ? recFilter : undefined,
  });
  const completed = useInterviews({ status: "completed", per_page: 20 });

  const reportsList = data?.reports ?? [];
  const reports: ReportItem[] = reportsList.map((r) => {
    const cand = (r.candidate as Record<string, unknown> | null) ?? null;
    const candName = (cand?.name as string) || "Candidate";
    const job = (r.job as Record<string, unknown> | null) ?? null;
    const jobTitle = (job?.title as string) || "Role Assessment";
    return {
      id: r.id,
      interviewId: r.interview_id,
      candidate: candName,
      job: jobTitle,
      score: Math.round(r.overall_score),
      recommendation: r.recommendation,
      date: r.created_at,
      pdfUrl: safeReportPdfUrl(r.pdf_url),
    };
  });

  const toggleSort = (field: SortField) => {
    if (sort === field) {
      setSortAsc((v) => !v);
    } else {
      setSort(field);
      setSortAsc(false);
    }
  };

  const filtered = reports.sort((a, b) => {
    let val = 0;
    if (sort === "date") {
      val = new Date(a.date).getTime() - new Date(b.date).getTime();
    } else {
      val = a.score - b.score;
    }
    return sortAsc ? val : -val;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Assessment Reports</h1>
        <p className="text-sm text-text-muted mt-0.5">
          {isLoading
            ? "Loading reports..."
            : error ? "Reports could not be loaded." : `${reports.length} completed interview ${reports.length === 1 ? "report" : "reports"}.`}
        </p>
      </div>

      {(completed.isLoading || completed.error || !!completed.data?.interviews.length) && <Card className="p-5">
        <h2 className="text-base font-semibold text-text-primary">Recent Completed Interviews</h2>
        <p className="mt-1 text-sm text-text-muted">Check report progress or retry a report that could not be prepared.</p>
        {completed.isLoading ? <p className="mt-3 text-sm text-text-muted">Loading interviews…</p>
          : completed.error ? <div className="mt-3" role="alert"><p className="text-sm text-error">Completed interviews could not be loaded.</p>
            <Button variant="secondary" size="sm" className="mt-2" onClick={() => void completed.refetch()}>Try Again</Button></div>
          : <ul className="mt-3">{completed.data?.interviews.map(interview => <CompletedInterviewReport key={interview.id} interview={interview} />)}</ul>}
      </Card>}

      {/* Filters + sort */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Recommendation filter */}
        <div className="flex flex-wrap gap-2">
          {REC_FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setRecFilter(f.key)}
              className={cn(
                "px-3 py-1.5 rounded-full text-sm font-medium transition-colors duration-100",
                recFilter === f.key
                  ? "bg-brand text-white"
                  : "bg-border text-text-muted hover:text-text-primary"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Sort buttons */}
        <div className="ml-auto flex gap-2">
          {(["date", "score"] as SortField[]).map((field) => (
            <button
              key={field}
              onClick={() => toggleSort(field)}
              className={cn(
                "flex items-center gap-1 px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors duration-100",
                sort === field
                  ? "border-brand text-brand bg-brand-light"
                  : "border-border text-text-muted hover:border-brand/40"
              )}
            >
              <ArrowUpDown className="h-3.5 w-3.5" />
              {field.charAt(0).toUpperCase() + field.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Reports grid */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="p-5 animate-pulse space-y-4">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-border" />
                <div className="space-y-2 flex-1">
                  <div className="h-4 w-1/2 bg-border rounded" />
                  <div className="h-3 w-1/3 bg-border rounded" />
                </div>
              </div>
              <div className="h-10 bg-border/50 rounded" />
              <div className="h-8 bg-border/30 rounded" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <Card className="p-6" role="alert">
          <p className="text-sm text-error">{error.message || "We couldn’t load assessment reports."}</p>
          <Button variant="secondary" size="sm" className="mt-4" onClick={() => void refetch()}>Try Again</Button>
        </Card>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={FileText}
          title="No reports found"
          description={
            recFilter !== "all"
              ? "No reports match the selected recommendation filter."
              : "No candidate assessment reports have been generated yet."
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((r) => (
            <Card key={r.id} className="p-5">
              {/* Candidate info */}
              <div className="flex items-center gap-3">
                <Avatar size="default" name={r.candidate} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-text-primary truncate">
                    {r.candidate}
                  </p>
                  <p className="text-xs text-text-muted truncate">{r.job}</p>
                </div>
              </div>

              {/* Score + recommendation */}
              <div className="flex items-center justify-between mt-4">
                <div className="flex items-center gap-3">
                  <ScoreBadge score={r.score} size="lg" />
                  <div>
                    <p className="text-xs text-text-muted">Overall</p>
                    <p className="text-sm font-semibold text-text-primary">
                      {r.score}/100
                    </p>
                  </div>
                </div>
                <span
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-semibold",
                    REC_BADGE_STYLES[r.recommendation]
                  )}
                >
                  {getRecommendationLabel(r.recommendation)}
                </span>
              </div>

              <p className="text-xs text-text-muted mt-3">
                {formatDate(r.date)}
              </p>

              {/* Actions */}
              <div className="flex items-center gap-2 mt-4 pt-4 border-t border-border">
                <Button asChild size="sm" className="flex-1">
                  <Link href={`/admin/reports/${r.id}`}>View Report</Link>
                </Button>
                {r.pdfUrl && (
                  <Button asChild variant="secondary" size="sm" title="Download PDF Report">
                    <a href={r.pdfUrl} target="_blank" rel="noreferrer">
                      <Download className="h-4 w-4" />
                      <span className="sr-only">Download PDF Report</span>
                    </a>
                  </Button>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
