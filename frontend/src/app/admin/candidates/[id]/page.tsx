"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Mail,
  Phone,
  MapPin,
  ExternalLink,
  Briefcase,
  GraduationCap,
  Award,
  FolderGit2,
  CheckCircle2,
  Clock,
  Sparkles,
  FileText,
  Calendar,
  Send,
  XCircle,
  Loader2,
  Upload,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { ScoreBadge } from "@/components/ui/score-badge";
import { Button } from "@/components/ui/button";
import { ResumeDownloadButton } from "@/components/resume-download-button";
import { formatDate } from "@/lib/utils";
import type { ApplicationStatus } from "@/types";
import { useCandidate, useCandidateApplications } from "@/hooks/queries/useCandidates";
import {
  useShortlistApplication,
  useInviteApplication,
  useRejectApplication,
  useReplaceApplicationResume,
} from "@/hooks/queries/useApplications";
import {
  useInterviewSlots,
  useBookInterviewSlot,
  useRescheduleInterview,
  useStartInstantInterview,
} from "@/hooks/queries/useScheduling";

import { SchedulingTemplateSelect } from "@/components/interviews/template-picker";

export default function CandidateDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const candidateId = (params?.id as string) || "";
  const selectedAppParam = searchParams.get("app");

  const { data: candidate, isLoading: candidateLoading, error: candidateError } = useCandidate(candidateId);
  const { data: appsData, isLoading: appsLoading } = useCandidateApplications(candidateId);

  const shortlistMutation = useShortlistApplication();
  const inviteMutation = useInviteApplication();
  const rejectMutation = useRejectApplication();
  const replaceResumeMutation = useReplaceApplicationResume();
  const bookingMutation = useBookInterviewSlot();
  const rescheduleMutation = useRescheduleInterview();
  const instantMutation = useStartInstantInterview();
  const resumeInputRef = useRef<HTMLInputElement>(null);
  const isActionPending = shortlistMutation.isPending || inviteMutation.isPending || rejectMutation.isPending || replaceResumeMutation.isPending || bookingMutation.isPending || rescheduleMutation.isPending || instantMutation.isPending;

  const [activeAppId, setActiveAppId] = useState<string | null>(selectedAppParam);
  const [selectedSlotId, setSelectedSlotId] = useState("");
  const [scheduleTemplateId, setScheduleTemplateId] = useState("");
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  const candidateApplications = appsData?.applications || [];
  const scheduleApplication = candidateApplications.find((a) => a.id === activeAppId) || candidateApplications[0];
  const canSchedule = scheduleApplication?.status === "shortlisted" || scheduleApplication?.status === "invited" || scheduleApplication?.status === "scheduled";
  const { data: availableSlots = [], isLoading: slotsLoading } = useInterviewSlots(
    scheduleApplication?.job_id || "",
    { enabled: Boolean(scheduleApplication?.job_id) && canSchedule },
  );

  if (candidateLoading) {
    return (
      <div className="py-24 text-center space-y-3">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-brand border-r-transparent align-[-0.125em]" />
        <p className="text-sm font-medium text-text-muted">Loading candidate dossier...</p>
      </div>
    );
  }

  if (candidateError || !candidate) {
    return (
      <div className="py-24 text-center space-y-3">
        <p className="text-base font-semibold text-text-primary">Candidate not found</p>
        <p className="text-sm text-text-muted">
          Could not load details for candidate identifier {candidateId}.
        </p>
        <Button asChild variant="secondary" size="sm">
          <Link href="/admin/candidates">Back to Candidates</Link>
        </Button>
      </div>
    );
  }

  const applications = appsData?.applications || (candidate.applications as any[]) || [];
  const activeApp = applications.find((a) => a.id === activeAppId) || applications[0] || null;

  const handleSchedule = async () => {
    if (!activeApp || !selectedSlotId) return;
    setScheduleError(null);
    try {
      if (activeApp.status === "scheduled") {
        await rescheduleMutation.mutateAsync({ applicationId: activeApp.id, slotId: selectedSlotId });
      } else {
        await bookingMutation.mutateAsync({ applicationId: activeApp.id, slotId: selectedSlotId, templateId: scheduleTemplateId || undefined });
      }
      setSelectedSlotId("");
    } catch (err: unknown) {
      setScheduleError(err instanceof Error ? err.message : "Failed to schedule the interview");
    }
  };

  const parsed = candidate.parsed_resume;
  const skills = parsed?.skills || [];
  const experience = parsed?.experience || [];
  const education = parsed?.education || [];
  const projects = parsed?.projects || [];
  const certifications = parsed?.certifications || [];
  const achievements = parsed?.achievements || [];
  const summary = parsed?.summary;
  const location = candidate.location || parsed?.location;

  const resumeUrl = activeApp?.resume_url || candidate.resume_url || null;

  const currentRole = experience.length > 0
    ? `${experience[0].role} at ${experience[0].company}`
    : activeApp?.job?.title
    ? `Applicant · ${activeApp.job.title}`
    : "Candidate Profile";

  const isParsingInProgress = activeApp?.status === "parsing";

  return (
    <div className="space-y-6">
      {/* ── Top Navigation Bar ── */}
      <div className="flex items-start gap-3">
        <Link
          href="/admin/candidates"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border text-text-muted hover:bg-bg hover:text-text-primary transition-colors duration-100 mt-1 shadow-sm"
          title="Back to candidates"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>

        {/* ── Candidate Header Dossier Card ── */}
        <Card className="flex-1 p-5 shadow-sm">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-start gap-4">
              <Avatar size="lg" name={candidate.name} />
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h1 className="text-2xl font-bold text-text-primary tracking-tight">
                    {candidate.name}
                  </h1>
                  {activeApp?.status && (
                    <StatusBadge status={activeApp.status} />
                  )}
                  {activeApp?.eligibility_score != null && activeApp.eligibility_score > 0 && (
                    <ScoreBadge score={activeApp.eligibility_score} size="sm" />
                  )}
                </div>

                <p className="text-sm font-medium text-text-muted">
                  {currentRole}
                </p>

                {/* Contact & Location Metadata */}
                <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 pt-1 text-xs text-text-muted">
                  <a
                    href={`mailto:${candidate.email}`}
                    className="flex items-center gap-1.5 hover:text-brand transition-colors duration-100"
                  >
                    <Mail className="h-3.5 w-3.5 text-text-muted" />
                    {candidate.email}
                  </a>

                  {candidate.phone && (
                    <a
                      href={`tel:${candidate.phone}`}
                      className="flex items-center gap-1.5 hover:text-brand transition-colors duration-100"
                    >
                      <Phone className="h-3.5 w-3.5 text-text-muted" />
                      {candidate.phone}
                    </a>
                  )}

                  {location && (
                    <span className="flex items-center gap-1.5">
                      <MapPin className="h-3.5 w-3.5 text-text-muted" />
                      {location}
                    </span>
                  )}

                  {parsed?.linkedin_url && (
                    <a
                      href={parsed.linkedin_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-brand hover:underline"
                    >
                      <span>LinkedIn</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}

                  {parsed?.github_url && (
                    <a
                      href={parsed.github_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-brand hover:underline"
                    >
                      <span>GitHub</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-2 shrink-0">
              {resumeUrl && activeApp ? <ResumeDownloadButton applicationId={activeApp.id} resumeUrl={resumeUrl} label="Resume" /> : null}
              <input
                ref={resumeInputRef}
                type="file"
                accept=".pdf,.doc,.docx,.txt"
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file && activeApp) {
                    replaceResumeMutation.mutate({ appId: activeApp.id, resumeFile: file });
                  }
                  event.target.value = "";
                }}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => resumeInputRef.current?.click()}
                disabled={isActionPending || !activeApp}
                title="Upload a corrected resume and refresh parsing"
              >
                {replaceResumeMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4 mr-1.5" />
                )}
                {resumeUrl ? "Replace Resume" : "Upload Resume"}
              </Button>

              {activeApp && (
                <>
                  {/* Shortlist action */}
                  {(activeApp.status === "applied" ||
                    activeApp.status === "parsing" ||
                    activeApp.status === "rejected") && (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="text-emerald-700 hover:text-emerald-800 hover:bg-emerald-50 border-emerald-200"
                      onClick={() => shortlistMutation.mutate(activeApp.id)}
                      disabled={isActionPending}
                    >
                      {shortlistMutation.isPending ? (
                        <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 mr-1.5 text-emerald-600" />
                      )}
                      {activeApp.status === "rejected" ? "Reconsider & Shortlist" : "Shortlist Candidate"}
                    </Button>
                  )}

                  {/* Send Interview Invitation */}
                  {(activeApp.status === "shortlisted" ||
                    activeApp.status === "applied" ||
                    activeApp.status === "parsing") && (
                    <Button
                      size="sm"
                      className="bg-brand hover:bg-brand-hover text-white shadow-sm"
                      onClick={() => inviteMutation.mutate(activeApp.id)}
                      disabled={isActionPending}
                    >
                      {inviteMutation.isPending ? (
                        <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4 mr-1.5" />
                      )}
                      Send Interview Invite
                    </Button>
                  )}

                  {/* Recruiter-owned scheduling */}
                  {(activeApp.status === "shortlisted" || activeApp.status === "invited" || activeApp.status === "scheduled") && (
                    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-brand/20 bg-brand-light/20 px-2.5 py-2">
                      <Calendar className="h-4 w-4 text-brand shrink-0" />
                      {activeApp.status !== "scheduled" && <SchedulingTemplateSelect value={scheduleTemplateId} onChange={setScheduleTemplateId} disabled={isActionPending} />}
                      <select
                        aria-label="Interview slot"
                        value={selectedSlotId}
                        onChange={(event) => setSelectedSlotId(event.target.value)}
                        disabled={isActionPending || slotsLoading}
                        className="h-8 max-w-[230px] rounded-md border border-border bg-surface px-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-brand/30"
                      >
                        <option value="">
                          {slotsLoading ? "Loading slots..." : availableSlots.length ? "Choose a slot" : "Create a job slot first"}
                        </option>
                        {availableSlots.map((slot) => (
                          <option key={slot.id} value={slot.id}>
                            {slot.date} · {slot.start_time.slice(0, 5)}–{slot.end_time.slice(0, 5)}
                          </option>
                        ))}
                      </select>
                      <Button
                        size="sm"
                        onClick={handleSchedule}
                        disabled={!selectedSlotId || isActionPending || slotsLoading}
                      >
                        {bookingMutation.isPending || rescheduleMutation.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : null}
                        {activeApp.status === "scheduled" ? "Reschedule Interview" : "Schedule Interview"}
                      </Button>
                      {scheduleError && (
                        <p className="basis-full text-[11px] text-error">{scheduleError}</p>
                      )}
                    </div>
                  )}

                  {/* If already invited: Show badge + Resend Invitation */}
                  {activeApp.status === "invited" && (
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                        <Clock className="h-3.5 w-3.5" />
                        {activeApp.meeting_mode === "instant" && activeApp.instant_status === "instant_pending"
                          ? "Instant invite live · 10 min response"
                          : "Invited · Awaiting Slot"}
                      </span>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => inviteMutation.mutate(activeApp.id)}
                        disabled={isActionPending}
                      >
                        {inviteMutation.isPending ? (
                          <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                        ) : (
                          <Send className="h-3.5 w-3.5 mr-1.5" />
                        )}
                        Resend Invite
                      </Button>
                    </div>
                  )}

                  {(activeApp.status === "shortlisted" || activeApp.status === "invited") && (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="border-amber-300 text-amber-800 hover:bg-amber-50"
                      onClick={() => { setScheduleError(null); instantMutation.mutate({ applicationId: activeApp.id, templateId: scheduleTemplateId || undefined }, { onError: error => setScheduleError(error.message) }); }}
                      disabled={isActionPending}
                      title="Give the candidate ten minutes to accept an immediate interview"
                    >
                      {instantMutation.isPending ? (
                        <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                      ) : (
                        <Zap className="h-4 w-4 mr-1.5 text-amber-600" />
                      )}
                      Start Instant (10 min)
                    </Button>
                  )}

                  {/* If scheduled: View scheduled interview */}
                  {activeApp.status === "scheduled" && (
                    <div className="flex flex-wrap items-center gap-2">
                      {activeApp.interview_id && (
                        <Button asChild size="sm">
                          <Link href={`/interview/${activeApp.interview_id}/prep`}>
                            <ExternalLink className="h-4 w-4 mr-1.5" />
                            Open Interview Room
                          </Link>
                        </Button>
                      )}
                      <Button asChild size="sm" variant="secondary">
                        <Link href="/admin/interviews">
                          <Calendar className="h-4 w-4 mr-1.5 text-purple-600" />
                          View Schedule
                        </Link>
                      </Button>
                    </div>
                  )}

                  {/* Reject button */}
                  {activeApp.status !== "rejected" && activeApp.status !== "completed" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-error hover:text-error hover:bg-red-50"
                      onClick={() => rejectMutation.mutate(activeApp.id)}
                      disabled={isActionPending}
                    >
                      {rejectMutation.isPending ? (
                        <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                      ) : (
                        <XCircle className="h-4 w-4 mr-1.5" />
                      )}
                      Reject
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* ── Parsing In-Progress Alert Banner ── */}
      {isParsingInProgress && (
        <div className="flex items-center gap-3 rounded-lg border border-warning/40 bg-warning-light p-4 text-sm text-warning shadow-sm">
          <Clock className="h-5 w-5 shrink-0 animate-pulse" />
          <div>
            <p className="font-semibold">Resume parsing in progress</p>
            <p className="text-xs opacity-90 mt-0.5">
              Structured resume intelligence and candidate qualification scoring are being processed.
            </p>
          </div>
        </div>
      )}

      {/* ── Main Dossier Navigation Tabs ── */}
      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Candidate Dossier</TabsTrigger>
          <TabsTrigger value="applications">
            Applications ({applications.length})
          </TabsTrigger>
          <TabsTrigger value="interviews">Interview History</TabsTrigger>
        </TabsList>

        {/* ── DOSSIER / PROFILE TAB ── */}
        <TabsContent value="profile" className="space-y-6">
          <div className="grid gap-6 lg:grid-cols-3">
            {/* Left Column (2 Cols): Summary, Experience, Projects */}
            <div className="lg:col-span-2 space-y-6">
              {/* Professional Summary */}
              {summary && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base font-semibold">
                      <Sparkles className="h-4 w-4 text-brand" />
                      Professional Summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-text-primary leading-relaxed bg-bg/50 p-3.5 rounded-lg border border-border">
                      {summary}
                    </p>
                  </CardContent>
                </Card>
              )}

              {/* Work Experience */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base font-semibold">
                    <Briefcase className="h-4 w-4 text-text-muted" />
                    Work Experience
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {experience.length > 0 ? (
                    experience.map((exp, i) => (
                      <div key={i} className="relative pl-5">
                        <div className="absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full bg-brand" />
                        {i < experience.length - 1 && (
                          <div className="absolute left-[4px] top-4 bottom-[-20px] w-px bg-border" />
                        )}
                        <div>
                          <div className="flex flex-wrap items-center justify-between gap-1">
                            <p className="text-sm font-semibold text-text-primary">
                              {exp.role}
                            </p>
                            <span className="text-xs text-text-muted font-medium">
                              {exp.start_date} — {exp.end_date || "Present"}
                            </span>
                          </div>
                          <p className="text-sm font-medium text-brand mt-0.5">
                            {exp.company}
                          </p>
                          {exp.description && (
                            <p className="text-sm text-text-muted mt-1.5 leading-relaxed">
                              {exp.description}
                            </p>
                          )}
                          {exp.technologies && exp.technologies.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-2.5">
                              {exp.technologies.map((t) => (
                                <span
                                  key={t}
                                  className="text-[11px] font-medium bg-bg px-2 py-0.5 rounded border border-border text-text-muted"
                                >
                                  {t}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="py-4 text-center text-sm text-text-muted">
                      {isParsingInProgress
                        ? "Resume uploaded — details are still being processed."
                        : "No work experience details listed."}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Projects */}
              {projects.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base font-semibold">
                      <FolderGit2 className="h-4 w-4 text-text-muted" />
                      Key Projects
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    {projects.map((p, i) => (
                      <div key={i} className="border-b border-border last:border-0 pb-4 last:pb-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-text-primary">
                            {p.name}
                          </p>
                          {p.url && (
                            <a
                              href={p.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-brand hover:underline flex items-center gap-1"
                            >
                              <span>View Project</span>
                              <ExternalLink className="h-3 w-3" />
                            </a>
                          )}
                        </div>
                        {p.description && (
                          <p className="text-sm text-text-muted mt-1 leading-relaxed">
                            {p.description}
                          </p>
                        )}
                        {p.technologies && p.technologies.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2.5">
                            {p.technologies.map((t) => (
                              <Badge key={t} variant="outline" className="text-xs font-normal">
                                {t}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Right Column (1 Col): Eligibility, Skills, Education, Certifications */}
            <div className="space-y-6">
              {/* Eligibility Evaluation Card */}
              {activeApp && (
                <Card className="border-brand/30 bg-brand-light/10 shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center justify-between text-base font-semibold text-text-primary">
                      <span>Eligibility Assessment</span>
                      {activeApp.eligibility_score != null && (
                        <ScoreBadge score={activeApp.eligibility_score} size="default" />
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3 pt-1">
                    <div className="flex items-center justify-between text-xs py-1 border-b border-border/60">
                      <span className="text-text-muted">Target Opportunity</span>
                      <span className="font-semibold text-text-primary text-right truncate max-w-[170px]">
                        {activeApp.job?.title || "Applied Role"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs py-1 border-b border-border/60">
                      <span className="text-text-muted">Application Status</span>
                      <StatusBadge status={activeApp.status} />
                    </div>

                    <div className="flex items-center justify-between text-xs py-1">
                      <span className="text-text-muted">Recommendation</span>
                      <span className="font-semibold capitalize text-text-primary">
                        {activeApp.status === "shortlisted"
                          ? "Shortlisted for Interview"
                          : activeApp.status === "rejected"
                          ? "Did Not Meet Criteria"
                          : "Under Review"}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Skills */}
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold">
                      Extracted Skills
                    </CardTitle>
                    <span className="text-xs font-medium text-text-muted bg-border px-2 py-0.5 rounded-full">
                      {skills.length} skills
                    </span>
                  </div>
                </CardHeader>
                <CardContent>
                  {skills.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {skills.map((s) => (
                        <Badge key={s} variant="default" className="text-xs">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-text-muted text-center py-2">
                      {isParsingInProgress
                        ? "Extracting skills from resume..."
                        : "No skills detected in resume."}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Education */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base font-semibold">
                    <GraduationCap className="h-4 w-4 text-text-muted" />
                    Education
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3.5">
                  {education.length > 0 ? (
                    education.map((e, i) => (
                      <div key={i} className="border-b border-border last:border-0 pb-3 last:pb-0">
                        <p className="text-sm font-semibold text-text-primary">
                          {e.degree}
                        </p>
                        <p className="text-xs text-brand font-medium mt-0.5">
                          {e.field}
                        </p>
                        <p className="text-xs text-text-muted mt-0.5">
                          {e.institution}
                        </p>
                        {e.year && (
                          <p className="text-[11px] text-text-muted mt-1">
                            Graduation: {e.year}
                          </p>
                        )}
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-text-muted text-center py-2">
                      {isParsingInProgress
                        ? "Extracting education..."
                        : "No education entries detected."}
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Certifications */}
              {certifications.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base font-semibold">
                      <Award className="h-4 w-4 text-text-muted" />
                      Certifications
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2.5">
                    {certifications.map((c, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs">
                        <CheckCircle2 className="h-4 w-4 text-success shrink-0 mt-0.5" />
                        <span className="text-text-primary font-medium">{c}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Achievements */}
              {achievements.length > 0 && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base font-semibold">
                      <Award className="h-4 w-4 text-brand" />
                      Achievements & Honors
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {achievements.map((ach, i) => (
                      <p key={i} className="text-xs text-text-muted leading-relaxed">
                        • {ach}
                      </p>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </TabsContent>

        {/* ── APPLICATIONS TAB ── */}
        <TabsContent value="applications">
          {appsLoading ? (
            <div className="py-12 text-center text-sm text-text-muted">
              Loading applications...
            </div>
          ) : applications.length === 0 ? (
            <Card className="p-8 text-center text-sm text-text-muted">
              No applications submitted by this candidate yet.
            </Card>
          ) : (
            <Card className="overflow-hidden">
              <table className="w-full">
                <thead className="border-b border-border bg-bg/50">
                  <tr>
                    {["Job Title", "Score", "Status", "Applied Date", "Action"].map((h) => (
                      <th key={h} className="text-left px-5 py-3 text-xs font-medium text-text-muted uppercase tracking-wide">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {applications.map((a) => (
                    <tr key={a.id} className="hover:bg-bg transition-colors duration-100">
                      <td className="px-5 py-4">
                        <Link
                          href={`/admin/jobs/${a.job_id}`}
                          className="text-sm font-medium text-text-primary hover:text-brand"
                        >
                          {a.job?.title || `Job: ${a.job_id}`}
                        </Link>
                        <p className="text-xs text-text-muted">{a.job?.department || "Intra AI"}</p>
                      </td>
                      <td className="px-5 py-4">
                        {a.eligibility_score != null && a.eligibility_score > 0 ? (
                          <ScoreBadge score={a.eligibility_score} size="sm" />
                        ) : (
                          <span className="text-xs text-text-muted">—</span>
                        )}
                      </td>
                      <td className="px-5 py-4">
                        <StatusBadge status={a.status} />
                      </td>
                      <td className="px-5 py-4 text-sm text-text-muted">
                        {formatDate(a.created_at)}
                      </td>
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setActiveAppId(a.id)}
                            className="text-xs font-semibold text-brand hover:underline mr-2"
                          >
                            Focus in Dossier
                          </button>

                          {(a.status === "applied" || a.status === "parsing") && (
                            <>
                              <Button
                                size="sm"
                                variant="secondary"
                                className="h-7 text-xs px-2 text-emerald-700 hover:text-emerald-800 hover:bg-emerald-50"
                                onClick={() => shortlistMutation.mutate(a.id)}
                                disabled={isActionPending}
                              >
                                Shortlist
                              </Button>
                              <Button
                                size="sm"
                                className="h-7 text-xs px-2 bg-brand hover:bg-brand-hover text-white"
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
                              className="h-7 text-xs px-2 bg-brand hover:bg-brand-hover text-white"
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
                              Reject
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </TabsContent>

        {/* ── INTERVIEWS TAB ── */}
        <TabsContent value="interviews">
          <Card className="p-8 text-center text-sm text-text-muted">
            Interview sessions will appear here once scheduled or completed with Jordan and Alex agents.
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
