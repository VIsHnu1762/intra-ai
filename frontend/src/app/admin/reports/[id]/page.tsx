"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, Share2, Calendar, CheckCircle2, AlertTriangle, Check, FileText, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreBadge } from "@/components/ui/score-badge";
import { RecruiterReportAnalysis } from "@/components/reports/recruiter-report-analysis";
import { cn, formatDate, getRecommendationLabel, getScoreBg } from "@/lib/utils";
import type { Recommendation } from "@/types";
import { useReport, useReportStatus, useGenerateReport } from "@/hooks/queries/useReports";
import { safeReportPdfUrl, reportGenerationAction, reportLabel } from "@/lib/report-presentation";

const REC_BADGE_STYLES: Record<Recommendation, string> = {
  strong_hire: "bg-success-light text-success border-success",
  hire: "bg-brand-light text-brand border-brand",
  maybe: "bg-warning-light text-warning border-warning",
  no_hire: "bg-error-light text-error border-error",
};

export default function ReportDetailPage() {
  const params = useParams();
  const id = typeof params?.id === "string" ? params.id : "";
  const [copied, setCopied] = useState(false);
  const [shareError, setShareError] = useState(false);
  const statusQuery = useReportStatus(id);
  const status = statusQuery.data;
  const reportQuery = useReport(id, { enabled: status?.status === "ready" && !statusQuery.error });
  const generation = useGenerateReport();
  const report = reportQuery.data;
  const error = statusQuery.error || (status?.status === "ready" ? reportQuery.error : null);
  const loading = statusQuery.isLoading || (status?.status === "ready" && reportQuery.isLoading);

  if (loading || error || status?.status !== "ready" || !report) {
    const action = !error && reportGenerationAction(status?.status, status?.retryable);
    const message = loading ? "Loading the saved report status…" : error?.message || status?.message || (
      status?.status === "not_completed" ? "Complete the interview before generating its assessment report."
      : status?.status === "not_started" ? "The interview is complete. Generate its report from the saved interview evidence."
      : status?.status === "generating" ? "The report is being prepared from the saved interview evidence. This page will update when it is ready."
      : status?.status === "failed" ? "Report generation failed. No completed report is available."
      : "The saved report could not be loaded."
    );
    return <div className="max-w-2xl space-y-6">
      <Link href="/admin/reports" className="inline-flex items-center gap-2 text-sm text-brand"><ArrowLeft className="h-4 w-4" /> Back to Reports</Link>
      <Card><CardContent className="p-6" aria-live="polite">
        <FileText className="mb-3 h-6 w-6 text-brand" />
        <h1 className="text-xl font-semibold text-text-primary">Assessment Report</h1>
        <p className="mt-3 text-sm leading-relaxed text-text-muted">{message}</p>
        {generation.error && <p role="alert" className="mt-3 text-sm text-error">{generation.error.message}</p>}
        <div className="mt-4 flex flex-wrap gap-3">
          {action && status && <Button loading={generation.isPending} onClick={() => generation.mutate(status.interview_id)}>{action}</Button>}
          {!loading && (error || status?.status !== "generating") && <Button variant="secondary" loading={statusQuery.isFetching || reportQuery.isFetching} onClick={() => {
            void statusQuery.refetch();
            if (status?.status === "ready") void reportQuery.refetch();
          }}><RefreshCw className="h-4 w-4" /> Check Again</Button>}
        </div>
      </CardContent></Card>
    </div>;
  }

  const candidateName = report.candidate?.name || "Candidate";
  const candidateId = report.candidate?.id;
  const jobTitle = report.job?.title || "Interview Assessment";
  const overallScore = Math.round(report.overall_score);
  const pdfUrl = safeReportPdfUrl(report.pdf_url);
  const proctoring = report.proctoring_summary;
  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setShareError(false);
      setTimeout(() => setCopied(false), 2000);
    } catch { setShareError(true); }
  };
  const download = pdfUrl ? <Button asChild size="sm"><a href={pdfUrl} target="_blank" rel="noreferrer"><Download className="h-4 w-4" /> Download PDF</a></Button> : null;

  return (
    <div className="max-w-4xl space-y-6">
      <div className="flex flex-wrap items-start gap-3">
        <Link href="/admin/reports" aria-label="Back to Reports" className="mt-1 flex h-8 w-8 items-center justify-center rounded-md text-text-muted hover:bg-border"><ArrowLeft className="h-4 w-4" /></Link>
        <div className="min-w-0 flex-1"><h1 className="text-2xl font-bold text-text-primary">Assessment Report</h1><p className="mt-0.5 text-sm text-text-muted">{candidateName} · {jobTitle}</p></div>
        <div className="flex items-center gap-2"><Button variant="secondary" size="sm" onClick={handleShare}>{copied ? <Check className="h-4 w-4 text-success" /> : <Share2 className="h-4 w-4" />}{copied ? "Copied Link" : "Share"}</Button>{download}</div>
      </div>
      {shareError && <p role="alert" className="text-sm text-error">Unable to copy the link. You can copy this page’s address from your browser.</p>}
      <Card><CardContent className="py-8"><div className="flex flex-col items-center gap-4 text-center">
        <div className={cn("flex h-24 w-24 items-center justify-center rounded-full text-4xl font-black", getScoreBg(overallScore))}>{overallScore}</div>
        <div><p className="text-sm text-text-muted">Overall Score /100</p><p className="mt-0.5 text-xs text-text-muted"><Calendar className="mr-1 inline h-3 w-3" />{formatDate(report.created_at)}</p></div>
        <span className={cn("rounded-full border px-5 py-1.5 text-sm font-bold", REC_BADGE_STYLES[report.recommendation])}>{getRecommendationLabel(report.recommendation)}</span>
      </div></CardContent></Card>

      {!!report.round_assessments?.length && <section><h2 className="mb-3 text-base font-semibold text-text-primary">Round Assessments</h2><div className="grid gap-4 sm:grid-cols-2">{report.round_assessments.map((round, index) => <Card key={round.round_id || `${round.round_type}-${index}`} className="p-4">
        <div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-sm font-semibold text-text-primary">{reportLabel(round.round_name || round.round_type, "Unresolved round")}</h3><ScoreBadge score={Math.round(round.score)} /></div>
        {!!round.agent_ids?.length && <p className="mb-3 text-xs text-text-muted">Interviewers: {round.agent_ids.map(agent => reportLabel(agent, "Interviewer")).join(", ")}</p>}
        {round.identity_resolution === "unresolved" && <p className="mb-3 text-xs text-warning">This evidence could not be matched uniquely to a configured round.</p>}
        {round.observations?.length ? <ul className="space-y-1.5 text-sm text-text-muted">{round.observations.map((text, i) => <li key={i}>{text}</li>)}</ul> : <p className="text-sm text-text-muted">No round observations were recorded.</p>}
      </Card>)}</div></section>}

      <div className="grid gap-4 sm:grid-cols-2">
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-success"><CheckCircle2 className="h-4 w-4" /> Strengths</CardTitle></CardHeader><CardContent>{report.strengths?.length ? <ul className="space-y-2 text-sm text-text-muted">{report.strengths.map((text, index) => <li key={index}>{text}</li>)}</ul> : <p className="text-sm text-text-muted">No strengths were recorded in this report.</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2 text-warning"><AlertTriangle className="h-4 w-4" /> Areas for Improvement</CardTitle></CardHeader><CardContent>{report.improvements?.length ? <ul className="space-y-2 text-sm text-text-muted">{report.improvements.map((text, index) => <li key={index}>{text}</li>)}</ul> : <p className="text-sm text-text-muted">No improvement findings were recorded in this report.</p>}</CardContent></Card>
      </div>
      <RecruiterReportAnalysis analysis={report.analysis} />
      {report.salary_recommendation && <Card><CardHeader><CardTitle>Salary Recommendation</CardTitle></CardHeader><CardContent><p className="text-xl font-semibold text-text-primary">${report.salary_recommendation.min.toLocaleString()} – ${report.salary_recommendation.max.toLocaleString()} / year</p>{report.salary_recommendation.justification && <p className="mt-2 text-sm text-text-muted">{report.salary_recommendation.justification}</p>}</CardContent></Card>}
      <Card><CardHeader><CardTitle>Proctoring Summary</CardTitle></CardHeader><CardContent>
        {proctoring ? <><dl className="grid grid-cols-3 gap-4">{([['Face Presence', proctoring.face_presence_pct, '%'], ['Tab Switches', proctoring.tab_switches, ''], ['Integrity Score', proctoring.integrity_score, '%']] as const).map(([label, value, suffix]) => <div key={label} className="rounded-lg bg-bg p-3 text-center"><dt className="text-xs text-text-muted">{label}</dt><dd className="mt-1 text-xl font-semibold text-text-primary">{typeof value === "number" && Number.isFinite(value) ? `${value}${suffix}` : "Not recorded"}</dd></div>)}</dl>{!!proctoring.events?.length && <ul className="mt-4 space-y-2 text-sm text-text-muted">{proctoring.events.map((event, index) => <li key={index}>{reportLabel(event.type)}{event.details ? `: ${event.details}` : ""}</li>)}</ul>}</> : <p className="text-sm text-text-muted">No proctoring measurements were recorded for this interview.</p>}
      </CardContent></Card>
      <div className="flex flex-wrap gap-3 pb-8">{download}<Button variant="secondary" size="sm" onClick={handleShare}><Share2 className="h-4 w-4" /> Share Report</Button><Button asChild variant="secondary" size="sm"><Link href="/admin/interviews">View Interviews</Link></Button>{candidateId && <Button asChild variant="ghost" size="sm"><Link href={`/admin/candidates/${candidateId}`}>View Candidate Profile</Link></Button>}</div>
    </div>
  );
}
