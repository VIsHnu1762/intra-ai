import type { VoicePendingAction, VoiceToolResult } from "@/lib/api/voice-assistants";

export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
export const safeText = (value: unknown): string => typeof value === "string" ? value : "";
export function isMorganBulkAction(action: VoicePendingAction | null | undefined): boolean {
  return Boolean(action && ["bulk_shortlist_candidates", "bulk_schedule_interviews"].includes(action.tool));
}
export function morganBulkResults(result: VoiceToolResult | null | undefined): Record<string, unknown>[] | null {
  const data = asRecord(result?.result);
  if (!Array.isArray(data.items) || !["succeeded", "failed", "skipped"].some(key => typeof data[key] === "number")) return null;
  return data.items.map(asRecord);
}
export function morganChangedQueryKeys(status?: string, outcomeUnknown = false): readonly string[][] {
  return outcomeUnknown || ["succeeded", "partial", "failed"].includes(status?.toLowerCase() || "") ? [["jobs"], ["candidates"], ["applications"], ["scheduling"], ["interview-templates"]] : [];
}
/** Polling reads outcomes; it never resubmits an accepted confirmation. */
export function reconcileMorganActionSnapshot(current: VoiceToolResult | null, incoming: VoiceToolResult | null | undefined, pending: VoicePendingAction | null | undefined, submitted: ReadonlySet<string>) {
  const waiting = ["submitting", "executing"].includes(current?.status || "") || current?.outcome_unknown === true;
  let result = incoming || current;
  if (waiting && current?.confirmation_id && incoming?.confirmation_id !== current.confirmation_id) result = current;
  if (current?.confirmation_id && incoming?.confirmation_id === current.confirmation_id && ["succeeded", "partial", "failed", "declined"].includes(current.status || "") && !current.outcome_unknown && incoming.status === "executing") result = current;
  return { result, pending: pending && !submitted.has(pending.confirmation_id) ? pending : null };
}

export function morganExternalReviewKind(action: VoicePendingAction): "email" | "calendar" | "slack" | null {
  if (["send_candidate_email", "send_reminder_email", "create_candidate_email_draft"].includes(action.tool)) return "email";
  if (action.tool === "add_interview_to_calendar") return "calendar";
  if (action.tool === "post_recruiting_update_to_slack") return "slack";
  return null;
}
export function morganExternalReviewReady(action: VoicePendingAction): boolean {
  const details = asRecord(action.details);
  switch (morganExternalReviewKind(action)) {
    case "email": { const email = asRecord(details.email); return [email.to, email.subject, email.body].every(value => typeof value === "string" && Boolean(value.trim())) && ["send", "draft_only"].includes(safeText(email.mode)); }
    case "slack": return Boolean(safeText(asRecord(details.channel).name) && safeText(details.message));
    case "calendar": { const event = asRecord(details.event); const calendar = asRecord(details.calendar); return Boolean((safeText(calendar.summary) || safeText(calendar.id)) && safeText(event.summary) && safeText(event.start_datetime) && safeText(event.end_datetime) && Array.isArray(event.attendees) && event.attendees.length && event.attendees.every(item => typeof item === "string" && item.includes("@")) && ["all", "none"].includes(safeText(event.send_updates))); }
    default: return true;
  }
}
export function morganConfirmLabel(action: VoicePendingAction): string {
  const details = asRecord(action.details);
  switch (morganExternalReviewKind(action)) {
    case "email": return asRecord(details.email).mode === "draft_only" ? "Save Email Draft" : "Send This Email";
    case "slack": return "Post to Slack";
    case "calendar": return asRecord(details.event).send_updates === "all" ? "Add & Notify Candidate" : "Add to Calendar";
    default: return "Confirm Action";
  }
}
export function reviewDate(value: unknown, timeZone?: unknown): string {
  const text = safeText(value);
  if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(text)) return text;
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  try { return date.toLocaleString(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short", ...(typeof timeZone === "string" && timeZone ? { timeZone } : {}) }); }
  catch { return text; }
}
