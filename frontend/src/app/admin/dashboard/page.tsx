"use client";

import Link from "next/link";
import {
  Briefcase,
  Users,
  Video,
  TrendingUp,
  ArrowUpRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/ui/avatar";
import { ScoreBadge } from "@/components/ui/score-badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { Progress } from "@/components/ui/progress";
import { formatDate, cn } from "@/lib/utils";

import { useAuth } from "@/context/AuthContext";
import { useSidebar } from "@/components/layout/admin-layout";
import { useJobs } from "@/hooks/queries/useJobs";
import { useCandidates } from "@/hooks/queries/useCandidates";
import { useInterviews } from "@/hooks/queries/useScheduling";

export default function DashboardPage() {
  const { user } = useAuth();
  const { collapsed } = useSidebar();
  const { data: jobsData } = useJobs();
  const { data: candidatesData } = useCandidates();
  const { data: interviewsData } = useInterviews();

  const activeJobs = jobsData?.jobs?.filter((j) => j.status === "published").length ?? (jobsData?.total ?? 0);
  const totalCandidates = candidatesData?.total ?? 0;
  const interviewsList = interviewsData?.interviews ?? [];
  const totalInterviews = interviewsData?.total ?? interviewsList.length;

  // Compute average score from candidates who have an eligibility score
  const scores = (candidatesData?.candidates ?? [])
    .flatMap((c) => c.applications?.map((a) => a.eligibility_score) ?? [])
    .filter((s): s is number => typeof s === "number" && s > 0);
  const avgScore = scores.length > 0 ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 78;

  const STATS = [
    {
      label: "Active Jobs",
      value: String(activeJobs),
      trend: `${jobsData?.total ?? 0} total postings`,
      icon: Briefcase,
      iconBg: "bg-brand-light",
      iconColor: "text-brand",
    },
    {
      label: "Total Candidates",
      value: String(totalCandidates),
      trend: "+100% live synchronized",
      icon: Users,
      iconBg: "bg-success-light",
      iconColor: "text-success",
    },
    {
      label: "Interviews Scheduled",
      value: String(totalInterviews),
      trend: `${interviewsList.filter((i) => i.status === "completed").length} completed`,
      icon: Video,
      iconBg: "bg-warning-light",
      iconColor: "text-warning",
    },
    {
      label: "Average Score",
      value: `${avgScore}/100`,
      trend: "Adaptive AI screened",
      icon: TrendingUp,
      iconBg: "bg-brand-light",
      iconColor: "text-brand",
    },
  ];

  // Map real recent interviews
  const recentInterviews = interviewsList.slice(0, 8).map((iv) => {
    return {
      id: iv.id,
      candidate: iv.candidate?.name || "Candidate",
      job: iv.job?.title || "Role Interview",
      status: iv.status || "scheduled",
      score: 0,
      date: iv.scheduled_at ? iv.scheduled_at.split("T")[0] : "2026-09-10",
    };
  });

  // Calculate pipeline counts from candidates
  const allApps = (candidatesData?.candidates ?? []).flatMap((c) => c.applications ?? []);
  const appliedCount = allApps.filter((a) => a.status === "applied" || a.status === "parsing").length || totalCandidates;
  const shortlistedCount = allApps.filter((a) => a.status === "shortlisted" || a.status === "invited").length;
  const scheduledCount = allApps.filter((a) => a.status === "scheduled").length || totalInterviews;
  const inProgressCount = allApps.filter((a) => a.status === "in_progress").length;
  const completedCount = allApps.filter((a) => a.status === "completed").length;
  const totalPipeline = Math.max(1, appliedCount + shortlistedCount + scheduledCount + inProgressCount + completedCount);

  const PIPELINE = [
    { label: "Applied", count: appliedCount, total: totalPipeline, color: "bg-text-muted" },
    { label: "Shortlisted", count: shortlistedCount, total: totalPipeline, color: "bg-brand" },
    { label: "Scheduled", count: scheduledCount, total: totalPipeline, color: "bg-warning" },
    { label: "In Progress", count: inProgressCount, total: totalPipeline, color: "bg-brand" },
    { label: "Completed", count: completedCount, total: totalPipeline, color: "bg-success" },
  ];

  const userName = user?.name ? user.name.split(" ")[0] : "Recruiter";

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
          <p className="text-sm text-text-muted mt-0.5">
            Welcome back, {userName}. Here&apos;s what&apos;s happening across your recruiting pipelines.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button asChild variant="secondary" size="sm">
            <Link href="/admin/candidates">View Candidates</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/admin/jobs/new">Post New Job</Link>
          </Button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {STATS.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text-muted">{stat.label}</p>
                    <p className="text-2xl font-bold text-text-primary mt-1">
                      {stat.value}
                    </p>
                    <p className="text-xs text-text-muted mt-1 flex items-center gap-1">
                      <ArrowUpRight className="h-3 w-3 text-success" />
                      {stat.trend}
                    </p>
                  </div>
                  <div
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${stat.iconBg}`}
                  >
                    <Icon className={`h-5 w-5 ${stat.iconColor}`} />
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div
        className="grid grid-cols-1 lg:grid-cols-12 gap-6 transition-all duration-300"
      >
        {/* Recent Activity table */}
        <Card
          className={cn(
            "transition-all duration-300 overflow-hidden",
            collapsed
              ? "lg:col-span-8"
              : "lg:col-span-9"
          )}
        >
          <CardHeader className="p-5 pb-4">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Recent Activity</CardTitle>
                <p className="text-xs text-text-muted mt-0.5">
                  Latest candidate interview evaluations and live statuses
                </p>
              </div>
              <Link
                href="/admin/interviews"
                className="text-sm text-brand hover:text-brand-hover font-medium shrink-0"
              >
                View all
              </Link>
            </div>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full table-fixed min-w-[510px]">
              <thead>
                <tr className="border-t border-border bg-surface-muted/40">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-text-muted uppercase tracking-wide w-[28%] min-w-[140px]">
                    Candidate
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-text-muted uppercase tracking-wide w-[26%] min-w-[125px] hidden sm:table-cell">
                    Job Title
                  </th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-text-muted uppercase tracking-wide w-[18%] min-w-[95px]">
                    Status
                  </th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-text-muted uppercase tracking-wide w-[13%] min-w-[65px]">
                    Score
                  </th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-text-muted uppercase tracking-wide w-[15%] min-w-[85px] hidden md:table-cell">
                    Date
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {recentInterviews.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-5 py-8 text-center text-sm text-text-muted"
                    >
                      No interviews conducted or scheduled yet.
                    </td>
                  </tr>
                ) : (
                  recentInterviews.map((row) => (
                    <tr
                      key={row.id}
                      className="hover:bg-bg transition-colors duration-100"
                    >
                      <td className="px-5 py-3 text-left">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <Avatar size="sm" name={row.candidate} className="shrink-0" />
                          <span
                            className="text-sm font-medium text-text-primary truncate"
                            title={row.candidate}
                          >
                            {row.candidate}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-left hidden sm:table-cell">
                        <span
                          className="text-sm text-text-muted truncate block"
                          title={row.job}
                        >
                          {row.job}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-left">
                        <StatusBadge status={row.status} className="shrink-0 inline-flex" />
                      </td>
                      <td className="px-3 py-3 text-center">
                        {row.score > 0 ? (
                          <ScoreBadge score={row.score} size="sm" />
                        ) : (
                          <span className="text-xs text-text-muted font-mono">—</span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-right hidden md:table-cell">
                        <span className="text-sm text-text-muted whitespace-nowrap">
                          {formatDate(row.date)}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Pipeline summary */}
        <Card
          className={cn(
            "transition-all duration-300",
            collapsed
              ? "lg:col-span-4"
              : "lg:col-span-3"
          )}
        >
          <CardHeader className="p-5 pb-4">
            <CardTitle>Hiring Pipeline</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 space-y-4">
            {PIPELINE.map((stage) => (
              <div key={stage.label}>
                <div className="flex items-center justify-between mb-1.5 gap-2">
                  <span className="text-sm text-text-primary truncate">
                    {stage.label}
                  </span>
                  <span className="text-sm font-semibold text-text-primary tabular-nums shrink-0">
                    {stage.count}
                  </span>
                </div>
                <Progress
                  value={(stage.count / stage.total) * 100}
                />
              </div>
            ))}
            <div className="pt-2 border-t border-border">
              <p className="text-xs text-text-muted">
                {totalPipeline} candidates tracked across active pipelines
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
