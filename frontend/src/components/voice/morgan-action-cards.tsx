"use client";

import { CheckCircle2, AlertCircle, Users } from "lucide-react";
import { asRecord, morganBulkResults, reviewDate, safeText } from "@/lib/morgan-workflows";
import type { VoicePendingAction, VoiceToolResult } from "@/lib/api/voice-assistants";

function CandidateName({ item }: { item: Record<string, unknown> }) {
  const candidate = asRecord(item.candidate);
  const job = asRecord(item.job);
  return <div><p className="text-sm font-semibold text-text-primary">{safeText(candidate.name) || safeText(item.candidate_name) || "Candidate"}</p>{candidate.email ? <p className="mt-0.5 break-all text-xs text-text-muted">{safeText(candidate.email)}</p> : null}{job.title ? <p className="mt-0.5 text-xs text-text-muted">{safeText(job.title)}</p> : null}</div>;
}
export function MorganBulkReview({ action }: { action: VoicePendingAction }) {
  const details = asRecord(action.details);
  const items = Array.isArray(details.items) ? details.items.map(asRecord) : [];
  const template = asRecord(details.template);
  const eligible = items.filter(item => item.eligible === true).length;
  return <div className="space-y-3">
    <p className="flex items-center gap-2 text-xs font-semibold text-brand"><Users className="h-4 w-4" />{eligible} ready · {items.length - eligible} will be skipped</p>
    {safeText(template.name) && <p className="rounded-lg border border-brand/20 bg-surface p-2 text-xs text-text-primary">Template: <strong>{safeText(template.name)}</strong>{typeof template.duration_minutes === "number" ? ` · ${template.duration_minutes} minutes` : ""}</p>}
    {details.timezone ? <p className="text-xs text-text-muted">Times shown in {safeText(details.timezone)}</p> : null}
    <ol className="max-h-64 space-y-2 overflow-auto pr-1" aria-label="Candidates included in this request">{items.map((item, index) => <li key={safeText(asRecord(item.application).id) || index} className="rounded-lg border border-border bg-surface p-3"><div className="flex items-start justify-between gap-2"><CandidateName item={item} /><span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${item.eligible === true ? "bg-brand-light text-brand" : "bg-bg text-text-muted"}`}>{item.eligible === true ? "Ready" : "Skip"}</span></div>{safeText(item.scheduled_at) && <p className="mt-2 text-xs font-medium text-text-primary">{reviewDate(item.scheduled_at, details.timezone)}{typeof item.duration_minutes === "number" ? ` · ${item.duration_minutes} min` : ""}</p>}{safeText(item.skip_reason) && <p className="mt-2 text-xs text-text-muted">{safeText(item.skip_reason)}</p>}</li>)}</ol>
    <p className="text-xs leading-relaxed text-text-muted">Only candidates marked Ready will be changed after you confirm.</p>
  </div>;
}
export function MorganBulkResult({ result }: { result: VoiceToolResult }) {
  const data = asRecord(result.result);
  const items = morganBulkResults(result) || [];
  const failed = Number(data.failed || 0);
  return <div className="space-y-3">
    <p className="flex items-center gap-2 text-xs font-semibold">{failed ? <AlertCircle className="h-4 w-4 text-warning" /> : <CheckCircle2 className="h-4 w-4 text-brand" />}{Number(data.succeeded || 0)} completed · {Number(data.skipped || 0)} skipped · {failed} failed</p>
    <ol className="max-h-64 space-y-2 overflow-auto pr-1" aria-label="Results by candidate">{items.map((item, index) => <li key={safeText(item.application_id) || index} className="rounded-lg border border-border bg-surface p-3"><div className="flex items-start justify-between gap-2"><CandidateName item={item} /><span className={`shrink-0 text-xs font-semibold ${item.status === "succeeded" ? "text-brand" : item.status === "failed" ? "text-error" : "text-text-muted"}`}>{item.status === "succeeded" ? "Completed" : item.status === "skipped" ? "Skipped" : "Failed"}</span></div>{safeText(item.scheduled_at) && <p className="mt-2 text-xs text-text-primary">{reviewDate(item.scheduled_at)}</p>}<p className="mt-1 text-xs leading-relaxed text-text-muted">{safeText(item.message)}</p></li>)}</ol>
  </div>;
}
