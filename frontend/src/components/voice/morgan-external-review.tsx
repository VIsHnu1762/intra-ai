"use client";

import { asRecord, morganExternalReviewKind, reviewDate, safeText } from "@/lib/morgan-workflows";
import type { VoicePendingAction } from "@/lib/api/voice-assistants";

function ReviewText({ label, text }: { label: string; text: string }) {
  return <div><dt className="text-xs font-semibold text-text-muted">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words text-sm leading-relaxed text-text-primary">{text}</dd></div>;
}

/** Exact destination and content returned by the authorized server preview. */
export function MorganExternalReview({ action }: { action: VoicePendingAction }) {
  const details = asRecord(action.details);
  const kind = morganExternalReviewKind(action);
  if (kind === "email") {
    const email = asRecord(details.email);
    const draft = email.mode === "draft_only";
    return <div className="space-y-3"><p className="rounded-lg bg-surface p-2 text-xs font-medium text-brand">{draft ? "Save a Gmail draft · No email will be sent" : "Send this email to the candidate"}</p><dl className="max-h-80 space-y-3 overflow-auto rounded-lg border border-border bg-surface p-3"><ReviewText label="To" text={safeText(email.to)} /><ReviewText label="Subject" text={safeText(email.subject)} /><ReviewText label="Message" text={safeText(email.body)} /></dl></div>;
  }
  if (kind === "slack") {
    const channel = asRecord(details.channel);
    return <div className="space-y-3"><p className="rounded-lg bg-surface p-2 text-xs font-medium text-brand">Post to Slack · #{safeText(channel.name).replace(/^#/, "")}</p><dl className="max-h-80 space-y-3 overflow-auto rounded-lg border border-border bg-surface p-3"><ReviewText label="Channel" text={`#${safeText(channel.name).replace(/^#/, "")}`} />{safeText(asRecord(details.job).title) && <ReviewText label="Job" text={safeText(asRecord(details.job).title)} />}<ReviewText label="Message" text={safeText(details.message)} /></dl></div>;
  }
  if (kind === "calendar") {
    const calendar = asRecord(details.calendar);
    const event = asRecord(details.event);
    const calendarId = safeText(calendar.id);
    const calendarName = safeText(calendar.summary) || calendarId;
    const attendees = Array.isArray(event.attendees) ? event.attendees.map(safeText).join("\n") : "";
    return <div className="space-y-3"><dl className="max-h-80 space-y-3 overflow-auto rounded-lg border border-border bg-surface p-3"><ReviewText label="Google Calendar" text={calendarName + (calendarName !== calendarId && calendarId.includes("@") ? `\n${calendarId}` : "")} /><ReviewText label="Event title" text={safeText(event.summary)} /><ReviewText label="Starts" text={reviewDate(event.start_datetime)} /><ReviewText label="Ends" text={reviewDate(event.end_datetime)} /><ReviewText label="Attendees" text={attendees} /><ReviewText label="Candidate notification" text={event.send_updates === "all" ? "An invitation email will be sent to the attendee." : event.send_updates === "none" ? "No invitation email will be sent." : "Notification setting unavailable."} /></dl><p className="text-xs leading-relaxed text-text-muted">This adds the saved interview to the selected calendar. It does not reschedule the interview.</p></div>;
  }
  return null;
}
