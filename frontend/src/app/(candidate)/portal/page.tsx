"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  GraduationCap,
  Briefcase,
  Building2,
  Calendar,
  Clock,
  Video,
  FileText,
  Check,
  AlertCircle,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ResumeDownloadButton } from "@/components/resume-download-button";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate, formatTime, cn } from "@/lib/utils";
import { useMyApplications } from "@/hooks/queries/useCandidates";
import { useRespondToInstantInterview } from "@/hooks/queries/useScheduling";
import type { BackendApplicationResponse } from "@/types/api";

const PIPELINE_STEPS = [
  { key: "applied", label: "Applied" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "scheduled", label: "Scheduled" },
  { key: "completed", label: "Completed" },
];

const STATUS_STEP_INDEX: Record<string, number> = {
  applied: 0,
  parsing: 0,
  shortlisted: 1,
  invited: 1,
  scheduled: 2,
  in_progress: 2,
  completed: 3,
  rejected: -1,
};

function CountdownTimer({ targetDate, expiredLabel = "Session Ready" }: { targetDate: string; expiredLabel?: string }) {
  const [timeLeft, setTimeLeft] = useState("");
  const [isImminent, setIsImminent] = useState(false);
  const [isExpired, setIsExpired] = useState(false);

  useEffect(() => {
    const calc = () => {
      const diff = new Date(targetDate).getTime() - Date.now();
      if (diff <= 0) {
        setTimeLeft(expiredLabel);
        setIsExpired(true);
        setIsImminent(false);
        return;
      }
      setIsExpired(false);
      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      const secs = Math.floor((diff % 60000) / 1000);

      setIsImminent(diff <= 300000); // 5 minutes or less

      if (days > 0) {
        setTimeLeft(`in ${days}d ${hours}h`);
      } else if (hours > 0) {
        setTimeLeft(`in ${hours}h ${mins}m`);
      } else if (mins > 0) {
        setTimeLeft(`in ${mins}m ${secs}s`);
      } else {
        setTimeLeft(`in ${secs}s`);
      }
    };

    calc();
    const intervalMs = new Date(targetDate).getTime() - Date.now() < 3600000 ? 1000 : 15000;
    const t = setInterval(calc, intervalMs);
    return () => clearInterval(t);
  }, [targetDate, expiredLabel]);

  return (
    <span
      className={cn(
        "text-xs font-semibold px-2 py-0.5 rounded-full inline-flex items-center gap-1",
        isExpired
          ? "text-error bg-error-light border border-error/30"
          : isImminent
          ? "text-success bg-success-light border border-success/30 animate-pulse"
          : "text-warning bg-warning-light border border-warning/30"
      )}
    >
      <Clock className="h-3 w-3" />
      {timeLeft}
    </span>
  );
}

function PipelineProgress({ status }: { status: string }) {
  const currentStep = STATUS_STEP_INDEX[status] ?? 0;
  const isRejected = status === "rejected";

  if (isRejected) {
    return (
      <p className="text-xs text-error font-medium">Application not selected</p>
    );
  }

  return (
    <div className="flex items-center gap-0">
      {PIPELINE_STEPS.map((step, i) => {
        const done = i < currentStep;
        const active = i === currentStep;
        const last = i === PIPELINE_STEPS.length - 1;

        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  "h-5 w-5 rounded-full flex items-center justify-center transition-colors",
                  done && "bg-brand text-white",
                  active && "bg-brand ring-2 ring-brand/30 ring-offset-1 text-white",
                  !done && !active && "bg-border text-transparent"
                )}
              >
                {done ? (
                  <Check className="h-2.5 w-2.5" strokeWidth={3} />
                ) : (
                  <div
                    className={cn(
                      "h-2 w-2 rounded-full",
                      active ? "bg-white" : "bg-text-muted/40"
                    )}
                  />
                )}
              </div>
              <span
                className={cn(
                  "text-[10px] leading-none whitespace-nowrap",
                  active
                    ? "text-brand font-semibold"
                    : done
                    ? "text-text-muted"
                    : "text-text-muted/60"
                )}
              >
                {step.label}
              </span>
            </div>
            {!last && (
              <div
                className={cn(
                  "h-px w-6 sm:w-10 mb-4 mx-0.5 transition-colors",
                  i < currentStep ? "bg-brand" : "bg-border"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function ApplicationCardSkeleton() {
  return (
    <Card className="animate-pulse">
      <CardContent className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="flex-1 space-y-3">
            <div className="h-5 bg-border/60 rounded w-1/3" />
            <div className="h-3.5 bg-border/40 rounded w-1/4" />
            <div className="h-4 bg-border/30 rounded w-1/2 pt-2" />
          </div>
          <div className="h-8 bg-border/50 rounded w-28 shrink-0" />
        </div>
      </CardContent>
    </Card>
  );
}

function ApplicationCard({ app }: { app: BackendApplicationResponse }) {
  const router = useRouter();
  const respondInstantMutation = useRespondToInstantInterview();
  const [instantExpired, setInstantExpired] = useState(false);
  const job = app.job || app.jobs;
  const jobTitle =
    job?.title ||
    (app as any).job_title ||
    app.current_role ||
    "Engineering Position";
  const department = job?.department || "General";
  const location = job?.location || "Remote";
  const company = (job as any)?.company || "Intra AI";
  const interviewTargetId = app.interview_id || app.id;

  // Candidate updated profile info (role and company)
  const currentRole = app.current_role || (app as any).role || "";
  const currentCompany = app.current_company || (app as any).company || "";
  const yearsExp = app.years_experience;
  const matchScore = typeof app.eligibility_score === "number" ? app.eligibility_score : null;
  const threshold = typeof job?.eligibility_threshold === "number" ? job.eligibility_threshold : 60;
  const recruiterReviewed =
    matchScore !== null &&
    matchScore < threshold &&
    (app.status === "shortlisted" || app.status === "invited");

  useEffect(() => {
    if (app.meeting_mode !== "instant" || app.instant_status !== "instant_pending" || !app.instant_deadline) {
      queueMicrotask(() => setInstantExpired(false));
      return;
    }
    const expiresAt = new Date(app.instant_deadline).getTime();
    const update = () => setInstantExpired(expiresAt <= Date.now());
    queueMicrotask(update);
    const remaining = expiresAt - Date.now();
    if (remaining <= 0) return;
    const timer = window.setTimeout(update, remaining + 50);
    return () => window.clearTimeout(timer);
  }, [app.meeting_mode, app.instant_status, app.instant_deadline]);

  const handleInstantResponse = async () => {
    try {
      const interview = await respondInstantMutation.mutateAsync(app.id);
      router.push(`/interview/${interview.id}/prep`);
    } catch {
      // The mutation error is rendered inline so the candidate can retry or
      // contact the recruiter when the ten-minute window has elapsed.
    }
  };

  return (
    <Card className="hover:border-brand/30 transition-colors">
      <CardContent className="p-5">
        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
          {/* Job info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2 mb-1">
              <div>
                <h3 className="text-base font-semibold text-text-primary leading-snug">
                  {jobTitle}
                </h3>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-text-muted">
                  <span className="font-medium text-brand">{company}</span>
                  <span className="text-text-muted/40">·</span>
                  <span>{department}</span>
                  <span className="text-text-muted/40">·</span>
                  <span>{location}</span>
                </div>
              </div>
              <StatusBadge status={app.status} className="shrink-0" />
            </div>

            {/* Candidate Submitted / Updated Experience */}
            {(currentRole || currentCompany) && (
              <div className="mt-2 inline-flex flex-wrap items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface-muted border border-border/70 text-xs">
                <Briefcase className="h-3.5 w-3.5 text-brand shrink-0" />
                <span className="text-text-muted">Profile:</span>
                <span className="font-semibold text-text-primary">
                  {currentRole || "Candidate"}
                </span>
                {currentCompany && (
                  <>
                    <span className="text-text-muted">at</span>
                    <span className="font-semibold text-text-primary">
                      {currentCompany}
                    </span>
                  </>
                )}
                {yearsExp != null && yearsExp > 0 && (
                  <span className="text-text-muted">
                    ({yearsExp} {yearsExp === 1 ? "yr" : "yrs"} exp)
                  </span>
                )}
              </div>
            )}

            <div className="flex items-center gap-3 mt-2.5">
              <p className="text-xs text-text-muted">
                Applied {formatDate(app.created_at)}
              </p>
              {matchScore !== null && (
                <span className="text-[11px] font-medium text-brand bg-brand-light/70 px-2 py-0.5 rounded-full">
                  {Math.round(matchScore)}% Automated Match
                </span>
              )}
            </div>

            {recruiterReviewed && (
              <div className="mt-2 flex items-start gap-1.5 text-[11px] text-warning">
                <AlertCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
                <span>
                  A recruiter approved your application. The automated match score is retained for transparency.
                </span>
              </div>
            )}

            {app.meeting_mode === "instant" && app.instant_status === "instant_pending" && app.instant_deadline && (
              <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
                <div className="flex flex-wrap items-center gap-2 font-semibold">
                  <AlertCircle className="h-3.5 w-3.5" />
                  Instant interview invitation · respond within 10 minutes
                  <CountdownTimer targetDate={app.instant_deadline} expiredLabel="Expired" />
                </div>
                <p className="mt-1 text-amber-800/80">
                  Accept now to enter the live AI interview immediately. The invitation closes when the timer reaches zero.
                </p>
                {respondInstantMutation.isError && (
                  <p className="mt-1 text-error">{respondInstantMutation.error.message}</p>
                )}
              </div>
            )}

            {app.meeting_mode === "instant" && app.instant_status === "instant_expired" && (
              <div className="mt-3 flex items-center gap-1.5 text-xs text-error">
                <AlertCircle className="h-3.5 w-3.5" />
                The instant interview invitation expired. Ask the recruiter to send another one.
              </div>
            )}

            {/* Pipeline */}
            <div className="mt-4">
              <PipelineProgress status={app.status} />
            </div>

            {/* Interview date + countdown */}
            {app.scheduled_at && (app.status === "scheduled" || app.status === "in_progress") && (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <div className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Calendar className="h-3.5 w-3.5 text-brand" />
                  <span>
                    {formatDate(app.scheduled_at)} at {formatTime(app.scheduled_at)}
                  </span>
                </div>
                <CountdownTimer targetDate={app.scheduled_at} />
              </div>
            )}

            {/* Interview rounds overview */}
            {job?.interview_rounds && job.interview_rounds.length > 0 && (
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {job.interview_rounds.map((r, i) => (
                  <span
                    key={r.id || i}
                    className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-brand-light/60 text-brand border border-brand/20"
                  >
                    Round {i + 1}: {r.type.replace("_", " ")} ({r.duration_minutes}m)
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Action button */}
          <div className="flex items-center gap-2 sm:flex-col sm:items-end shrink-0 pt-2 sm:pt-0">
            {app.resume_url && <ResumeDownloadButton applicationId={app.id} resumeUrl={app.resume_url} />}
            {app.status === "shortlisted" && (
              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-text-muted bg-surface-muted border border-border rounded-md px-2.5 py-1.5">
                <Clock className="h-3.5 w-3.5 text-brand" />
                Awaiting invitation
              </span>
            )}

            {app.status === "invited" && (
              app.meeting_mode === "instant" && app.instant_status === "instant_pending" && !instantExpired ? (
                <Button
                  size="sm"
                  className="bg-amber-600 hover:bg-amber-700 text-white shadow-xs w-full sm:w-auto"
                  onClick={handleInstantResponse}
                  disabled={respondInstantMutation.isPending}
                >
                  {respondInstantMutation.isPending ? <RefreshCw className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <Video className="h-3.5 w-3.5 mr-1.5" />}
                  Accept & Join Now
                </Button>
              ) : (
                <span className="inline-flex items-center gap-1.5 text-xs font-medium text-text-muted bg-surface-muted border border-border rounded-md px-2.5 py-1.5">
                  <Clock className="h-3.5 w-3.5 text-brand" />
                  {app.meeting_mode === "instant" && app.instant_status === "instant_pending" && instantExpired
                    ? "Instant invitation expired"
                    : "Awaiting recruiter schedule"}
                </span>
              )
            )}

            {app.status === "scheduled" && (
              <div className="flex flex-col items-end gap-1.5 w-full sm:w-auto">
                <Button asChild size="sm" className="bg-brand hover:bg-brand-hover text-white shadow-xs w-full sm:w-auto">
                  <Link href={`/interview/${interviewTargetId}/prep`}>
                    <Video className="h-3.5 w-3.5 mr-1.5" />
                    Prepare for Interview
                  </Link>
                </Button>
                <span className="text-[11px] text-text-muted">Scheduled by the hiring team</span>
              </div>
            )}

            {app.status === "in_progress" && (
              <Button asChild size="sm" className="bg-brand hover:bg-brand-hover">
                <Link href={`/interview/${interviewTargetId}`}>
                  <Video className="h-3.5 w-3.5 mr-1.5" />
                  Resume Interview
                </Link>
              </Button>
            )}

            {app.status === "completed" && (
              <Button asChild variant="secondary" size="sm">
                <Link href={`/interview/${interviewTargetId}/report`}>
                  <FileText className="h-3.5 w-3.5 mr-1.5" />
                  View Report
                </Link>
              </Button>
            )}

            {(app.status === "applied" || app.status === "parsing") && (
              <span className="text-xs text-text-muted bg-surface-muted px-2.5 py-1 rounded-md border border-border">
                Application Under Review
              </span>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function CandidatePortalPage() {
  const { data, isLoading, isError, error, refetch } = useMyApplications();
  const applications = data?.applications ?? [];

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">
            My Applications
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Track your interview pipeline and take action
          </p>
        </div>
        <div>
          <Button asChild variant="secondary" size="sm">
            <Link href="/jobs" className="flex items-center gap-1.5">
              Browse Open Positions
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </div>

      <Card className="mb-6 border-brand/20 bg-brand-light">
        <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex gap-3"><GraduationCap className="h-6 w-6 text-brand shrink-0 mt-1" /><div><h2 className="font-semibold text-text-primary">Interview Preparation</h2><p className="mt-1 text-sm text-text-muted">Practice your interview with Taylor. This training does not affect your official interview score.</p></div></div>
          <Button asChild className="shrink-0"><Link href="/training">Start Training <ArrowRight className="h-4 w-4" /></Link></Button>
        </CardContent>
      </Card>

      {/* Error state */}
      {isError && (
        <div className="mb-6 p-4 rounded-xl border border-error/30 bg-error-light flex items-center justify-between gap-3 text-sm text-error">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>
              {error?.message || "Failed to load applications. Please try again."}
            </span>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refetch()}
            className="border-error/40 text-error hover:bg-error-light shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            Retry
          </Button>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[
          {
            label: "Total Applied",
            value: applications.length,
            color: "text-text-primary",
          },
          {
            label: "Shortlisted & Invited",
            value: applications.filter((a) =>
              ["shortlisted", "invited"].includes(a.status)
            ).length,
            color: "text-brand",
          },
          {
            label: "Interview Scheduled",
            value: applications.filter((a) =>
              ["scheduled", "in_progress"].includes(a.status)
            ).length,
            color: "text-purple-600",
          },
          {
            label: "Completed",
            value: applications.filter((a) => a.status === "completed").length,
            color: "text-success",
          },
        ].map((stat) => (
          <div
            key={stat.label}
            className="bg-surface border border-border rounded-lg p-4 shadow-2xs"
          >
            <p className={cn("text-2xl font-bold", stat.color)}>
              {isLoading ? "-" : stat.value}
            </p>
            <p className="text-xs text-text-muted mt-0.5">{stat.label}</p>
          </div>
        ))}
      </div>

      {/* Applications list */}
      {isLoading ? (
        <div className="flex flex-col gap-3">
          <ApplicationCardSkeleton />
          <ApplicationCardSkeleton />
        </div>
      ) : applications.length === 0 ? (
        <Card>
          <EmptyState
            icon={Briefcase}
            title="No applications yet"
            description="Browse open positions and apply. Your applications and scheduled interviews will appear here."
            action={
              <Button asChild>
                <Link href="/jobs">Browse Open Positions</Link>
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {applications.map((app) => (
            <ApplicationCard key={app.id} app={app} />
          ))}
        </div>
      )}
    </div>
  );
}
