"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  MapPin,
  Calendar,
  Plus,
  ExternalLink,
  CheckCircle2,
  XCircle,
  Send,
  Clock,
  Cpu,
  Compass,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { StatusBadge } from "@/components/ui/status-badge";
import { ScoreBadge } from "@/components/ui/score-badge";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/avatar";
import { cn, formatDate } from "@/lib/utils";
import type { ApplicationStatus } from "@/types";
import { useJob, usePublishJob } from "@/hooks/queries/useJobs";
import { PublishValidationModal } from "@/components/jobs/publish-validation-modal";
import {
  useJobApplications,
  useShortlistApplication,
  useInviteApplication,
  useRejectApplication,
} from "@/hooks/queries/useApplications";
import {
  useInterviewSlots,
  useCreateInterviewSlots,
} from "@/hooks/queries/useScheduling";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

const STATUS_FILTERS: { key: ApplicationStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "applied", label: "Applied" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "invited", label: "Invited" },
  { key: "scheduled", label: "Scheduled" },
  { key: "in_progress", label: "In Progress" },
  { key: "completed", label: "Completed" },
  { key: "rejected", label: "Rejected" },
];

const JOB_TYPE_LABELS: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
};

const ROUND_LABELS: Record<string, string> = {
  introduction: "Introduction",
  technical: "Technical",
  behavioral: "Behavioral",
  hr_culture: "HR & Culture",
};

export default function JobDetailPage() {
  const params = useParams();
  const jobId = (params?.id as string) || "";
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "all">("all");

  const { data: job, isLoading: jobLoading, error: jobError } = useJob(jobId);
  const { data: appsData, isLoading: appsLoading } = useJobApplications(jobId);
  const shortlistMutation = useShortlistApplication();
  const inviteMutation = useInviteApplication();
  const rejectMutation = useRejectApplication();
  const isActionPending = shortlistMutation.isPending || inviteMutation.isPending || rejectMutation.isPending;
  const publishMutation = usePublishJob();
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);

  const handlePublishJob = async () => {
    if (!job) return;
    setIsPublishing(true);
    try {
      await publishMutation.mutateAsync(job.id);
      setIsPublishModalOpen(false);
    } finally {
      setIsPublishing(false);
    }
  };

  const { data: slots, isLoading: slotsLoading } = useInterviewSlots(jobId);
  const createSlotsMutation = useCreateInterviewSlots();
  const [isAddSlotOpen, setIsAddSlotOpen] = useState(false);
  const [slotDate, setSlotDate] = useState("");
  const [slotStartTime, setSlotStartTime] = useState("10:00");
  const [slotEndTime, setSlotEndTime] = useState("11:00");
  const [slotSubmitting, setSlotSubmitting] = useState(false);
  const [slotError, setSlotError] = useState<string | null>(null);

  const handleAddSlot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!slotDate || !slotStartTime || !slotEndTime) {
      setSlotError("Please fill out date, start time, and end time.");
      return;
    }
    setSlotSubmitting(true);
    setSlotError(null);
    try {
      await createSlotsMutation.mutateAsync({
        jobId,
        slots: [
          {
            date: slotDate,
            start_time: slotStartTime.length === 5 ? `${slotStartTime}:00` : slotStartTime,
            end_time: slotEndTime.length === 5 ? `${slotEndTime}:00` : slotEndTime,
          },
        ],
      });
      setIsAddSlotOpen(false);
      setSlotDate("");
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to create interview slot";
      setSlotError(message);
    } finally {
      setSlotSubmitting(false);
    }
  };


  if (jobLoading) {
    return (
      <div className="py-24 text-center text-sm text-text-muted">
        Loading job details...
      </div>
    );
  }

  if (jobError || !job) {
    return (
      <div className="py-24 text-center space-y-3">
        <p className="text-base font-semibold text-text-primary">Job not found</p>
        <p className="text-sm text-text-muted">
          Could not load details for job {jobId}.
        </p>
        <Button asChild variant="secondary" size="sm">
          <Link href="/admin/jobs">Back to Jobs</Link>
        </Button>
      </div>
    );
  }

  const applicants = appsData?.applications || [];
  const filtered =
    statusFilter === "all"
      ? applicants
      : applicants.filter((a) => a.status === statusFilter);

  const salaryDisplay =
    job.salary_min && job.salary_max
      ? `₹${Number(job.salary_min).toLocaleString()} – ₹${Number(job.salary_max).toLocaleString()} / year`
      : job.salary_min
      ? `₹${Number(job.salary_min).toLocaleString()}+ / year`
      : "Not specified";

  const expDisplay = `${job.experience_min}–${job.experience_max} years`;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Link
          href="/admin/jobs"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-border hover:text-text-primary transition-colors duration-100 mt-1"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold text-text-primary">{job.title}</h1>
            <StatusBadge status={job.status} />
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1">
            <span className="text-sm text-text-muted">{job.department}</span>
            <span className="flex items-center gap-1 text-sm text-text-muted">
              <MapPin className="h-3.5 w-3.5" />
              {job.location}
            </span>
            <span className="flex items-center gap-1 text-sm text-text-muted">
              <Calendar className="h-3.5 w-3.5" />
              Posted {formatDate(job.created_at)}
            </span>
            <span className="text-sm text-text-muted">
              {applicants.length} applicants
            </span>
          </div>
        </div>
        {job.status === "draft" && (
          <Button
            size="sm"
            onClick={() => setIsPublishModalOpen(true)}
            className="bg-brand hover:bg-brand-hover text-white text-xs h-8 gap-1.5 shadow-sm shrink-0"
          >
            <Send className="h-3.5 w-3.5" />
            Publish Opportunity
          </Button>
        )}
      </div>


      {/* Tabs */}
      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="applicants">
            Applicants ({applicants.length})
          </TabsTrigger>
          <TabsTrigger value="slots">Interview Slots</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview">
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Job Description</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-text-muted leading-relaxed whitespace-pre-line">
                    {job.description}
                  </p>
                </CardContent>
              </Card>
            </div>
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Details</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {[
                    { label: "Experience", value: expDisplay },
                    { label: "Education", value: job.education || "Any" },
                    { label: "Salary", value: salaryDisplay },
                    { label: "Job Type", value: JOB_TYPE_LABELS[job.job_type] || job.job_type },
                  ].map((d) => (
                    <div key={d.label}>
                      <p className="text-xs font-medium text-text-muted uppercase tracking-wide">
                        {d.label}
                      </p>
                      <p className="text-sm font-medium text-text-primary mt-0.5">
                        {d.value}
                      </p>
                    </div>
                  ))}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Required Skills</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-1.5">
                    {(job.required_skills || []).map((s) => (
                      <Badge key={s} variant="outline">
                        {s}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-3 border-b border-border">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-base font-semibold">Configured Rounds</CardTitle>
                      <CardDescription className="text-xs text-text-muted">
                        Multi-agent sequential evaluation pipeline
                      </CardDescription>
                    </div>
                    <span className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full bg-brand/10 text-brand border border-brand/20">
                      <Clock className="h-3 w-3" />
                      {(job.interview_rounds || [])
                        .filter((r) => r.enabled !== false)
                        .reduce((sum, r) => sum + (r.duration_minutes || 0), 0)}{" "}
                      min total
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3 pt-4">
                  {(job.interview_rounds || []).length === 0 ? (
                    <p className="text-xs text-text-muted italic">No interview rounds configured.</p>
                  ) : (
                    (job.interview_rounds || []).map((r, i) => {
                      const agentIds = r.agent_ids?.length
                        ? r.agent_ids
                        : [r.agent_id || (r.type === "technical" ? "alex" : "jordan")];
                      const isAlex = agentIds[0] === "alex";
                      return (
                        <div
                          key={i}
                          className="p-3 rounded-lg border border-border bg-bg/40 space-y-2"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="h-5 w-5 rounded-full bg-surface border border-border text-[11px] font-mono font-bold flex items-center justify-center text-text-muted">
                                {r.order_index ?? i + 1}
                              </span>
                              <span className="text-sm font-semibold text-text-primary capitalize">
                                {ROUND_LABELS[r.type] || r.type.replace(/_/g, " ")}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              {/* Assigned Persona Badge */}
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full border",
                                  isAlex
                                    ? "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400"
                                    : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                                )}
                              >
                                {isAlex ? <Cpu className="h-3 w-3" /> : <Compass className="h-3 w-3" />}
                                {agentIds.map((agentId) => agentId === "alex" ? "Alex" : agentId === "jordan" ? "Jordan" : agentId).join(" + ")}
                              </span>
                              <span className="text-xs font-medium text-text-muted">
                                {r.duration_minutes} min
                              </span>
                            </div>
                          </div>

                          {/* Focus areas / Competencies */}
                          {r.focus_areas && r.focus_areas.length > 0 && (
                            <div className="flex flex-wrap gap-1 pt-1">
                              {r.focus_areas.map((comp) => (
                                <span
                                  key={comp}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border text-text-secondary capitalize"
                                >
                                  {comp.replace(/_/g, " ")}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}

                  <div className="pt-3 border-t border-border mt-3 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-text-muted">Agora Session Constraint</span>
                      <span className="font-semibold text-text-secondary">Max 60 min</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-text-muted">Eligibility threshold</span>
                      <span className="font-semibold text-brand">
                        {job.eligibility_threshold}%
                      </span>
                    </div>
                  </div>
                </CardContent>
              </Card>

            </div>
          </div>
        </TabsContent>

        {/* Applicants */}
        <TabsContent value="applicants">
          <div className="space-y-4">
            {/* Status filter */}
            <div className="flex flex-wrap gap-2">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setStatusFilter(f.key)}
                  className={[
                    "px-3 py-1.5 rounded-full text-sm font-medium transition-colors duration-100",
                    statusFilter === f.key
                      ? "bg-brand text-white"
                      : "bg-border text-text-muted hover:text-text-primary",
                  ].join(" ")}
                >
                  {f.label}
                </button>
              ))}
            </div>

            {appsLoading ? (
              <div className="py-12 text-center text-sm text-text-muted">
                Loading applications...
              </div>
            ) : filtered.length === 0 ? (
              <Card className="p-8 text-center text-sm text-text-muted">
                No applications found for this filter.
              </Card>
            ) : (
              <>
                {/* Table — desktop */}
                <Card className="hidden md:block overflow-hidden">
                  <table className="w-full">
                    <thead className="border-b border-border">
                      <tr>
                        {["Candidate", "Email", "Score", "Status", "Applied", "Actions"].map((h) => (
                          <th
                            key={h}
                            className="text-left px-5 py-3 text-xs font-medium text-text-muted uppercase tracking-wide"
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filtered.map((a) => {
                        const candName = a.candidate?.name || "Applicant";
                        const candEmail = a.candidate?.email || "—";
                        const candId = a.candidate?.id || a.candidate_id;

                        return (
                          <tr key={a.id} className="hover:bg-bg transition-colors duration-100">
                            <td className="px-5 py-3">
                              <div className="flex items-center gap-2.5">
                                <Avatar size="sm" name={candName} />
                                <span className="text-sm font-medium text-text-primary">
                                  {candName}
                                </span>
                              </div>
                            </td>
                            <td className="px-5 py-3 text-sm text-text-muted">{candEmail}</td>
                            <td className="px-5 py-3">
                              {a.eligibility_score != null && a.eligibility_score > 0 ? (
                                <ScoreBadge score={a.eligibility_score} size="sm" />
                              ) : (
                                <span className="text-xs text-text-muted">—</span>
                              )}
                            </td>
                            <td className="px-5 py-3">
                              <StatusBadge status={a.status} />
                            </td>
                            <td className="px-5 py-3 text-sm text-text-muted">
                              {formatDate(a.created_at)}
                            </td>
                            <td className="px-5 py-3">
                              <div className="flex items-center gap-2">
                                <Link
                                  href={`/admin/candidates/${candId}`}
                                  className="text-xs text-brand hover:text-brand-hover font-medium flex items-center gap-1"
                                >
                                  View
                                  <ExternalLink className="h-3 w-3" />
                                </Link>
                                {/* Dynamic HR Actions */}
                                {(a.status === "applied" || a.status === "parsing") && (
                                  <>
                                    <Button
                                      size="sm"
                                      variant="secondary"
                                      className="h-7 text-xs px-2 text-emerald-700 hover:text-emerald-800 hover:bg-emerald-50"
                                      onClick={() => shortlistMutation.mutate(a.id)}
                                      disabled={isActionPending}
                                    >
                                      <CheckCircle2 className="h-3 w-3 mr-1 text-emerald-600" />
                                      Shortlist
                                    </Button>
                                    <Button
                                      size="sm"
                                      className="h-7 text-xs px-2 bg-brand hover:bg-brand-hover text-white"
                                      onClick={() => inviteMutation.mutate(a.id)}
                                      disabled={isActionPending}
                                    >
                                      <Send className="h-3 w-3 mr-1" />
                                      Invite
                                    </Button>
                                  </>
                                )}

                                {a.status === "shortlisted" && (
                                  <Button
                                    size="sm"
                                    className="h-7 text-xs px-2 bg-brand hover:bg-brand-hover text-white"
                                    onClick={() => inviteMutation.mutate(a.id)}
                                    disabled={isActionPending}
                                  >
                                    <Send className="h-3 w-3 mr-1" />
                                    Send Invite
                                  </Button>
                                )}

                                {a.status === "invited" && (
                                  <Button
                                    size="sm"
                                    variant="secondary"
                                    className="h-7 text-xs px-2"
                                    onClick={() => inviteMutation.mutate(a.id)}
                                    disabled={isActionPending}
                                  >
                                    <Send className="h-3 w-3 mr-1" />
                                    Resend Invite
                                  </Button>
                                )}

                                {a.status !== "rejected" && a.status !== "completed" && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    className="h-7 text-xs px-2 text-error hover:text-error hover:bg-red-50"
                                    onClick={() => rejectMutation.mutate(a.id)}
                                    disabled={isActionPending}
                                  >
                                    <XCircle className="h-3 w-3 mr-1" />
                                    Reject
                                  </Button>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </Card>

                {/* Cards — mobile */}
                <div className="space-y-3 md:hidden">
                  {filtered.map((a) => {
                    const candName = a.candidate?.name || "Applicant";
                    const candEmail = a.candidate?.email || "—";
                    const candId = a.candidate?.id || a.candidate_id;

                    return (
                      <Card key={a.id} className="p-4">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2.5">
                            <Avatar size="sm" name={candName} />
                            <div>
                              <p className="text-sm font-medium text-text-primary">
                                {candName}
                              </p>
                              <p className="text-xs text-text-muted">{candEmail}</p>
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            <StatusBadge status={a.status} />
                            {a.eligibility_score != null && a.eligibility_score > 0 && (
                              <ScoreBadge score={a.eligibility_score} size="sm" />
                            )}
                          </div>
                        </div>
                        <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
                          <Link
                            href={`/admin/candidates/${candId}`}
                            className="text-xs text-brand hover:text-brand-hover font-medium flex items-center gap-1"
                          >
                            View Details
                            <ExternalLink className="h-3 w-3" />
                          </Link>
                          <div className="flex items-center gap-1.5">
                            {(a.status === "applied" || a.status === "parsing") && (
                              <>
                                <Button
                                  size="sm"
                                  variant="secondary"
                                  className="h-7 text-xs px-2 text-emerald-700"
                                  onClick={() => shortlistMutation.mutate(a.id)}
                                  disabled={isActionPending}
                                >
                                  Shortlist
                                </Button>
                                <Button
                                  size="sm"
                                  className="h-7 text-xs px-2 bg-brand text-white"
                                  onClick={() => inviteMutation.mutate(a.id)}
                                  disabled={isActionPending}
                                >
                                  Invite
                                </Button>
                              </>
                            )}
                            {a.status === "shortlisted" && (
                              <Button
                                size="sm"
                                className="h-7 text-xs px-2 bg-brand text-white"
                                onClick={() => inviteMutation.mutate(a.id)}
                                disabled={isActionPending}
                              >
                                Send Invite
                              </Button>
                            )}
                            {a.status === "invited" && (
                              <Button
                                size="sm"
                                variant="secondary"
                                className="h-7 text-xs px-2"
                                onClick={() => inviteMutation.mutate(a.id)}
                                disabled={isActionPending}
                              >
                                Resend
                              </Button>
                            )}
                            {a.status !== "rejected" && a.status !== "completed" && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 text-xs px-1.5 text-error hover:text-error"
                                onClick={() => rejectMutation.mutate(a.id)}
                                disabled={isActionPending}
                              >
                                Reject
                              </Button>
                            )}
                          </div>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </TabsContent>

        {/* Interview Slots */}
        <TabsContent value="slots">
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-text-primary">Interview Availability</h3>
                <p className="text-sm text-text-muted">
                  Create reusable slots that HR can assign to invited candidates.
                </p>
              </div>
              <Button size="sm" onClick={() => setIsAddSlotOpen(true)}>
                <Plus className="h-4 w-4 mr-1" />
                Add Slot
              </Button>
            </div>

            {slotsLoading ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Card key={i} className="p-4 animate-pulse space-y-2">
                    <div className="h-4 w-1/2 bg-border rounded" />
                    <div className="h-3 w-1/3 bg-border rounded" />
                  </Card>
                ))}
              </div>
            ) : !slots || slots.length === 0 ? (
              <EmptyState
                icon={Calendar}
                title="No interview slots added yet"
                description="Add time slots first, then assign one from the candidate dossier after sending an invitation."
                action={
                  <Button size="sm" onClick={() => setIsAddSlotOpen(true)}>
                    <Plus className="h-4 w-4 mr-1" />
                    Create Slot
                  </Button>
                }
              />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {slots.map((slot) => {
                  const startTime = slot.start_time.slice(0, 5);
                  const endTime = slot.end_time.slice(0, 5);
                  return (
                    <Card key={slot.id} className="p-4">
                      <p className="text-sm font-semibold text-text-primary">
                        {formatDate(slot.date)}
                      </p>
                      <p className="text-sm text-text-muted mt-0.5">
                        {startTime} – {endTime}
                      </p>
                      <div className="flex items-center justify-between mt-3 pt-3 border-t border-border">
                        <span className="text-xs text-text-muted">
                          {slot.is_booked ? "1 booked" : "0 booked"}
                        </span>
                        <span
                          className={cn(
                            "text-xs font-medium px-2 py-0.5 rounded-full",
                            slot.is_booked
                              ? "bg-error-light text-error"
                              : "bg-success-light text-success"
                          )}
                        >
                          {slot.is_booked ? "Booked" : "Available"}
                        </span>
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </div>
        </TabsContent>

        {/* Settings */}
        <TabsContent value="settings">
          <Card>
            <CardContent className="pt-5 space-y-4">
              <p className="text-sm text-text-muted">
                Job settings and advanced configuration coming soon.
              </p>
              <div className="flex gap-3">
                <Button variant="secondary">Edit Job</Button>
                <Button variant="danger">Archive Job</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Create Slot Modal */}
      <Dialog open={isAddSlotOpen} onOpenChange={setIsAddSlotOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Interview Slot</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleAddSlot} className="space-y-4 py-2">
            <Input
              label="Date"
              type="date"
              value={slotDate}
              onChange={(e) => setSlotDate(e.target.value)}
              required
            />
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Start Time"
                type="time"
                value={slotStartTime}
                onChange={(e) => setSlotStartTime(e.target.value)}
                required
              />
              <Input
                label="End Time"
                type="time"
                value={slotEndTime}
                onChange={(e) => setSlotEndTime(e.target.value)}
                required
              />
            </div>
            {slotError && (
              <p className="text-xs text-error">{slotError}</p>
            )}
            <DialogFooter className="mt-4">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setIsAddSlotOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={slotSubmitting}>
                {slotSubmitting ? "Creating..." : "Create Slot"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Pre-Flight Publish Validation Modal */}
      {job && (
        <PublishValidationModal
          open={isPublishModalOpen}
          onOpenChange={setIsPublishModalOpen}
          data={{
            title: job.title,
            department: job.department,
            location: job.location,
            description: job.description,
            skills: job.required_skills || [],
            rounds: job.interview_rounds || [],
          }}
          onConfirmPublish={handlePublishJob}
          isPublishing={isPublishing}
        />
      )}
    </div>
  );
}
