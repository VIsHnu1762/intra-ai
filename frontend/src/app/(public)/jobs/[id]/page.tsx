"use client";

import { use, useMemo } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  MapPin,
  Briefcase,
  Clock,
  IndianRupee,
  GraduationCap,
  MessageSquare,
  Users,
  Handshake,
  Code2,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/loading";
import { usePublicJob } from "@/hooks/queries/useJobs";
import { ApiError } from "@/lib/api/client";
import type { InterviewRoundConfig } from "@/types";

// ─── Round Meta Mapping (Candidate-Facing, Privacy-Preserving) ────────────────

interface RoundPresentationMeta {
  label: string;
  defaultDesc: string;
  icon: typeof MessageSquare;
}

const ROUND_TYPE_META: Record<string, RoundPresentationMeta> = {
  introduction: {
    label: "Introduction & Background",
    defaultDesc:
      "Discussion of your professional journey, technical background, and what excites you about this role.",
    icon: MessageSquare,
  },
  technical: {
    label: "Technical Assessment",
    defaultDesc:
      "Adaptive technical evaluation and domain problem-solving tailored to role requirements.",
    icon: Code2,
  },
  behavioral: {
    label: "Behavioral & Situational Assessment",
    defaultDesc:
      "Structured evaluation of collaboration, leadership, conflict resolution, and ownership.",
    icon: Users,
  },
  hr_culture: {
    label: "Culture Fit & Alignment",
    defaultDesc:
      "Role expectations, workplace preferences, compensation alignment, and candidate Q&A.",
    icon: Handshake,
  },
};

function getRoundMeta(type: string): RoundPresentationMeta {
  const normalized = (type || "").toLowerCase().replace(/[-_]/g, "_");
  if (ROUND_TYPE_META[normalized]) {
    return ROUND_TYPE_META[normalized];
  }
  const formatted = type
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    label: formatted,
    defaultDesc: "Comprehensive evaluation round conducted by our adaptive AI platform.",
    icon: MessageSquare,
  };
}

const TYPE_BADGE: Record<string, "success" | "default" | "outline"> = {
  remote: "success",
  hybrid: "default",
  onsite: "outline",
};

function formatRelativeDate(dateStr?: string): string {
  if (!dateStr) return "Recently";
  try {
    const timestamp = new Date(dateStr).getTime();
    if (isNaN(timestamp)) return "Recently";
    const diffDays = Math.floor((Date.now() - timestamp) / (1000 * 60 * 60 * 24));
    if (diffDays <= 0) return "Today";
    if (diffDays === 1) return "1 day ago";
    return `${diffDays} days ago`;
  } catch {
    return "Recently";
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: job, isLoading, isError, error, refetch } = usePublicJob(id);

  // Check for 404 status
  const isNotFound = useMemo(() => {
    if (!isError) return false;
    if (error instanceof ApiError && error.status === 404) return true;
    if ((error as { status?: number })?.status === 404) return true;
    if (error?.message?.toLowerCase().includes("not found")) return true;
    return false;
  }, [isError, error]);

  // Format salary
  const formattedSalary = useMemo(() => {
    if (!job) return "Competitive Compensation";
    if (job.salary_min && job.salary_max) {
      return `₹${job.salary_min}–${job.salary_max} LPA`;
    }
    if (job.salary_min) return `₹${job.salary_min} LPA+`;
    if (job.salary_max) return `Up to ₹${job.salary_max} LPA`;
    return "Competitive Compensation";
  }, [job]);

  // Format posted date
  const formattedPostedDate = formatRelativeDate(job?.created_at);

  // Sort and filter active interview rounds by order_index
  const interviewRounds = job?.interview_rounds;
  const sortedRounds = useMemo(() => {
    if (!interviewRounds) return [];
    return [...interviewRounds]
      .filter((r: InterviewRoundConfig) => r.enabled !== false)
      .sort(
        (a: InterviewRoundConfig, b: InterviewRoundConfig) =>
          (a.order_index ?? 0) - (b.order_index ?? 0)
      );
  }, [interviewRounds]);

  const totalInterviewMinutes = useMemo(() => {
    return sortedRounds.reduce(
      (acc: number, r: InterviewRoundConfig) => acc + (r.duration_minutes || 0),
      0
    );
  }, [sortedRounds]);

  // ─── 404 Not Found State ───────────────────────────────────────────────────
  if (isNotFound) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-24 text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-brand/10 text-brand">
          <Briefcase className="h-8 w-8" />
        </div>
        <h1 className="text-2xl font-bold text-text-primary">Position Not Found</h1>
        <p className="mt-2 text-sm text-text-muted max-w-md mx-auto">
          This job opportunity may have been closed, archived, or does not exist.
        </p>
        <div className="mt-6 flex justify-center">
          <Button asChild>
            <Link href="/jobs" className="inline-flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              Back to all positions
            </Link>
          </Button>
        </div>
      </div>
    );
  }

  // ─── General Error State ───────────────────────────────────────────────────
  if (isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <div className="rounded-xl border border-danger/30 bg-danger/10 p-6 text-danger flex items-start gap-4">
          <AlertCircle className="h-6 w-6 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h2 className="text-base font-semibold">Unable to Load Position Details</h2>
            <p className="text-sm text-danger/80 mt-1">
              {error?.message ||
                "An unexpected network error occurred while fetching this position. Please try again."}
            </p>
            <div className="mt-4 flex items-center gap-3">
              <Button variant="secondary" size="sm" onClick={() => refetch()}>
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                Retry
              </Button>
              <Button asChild variant="ghost" size="sm">
                <Link href="/jobs">Return to Listings</Link>
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ─── Loading Skeleton State ────────────────────────────────────────────────
  if (isLoading || !job) {
    return (
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-10">
        <div className="mb-6">
          <Skeleton className="h-5 w-36" />
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Main skeleton */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            <Card>
              <CardContent className="p-6 flex flex-col gap-3">
                <Skeleton className="h-8 w-3/4" />
                <div className="flex gap-2 pt-1">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-4 w-20" />
                </div>
                <div className="flex gap-3 pt-2">
                  <Skeleton className="h-6 w-18 rounded-full" />
                  <Skeleton className="h-6 w-28" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6 flex items-center gap-4">
                <Skeleton className="h-12 w-12 rounded-lg shrink-0" />
                <div className="flex-1 flex flex-col gap-2">
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-3 w-3/4" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <Skeleton className="h-5 w-32" />
              </CardHeader>
              <CardContent className="pt-2 flex flex-col gap-2.5">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-11/12" />
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-4 w-3/4" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <Skeleton className="h-5 w-32" />
              </CardHeader>
              <CardContent className="pt-2 flex flex-col gap-3">
                <Skeleton className="h-14 w-full rounded-lg" />
                <Skeleton className="h-14 w-full rounded-lg" />
                <Skeleton className="h-14 w-full rounded-lg" />
              </CardContent>
            </Card>
          </div>

          {/* Sidebar skeleton */}
          <div className="lg:col-span-1">
            <Card>
              <CardContent className="p-6 flex flex-col gap-4">
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-7 w-32" />
                <div className="h-px bg-border my-2" />
                <div className="flex flex-col gap-3">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-full" />
                </div>
                <Skeleton className="h-11 w-full rounded-full mt-4" />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  const jobTypeKey = (job.job_type || "remote").toLowerCase();

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-10">
      {/* Back link */}
      <Link
        href="/jobs"
        className="inline-flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary transition-colors mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to all positions
      </Link>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Title card */}
          <Card>
            <CardContent className="p-6">
              <h1 className="text-2xl font-bold text-text-primary">{job.title}</h1>

              {/* Tags row */}
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-sm text-text-muted">
                  <Briefcase className="h-4 w-4" />
                  {job.department}
                </span>
                <span className="text-border">·</span>
                <span className="inline-flex items-center gap-1.5 text-sm text-text-muted">
                  <MapPin className="h-4 w-4" />
                  {job.location}
                </span>
                <span className="text-border">·</span>
                <span className="inline-flex items-center gap-1.5 text-sm text-text-muted">
                  <GraduationCap className="h-4 w-4" />
                  {job.experience_min}–{job.experience_max} years exp
                </span>
                <span className="text-border">·</span>
                <span className="inline-flex items-center gap-1.5 text-sm text-text-muted">
                  <Clock className="h-4 w-4" />
                  Posted {formattedPostedDate}
                </span>
              </div>

              {/* Type + salary */}
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <Badge
                  variant={TYPE_BADGE[jobTypeKey] ?? "default"}
                  className="uppercase text-[11px] tracking-wide"
                >
                  {job.job_type}
                </Badge>
                <span className="inline-flex items-center gap-0.5 text-sm font-semibold text-text-primary">
                  <IndianRupee className="h-3.5 w-3.5" />
                  {formattedSalary}
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Company info (Intra AI) */}
          <Card>
            <CardContent className="p-6 flex items-center gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-brand text-white font-bold text-lg shadow-sm">
                I
              </div>
              <div>
                <p className="text-sm font-semibold text-text-primary">Intra AI</p>
                <p className="text-xs text-text-muted mt-0.5">
                  Adaptive Multi-Agent AI Voice Interview Platform · Enterprise Intelligence
                </p>
              </div>
            </CardContent>
          </Card>

          {/* About this role / Description */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">About this role</CardTitle>
            </CardHeader>
            <CardContent className="pt-2">
              <div className="text-sm text-text-muted leading-relaxed whitespace-pre-line">
                {job.description}
              </div>
            </CardContent>
          </Card>

          {/* Required Skills */}
          {job.required_skills && job.required_skills.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Required Skills & Competencies</CardTitle>
              </CardHeader>
              <CardContent className="pt-2 flex flex-wrap gap-2">
                {job.required_skills.map((skill: string) => (
                  <Badge key={skill} variant="outline" className="bg-bg/50 text-xs">
                    {skill}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Dynamic Interview Process (P4-004) */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Interview Process</CardTitle>
            </CardHeader>
            <CardContent className="pt-2">
              {sortedRounds.length === 0 ? (
                <p className="text-sm text-text-muted">
                  Interview process details and evaluation stages will be shared upon application review.
                </p>
              ) : (
                <>
                  <p className="text-xs text-text-muted mb-5">
                    Our adaptive AI interview agents conduct all rounds automatically
                    {totalInterviewMinutes > 0 && ` — total estimated duration ~${totalInterviewMinutes} min`}.
                  </p>
                  <div className="flex flex-col gap-4">
                    {sortedRounds.map((round: InterviewRoundConfig, i: number) => {
                      const meta = getRoundMeta(round.type);
                      const Icon = meta.icon;
                      return (
                        <div
                          key={round.id || `${round.type}-${i}`}
                          className="flex items-start gap-3.5 group rounded-lg border border-border/60 bg-surface/40 p-4 transition-colors hover:border-brand/40"
                        >
                          {/* Step number */}
                          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-bold text-brand">
                            {i + 1}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-2">
                                <Icon className="h-4 w-4 text-brand shrink-0" />
                                <span className="text-sm font-semibold text-text-primary">
                                  {meta.label}
                                </span>
                              </div>
                              <span className="text-xs text-text-muted font-medium shrink-0">
                                {round.duration_minutes} min
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-text-muted leading-relaxed">
                              {meta.defaultDesc}
                            </p>
                            {round.focus_areas && round.focus_areas.length > 0 && (
                              <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                                <span className="text-[11px] text-text-muted font-medium">Focus:</span>
                                {round.focus_areas.map((area: string, idx: number) => (
                                  <span
                                    key={idx}
                                    className="inline-flex items-center rounded-md bg-bg/70 px-2 py-0.5 text-[11px] font-medium text-text-secondary border border-border/80"
                                  >
                                    {area}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar CTA */}
        <div className="lg:col-span-1">
          <div className="sticky top-24">
            <Card>
              <CardContent className="p-6 flex flex-col gap-4">
                <div>
                  <p className="text-xs text-text-muted uppercase tracking-wide font-medium">
                    Compensation
                  </p>
                  <p className="mt-1 text-xl font-bold text-text-primary">
                    {formattedSalary}
                  </p>
                </div>

                <div className="h-px bg-border" />

                <div className="flex flex-col gap-2.5 text-sm text-text-muted">
                  <div className="flex justify-between">
                    <span>Location</span>
                    <span className="font-medium text-text-primary">{job.location}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Workplace</span>
                    <span className="font-medium text-text-primary capitalize">{job.job_type}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Experience</span>
                    <span className="font-medium text-text-primary">
                      {job.experience_min}–{job.experience_max} yrs
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span>Department</span>
                    <span className="font-medium text-text-primary">{job.department}</span>
                  </div>
                  {job.education && (
                    <div className="flex justify-between">
                      <span>Education</span>
                      <span className="font-medium text-text-primary">{job.education}</span>
                    </div>
                  )}
                  {totalInterviewMinutes > 0 && (
                    <div className="flex justify-between">
                      <span>Interview Time</span>
                      <span className="font-medium text-text-primary">~{totalInterviewMinutes} min</span>
                    </div>
                  )}
                </div>

                <div className="h-px bg-border" />

                <Button asChild size="lg" className="w-full">
                  <Link href={`/jobs/${job.id}/apply`}>Apply for this Position</Link>
                </Button>

                <p className="text-center text-xs text-text-muted">
                  Takes ~5 min · AI interview scheduled after shortlisting
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
