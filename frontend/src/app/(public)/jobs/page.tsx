"use client";

import { useState, useMemo, useEffect } from "react";
import Link from "next/link";
import { Search, MapPin, Briefcase, Clock, AlertCircle, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/loading";
import { usePublicJobs } from "@/hooks/queries/useJobs";
import type { BackendJobResponse } from "@/types/api";
import { cn } from "@/lib/utils";

type JobTypeFilter = "All" | "Remote" | "Hybrid" | "Onsite";

const PRESET_DEPARTMENTS = [
  "All Departments",
  "Engineering",
  "AI Research",
  "Product",
  "Design",
  "Infrastructure",
  "Marketing",
  "Sales",
  "Operations",
];

const JOB_TYPES: JobTypeFilter[] = ["All", "Remote", "Hybrid", "Onsite"];

const TYPE_BADGE: Record<string, "success" | "default" | "outline"> = {
  remote: "success",
  hybrid: "default",
  onsite: "outline",
};

export default function JobsPage() {
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [department, setDepartment] = useState("All Departments");
  const [jobType, setJobType] = useState<JobTypeFilter>("All");
  const [page, setPage] = useState(1);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Query live public jobs
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = usePublicJobs({
    page,
    per_page: 24,
    search: debouncedSearch || undefined,
    department: department !== "All Departments" ? department : undefined,
  });

  const jobs = useMemo(() => data?.jobs ?? [], [data?.jobs]);

  // Additional client filter for job type (if backend doesn't filter job_type param)
  const filteredJobs = useMemo(() => {
    if (jobType === "All") return jobs;
    return jobs.filter(
      (j) => j.job_type.toLowerCase() === jobType.toLowerCase()
    );
  }, [jobs, jobType]);

  // Collect available departments dynamically
  const departments = useMemo(() => {
    const dynamicDepts = Array.from(new Set(jobs.map((j) => j.department).filter(Boolean)));
    const combined = Array.from(new Set([...PRESET_DEPARTMENTS, ...dynamicDepts]));
    return combined;
  }, [jobs]);

  const handleClearFilters = () => {
    setSearchInput("");
    setDebouncedSearch("");
    setDepartment("All Departments");
    setJobType("All");
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-10">
      {/* Header */}
      <div className="mb-8 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-text-primary">
            Explore Open Positions
          </h1>
          <p className="mt-1.5 text-base text-text-muted">
            Find your next role powered by Intra AI&apos;s adaptive multi-agent evaluation platform
          </p>
        </div>
        {isFetching && !isLoading && (
          <span className="text-xs text-text-muted flex items-center gap-1.5">
            <RefreshCw className="h-3.5 w-3.5 animate-spin text-brand" />
            Updating listings...
          </span>
        )}
      </div>

      {/* Filter bar */}
      <div className="mb-8 flex flex-col gap-4">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Search */}
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted pointer-events-none" />
            <input
              type="search"
              placeholder="Search by role title, keyword, or skill..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className={cn(
                "h-11 w-full rounded-lg border border-input-border bg-surface pl-9 pr-4 text-sm text-text-primary placeholder:text-text-muted",
                "focus:border-brand focus:ring-2 focus:ring-brand/20 focus:outline-none transition-colors"
              )}
            />
          </div>

          {/* Department */}
          <select
            value={department}
            onChange={(e) => {
              setDepartment(e.target.value);
              setPage(1);
            }}
            className={cn(
              "h-11 rounded-lg border border-input-border bg-surface px-3.5 text-sm text-text-primary",
              "focus:border-brand focus:ring-2 focus:ring-brand/20 focus:outline-none transition-colors",
              "sm:w-56"
            )}
          >
            {departments.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>

        {/* Job type pills */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-text-muted font-medium uppercase tracking-wider">
            Workplace:
          </span>
          {JOB_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => setJobType(t)}
              className={cn(
                "rounded-full px-3.5 py-1 text-xs font-medium transition-colors duration-150 cursor-pointer",
                jobType === t
                  ? "bg-brand text-white shadow-xs"
                  : "bg-surface border border-border text-text-muted hover:text-text-primary hover:border-brand/40"
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Error state */}
      {isError && (
        <div className="mb-8 rounded-lg border border-danger/30 bg-danger/10 p-5 text-danger flex items-start gap-3">
          <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h3 className="text-sm font-semibold">Failed to load public positions</h3>
            <p className="text-xs text-danger/80 mt-1">
              {error?.message || "There was a network error fetching job opportunities. Please try again."}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      )}

      {/* Loading state: Skeleton Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, idx) => (
            <Card key={idx} className="p-5 flex flex-col gap-4">
              <div className="space-y-2">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-3 w-1/2" />
              </div>
              <div className="flex gap-1.5 pt-2">
                <Skeleton className="h-5 w-16 rounded-full" />
                <Skeleton className="h-5 w-20 rounded-full" />
              </div>
              <div className="mt-auto pt-4 border-t border-border flex justify-between items-center">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-8 w-20 rounded-md" />
              </div>
            </Card>
          ))}
        </div>
      ) : filteredJobs.length === 0 ? (
        /* Empty State */
        <div className="flex flex-col items-center justify-center py-20 text-center rounded-xl border border-border/80 bg-surface/50">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-brand/10 text-brand">
            <Briefcase className="h-7 w-7" />
          </div>
          <h3 className="text-lg font-semibold text-text-primary">No positions found</h3>
          <p className="mt-1 text-sm text-text-muted max-w-sm">
            We couldn&apos;t find any open positions matching your search or filters. Try clearing your filters.
          </p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-5"
            onClick={handleClearFilters}
          >
            Clear filters
          </Button>
        </div>
      ) : (
        /* Job Grid */
        <>
          <div className="mb-4 text-xs font-medium text-text-muted">
            Showing <span className="text-text-primary font-semibold">{filteredJobs.length}</span>{" "}
            active role{filteredJobs.length !== 1 ? "s" : ""}
          </div>
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {filteredJobs.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ─── Job Card ─────────────────────────────────────────────────────────────────

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

function JobCard({ job }: { job: BackendJobResponse }) {
  const visibleSkills = (job.required_skills ?? []).slice(0, 4);
  const extraCount = (job.required_skills ?? []).length - visibleSkills.length;
  const jobTypeKey = (job.job_type || "remote").toLowerCase();

  const formattedSalary = useMemo(() => {
    if (job.salary_min && job.salary_max) {
      return `₹${job.salary_min}–${job.salary_max} LPA`;
    }
    if (job.salary_min) return `₹${job.salary_min} LPA+`;
    if (job.salary_max) return `Up to ₹${job.salary_max} LPA`;
    return "Competitive Compensation";
  }, [job.salary_min, job.salary_max]);

  const formattedPostedDate = formatRelativeDate(job.created_at);

  return (
    <Card className="flex flex-col hover:border-brand/50 hover:shadow-sm transition-all duration-200 group">
      <CardContent className="flex flex-1 flex-col gap-4 p-5">
        {/* Top row */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <Link
              href={`/jobs/${job.id}`}
              className="text-base font-semibold text-text-primary group-hover:text-brand transition-colors line-clamp-1"
            >
              {job.title}
            </Link>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-text-muted">
              <span>{job.department}</span>
              <span className="text-border">·</span>
              <span className="flex items-center gap-0.5">
                <MapPin className="h-3 w-3 text-text-muted" />
                {job.location}
              </span>
            </div>
          </div>
          <Badge
            variant={TYPE_BADGE[jobTypeKey] ?? "default"}
            className="shrink-0 uppercase text-[10px] tracking-wide"
          >
            {job.job_type}
          </Badge>
        </div>

        {/* Experience & rounds summary */}
        <div className="text-xs text-text-muted flex items-center gap-3">
          <span>{job.experience_min}–{job.experience_max} yrs exp</span>
          {job.interview_rounds && job.interview_rounds.length > 0 && (
            <>
              <span className="text-border">·</span>
              <span>{job.interview_rounds.length} interview rounds</span>
            </>
          )}
        </div>

        {/* Skills */}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {visibleSkills.map((skill) => (
            <Badge key={skill} variant="outline" className="text-xs bg-bg/50">
              {skill}
            </Badge>
          ))}
          {extraCount > 0 && (
            <Badge variant="outline" className="text-xs text-text-muted bg-bg/30">
              +{extraCount} more
            </Badge>
          )}
        </div>

        {/* Footer */}
        <div className="mt-auto flex items-center justify-between pt-3 border-t border-border">
          <div>
            <p className="text-sm font-semibold text-text-primary">
              {formattedSalary}
            </p>
            <p className="text-[11px] text-text-muted flex items-center gap-1 mt-0.5">
              <Clock className="h-3 w-3" />
              Posted {formattedPostedDate}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Button asChild variant="secondary" size="sm">
              <Link href={`/jobs/${job.id}`}>View</Link>
            </Button>
            <Button asChild size="sm">
              <Link href={`/jobs/${job.id}/apply`}>Apply</Link>
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
