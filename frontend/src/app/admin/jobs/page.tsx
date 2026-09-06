"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, MapPin, Users, MoreHorizontal, Pencil, Archive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/empty-state";
import { formatDate } from "@/lib/utils";
import type { JobStatus } from "@/types";
import { useJobs, useArchiveJob } from "@/hooks/queries/useJobs";

const TABS: { key: JobStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "published", label: "Published" },
  { key: "draft", label: "Draft" },
  { key: "closed", label: "Closed" },
  { key: "archived", label: "Archived" },
];

const JOB_TYPE_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
};

export default function JobsPage() {
  const [activeTab, setActiveTab] = useState<JobStatus | "all">("all");
  const { data, isLoading } = useJobs();
  const archiveJobMutation = useArchiveJob();

  const allJobs = data?.jobs || [];
  const filtered =
    activeTab === "all"
      ? allJobs
      : allJobs.filter((j) => j.status === activeTab);

  const counts = TABS.reduce<Record<string, number>>((acc, t) => {
    acc[t.key] =
      t.key === "all"
        ? allJobs.length
        : allJobs.filter((j) => j.status === t.key).length;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Jobs</h1>
          <p className="text-sm text-text-muted mt-0.5">
            Manage your job postings and track applicants.
          </p>
        </div>
        <Button asChild size="sm">
          <Link href="/admin/jobs/new">
            <Plus className="h-4 w-4" />
            Post New Job
          </Link>
        </Button>
      </div>

      {/* Filter tabs */}
      <div className="flex border-b border-border gap-0 overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={[
              "relative px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors duration-150 border-b-2 -mb-px",
              activeTab === tab.key
                ? "border-brand text-brand"
                : "border-transparent text-text-muted hover:text-text-primary",
            ].join(" ")}
          >
            {tab.label}
            <span
              className={[
                "ml-1.5 inline-flex items-center justify-center rounded-full px-1.5 py-0.5 text-xs font-medium min-w-[20px]",
                activeTab === tab.key
                  ? "bg-brand text-white"
                  : "bg-border text-text-muted",
              ].join(" ")}
            >
              {counts[tab.key]}
            </span>
          </button>
        ))}
      </div>

      {/* Desktop table */}
      {isLoading ? (
        <div className="py-16 text-center text-sm text-text-muted">
          Loading jobs...
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No jobs found"
          description="No jobs match the selected filter."
        />
      ) : (
        <>
          {/* Table — desktop */}
          <Card className="hidden md:block overflow-hidden">
            <table className="w-full">
              <thead className="border-b border-border">
                <tr>
                  {["Job Title", "Department", "Location", "Applications", "Status", "Posted", ""].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left px-5 py-3 text-xs font-medium text-text-muted uppercase tracking-wide"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((job) => (
                  <tr
                    key={job.id}
                    className="hover:bg-bg transition-colors duration-100"
                  >
                    <td className="px-5 py-4">
                      <Link
                        href={`/admin/jobs/${job.id}`}
                        className="text-sm font-semibold text-text-primary hover:text-brand transition-colors duration-100"
                      >
                        {job.title}
                      </Link>
                      <p className="text-xs text-text-muted mt-0.5">
                        {JOB_TYPE_LABELS[job.job_type] || job.job_type}
                      </p>
                    </td>
                    <td className="px-5 py-4 text-sm text-text-muted">
                      {job.department}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-1.5 text-sm text-text-muted">
                        <MapPin className="h-3.5 w-3.5 shrink-0" />
                        {job.location}
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-1.5 text-sm text-text-muted">
                        <Users className="h-3.5 w-3.5 shrink-0" />
                        {job.applications_count ?? 0}
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-5 py-4 text-sm text-text-muted">
                      {formatDate(job.created_at)}
                    </td>
                    <td className="px-5 py-4">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button className="flex h-8 w-8 items-center justify-center rounded-md text-text-muted hover:bg-border hover:text-text-primary transition-colors duration-100">
                            <MoreHorizontal className="h-4 w-4" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link href={`/admin/jobs/${job.id}`}>
                              <Users className="h-4 w-4" />
                              View Applicants
                            </Link>
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            destructive
                            onClick={() => {
                              if (confirm(`Are you sure you want to archive "${job.title}"?`)) {
                                archiveJobMutation.mutate(job.id);
                              }
                            }}
                          >
                            <Archive className="h-4 w-4" />
                            Archive
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          {/* Cards — mobile */}
          <div className="grid gap-3 md:hidden">
            {filtered.map((job) => (
              <Card key={job.id} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <Link
                      href={`/admin/jobs/${job.id}`}
                      className="text-sm font-semibold text-text-primary hover:text-brand"
                    >
                      {job.title}
                    </Link>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
                      <span className="text-xs text-text-muted">{job.department}</span>
                      <span className="flex items-center gap-1 text-xs text-text-muted">
                        <MapPin className="h-3 w-3" />
                        {job.location}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-text-muted">
                        <Users className="h-3 w-3" />
                        {job.applications_count ?? 0} applicants
                      </span>
                    </div>
                  </div>
                  <StatusBadge status={job.status} />
                </div>
                <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
                  <span className="text-xs text-text-muted">
                    Posted {formatDate(job.created_at)}
                  </span>
                  <div className="flex gap-2">
                    <Button asChild variant="ghost" size="sm">
                      <Link href={`/admin/jobs/${job.id}`}>View</Link>
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
