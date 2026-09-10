"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Mic, MicOff, PhoneOff, Volume2, Waves } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { useVoiceAssistant } from "@/hooks/use-voice-assistant";

import { isMorganBulkAction, morganBulkResults, morganExternalReviewKind, morganExternalReviewReady, morganConfirmLabel } from "@/lib/morgan-workflows";
import { MorganBulkReview, MorganBulkResult } from "./morgan-action-cards";
import { MorganExternalReview } from "./morgan-external-review";

type Assistant = ReturnType<typeof useVoiceAssistant>;
const readable = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
function reviewDetails(value: unknown): unknown {
  if (value === null || value === undefined || value === "") return undefined;
  if (Array.isArray(value)) {
    const visible = value.map(reviewDetails).filter(item => item !== undefined);
    return visible.length ? visible : undefined;
  }
  if (typeof value === "object") {
    const visible = Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
      const normalized = key.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
      if (/(^|_)(id|ids|uid|uids)$/.test(normalized) || ["channel", "channel_name", "agent_type"].includes(normalized)) return [];
      const detail = reviewDetails(item);
      return detail === undefined ? [] : [[key, detail]];
    });
    return visible.length ? Object.fromEntries(visible) : undefined;
  }
  return value;
}

function detailText(value: string, field: string): string {
  if (!/(^|_)(date|time|at)$/.test(field)) return value;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const date = new Date(`${value}T12:00:00`);
    if (!Number.isNaN(date.getTime())) return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }
  // Only timestamps with an explicit offset can safely be converted to local time.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) return date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
  }
  if (/^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(value)) {
    return new Date(`1970-01-01T${value}`).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  return value;
}

function DetailValue({ value, field = "" }: { value: unknown; field?: string }) {
  if (Array.isArray(value)) return <ul className="space-y-2">{value.map((item, index) => <li key={index}><DetailValue value={item} field={field} /></li>)}</ul>;
  if (typeof value === "object" && value !== null) return <dl className="space-y-1.5">{Object.entries(value as Record<string, unknown>).map(([key, item]) => <div key={key}><dt className="font-medium">{readable(key)}</dt><dd className="mt-0.5"><DetailValue value={item} field={key} /></dd></div>)}</dl>;
  return <span>{typeof value === "boolean" ? value ? "Yes" : "No" : typeof value === "string" ? detailText(value, field) : String(value)}</span>;
}

export function VoiceAssistantPanel({ assistant, name, compact = false, onStart, onEnd, endLabel, startDisabled = false }: {
  assistant: Assistant;
  name: string;
  compact?: boolean;
  onStart: () => void;
  onEnd?: () => void;
  endLabel?: string;
  startDisabled?: boolean;
}) {
  const { connection, state, transcript, pendingAction, toolResult } = assistant;
  const transcriptView = useRef<HTMLDivElement>(null);
  const followTranscript = useRef(true);
  useEffect(() => {
    if (followTranscript.current && transcriptView.current) transcriptView.current.scrollTop = transcriptView.current.scrollHeight;
  }, [transcript]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!pendingAction?.expires_at) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [pendingAction?.expires_at]);
  const pendingDetails = reviewDetails(pendingAction?.details);
  const resultDetails = reviewDetails(toolResult?.result);
  const active = connection.active;
  const statusText = state === "speaking" ? `${name} is speaking` : state === "listening" ? "Listening to you" : state === "processing" ? `${name} is thinking` : state === "executing" ? "Completing your request" : readable(state);
  const incompleteReview = name === "Morgan" && pendingAction ? !morganExternalReviewReady(pendingAction) : false;
  const actionRunning = ["submitting", "executing"].includes(toolResult?.status || "");
  const expiredAction = pendingAction?.expires_at ? Date.parse(pendingAction.expires_at) <= now : false;
  const stages = [
    ["Voice connected", connection.connected],
    [`${name} joined`, connection.agentJoined],
    ["Audio received", connection.audioSubscribed],
    ["Audio playback started", connection.playbackStarted && !connection.autoplayBlocked],
  ] as const;
  return (
    <div className={cn("flex flex-col", compact ? "gap-4" : "gap-6")}>
      <div className={cn("rounded-2xl bg-brand-light border border-brand/15 text-center", compact ? "p-4" : "p-8")}>
        <div className={cn("mx-auto mb-3 flex items-center justify-center rounded-full bg-brand/10 text-brand", compact ? "h-14 w-14" : "h-20 w-20", state === "speaking" && "motion-safe:animate-pulse")}><Waves aria-hidden="true" className={compact ? "h-7 w-7" : "h-10 w-10"} /></div>
        <p role="status" aria-live="polite" className="font-semibold text-text-primary">{statusText}</p>
        <p className="mt-1 text-xs text-text-muted">{active ? assistant.muted ? "Your microphone is muted" : connection.microphonePublished ? "Microphone on · Speak naturally" : "Setting up your microphone…" : `Start a voice conversation with ${name}`}</p>
      </div>

      {connection.error && <div role="alert" className="rounded-xl border border-error/20 bg-error-light p-3 text-sm text-error flex items-start gap-2"><AlertCircle className="h-4 w-4 shrink-0 mt-0.5" /><p>{connection.error}</p></div>}
      {connection.autoplayBlocked && <Button variant="secondary" onClick={() => void assistant.unlockAudio()}><Volume2 className="h-4 w-4" />Enable {name}&apos;s audio</Button>}
      {active && !connection.playbackStarted && <ul className="grid grid-cols-2 gap-2 text-xs text-text-muted" aria-label="Connection progress">{stages.map(([label, done]) => <li key={label} className="flex items-center gap-1.5">{done ? <CheckCircle2 className="h-3.5 w-3.5 text-brand" /> : <span className="h-3 w-3 rounded-full border border-border" aria-hidden="true" />}<span>{label}{done ? " ✓" : "…"}</span></li>)}</ul>}

      <div className="flex flex-wrap justify-center gap-2">
        {!active ? <Button onClick={onStart} disabled={startDisabled || assistant.actionPending}><Mic className="h-4 w-4" />{name === "Taylor" ? "Start Training" : "Connect to Morgan"}</Button> : <>
          <Button variant="secondary" onClick={() => void assistant.toggleMute()} disabled={!connection.microphonePublished} aria-pressed={assistant.muted}>{assistant.muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}{assistant.muted ? "Unmute" : "Mute"}</Button>
          <Button variant="danger" onClick={onEnd || (() => void assistant.end())}><PhoneOff className="h-4 w-4" />{endLabel || `End ${name === "Taylor" ? "Training" : "Session"}`}</Button>
        </>}
        {!active && connection.error?.includes("Retry ending") && <Button variant="secondary" onClick={() => void assistant.end()}>Retry End Session</Button>}
        {!active && /active session/i.test(connection.error || "") && <Button variant="secondary" onClick={() => void assistant.resetSession()}>End Previous Session</Button>}
      </div>

      {name === "Morgan" && assistant.actionPending && !active && <p role="status" className="text-xs text-text-muted">Your confirmed action is still being checked. Its result will appear here.</p>}
      {pendingAction && <section className="rounded-xl border border-brand/30 bg-brand-light p-4 space-y-3" aria-label="Confirm assistant action">
        <h3 className="font-semibold text-sm">Review before continuing</h3>
        <p className="text-sm text-text-primary">{pendingAction.summary || readable(pendingAction.tool)}</p>
        {name === "Morgan" && isMorganBulkAction(pendingAction) ? <MorganBulkReview action={pendingAction} /> : name === "Morgan" && morganExternalReviewKind(pendingAction) ? <MorganExternalReview action={pendingAction} /> : pendingDetails !== undefined && <div className="text-xs leading-relaxed text-text-muted max-h-48 overflow-auto break-words"><DetailValue value={pendingDetails} /></div>}
        {pendingAction.expires_at && <p className="text-xs text-text-muted">{expiredAction ? "This confirmation has expired. Ask Morgan to prepare the request again." : `Confirm by ${new Date(pendingAction.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`}</p>}
        {incompleteReview && <p role="alert" className="text-xs text-error">The destination or message details are incomplete. Ask Morgan to prepare a new review.</p>}
        <div className="flex flex-wrap gap-2"><Button size="sm" loading={assistant.confirming} disabled={expiredAction || incompleteReview || assistant.actionPending} onClick={() => void assistant.confirm(true)}>{name === "Morgan" ? morganConfirmLabel(pendingAction) : "Confirm Action"}</Button><Button size="sm" variant="secondary" disabled={assistant.confirming} onClick={() => void assistant.confirm(false)}>Decline</Button></div>
      </section>}
      {toolResult && <section role="status" className={cn("rounded-xl border p-3 text-sm", /error|failed/i.test(toolResult.status || "") ? "border-error/20 bg-error-light text-error" : "border-border bg-bg text-text-primary")}>
        {actionRunning && <p className="mb-2 flex items-center gap-2 text-xs font-semibold text-brand"><Loader2 className="h-4 w-4 animate-spin" />{toolResult.status === "submitting" ? "Submitting confirmation" : "Action in progress"}</p>}
        <p>{toolResult.message || (actionRunning ? "Your confirmed action is running. Waiting for its result." : "Your request returned a result.")}</p>
        {toolResult.outcome_unknown && <p className="mt-2 text-xs leading-relaxed">The request may have changed data or reached the connected service. Check its current state before preparing another action.</p>}
        {name === "Morgan" && morganBulkResults(toolResult) ? <div className="mt-3"><MorganBulkResult result={toolResult} /></div> : resultDetails !== undefined && <details className="mt-2"><summary className="cursor-pointer text-xs font-medium">View details</summary><div className="mt-2 max-h-52 overflow-auto break-words text-xs"><DetailValue value={resultDetails} /></div></details>}
      </section>}
      <section aria-label={`${name} conversation`}>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-text-muted mb-3">Conversation</h3>
        <div ref={transcriptView} onScroll={event => { const view = event.currentTarget; followTranscript.current = view.scrollHeight - view.scrollTop - view.clientHeight < 40; }} role="log" aria-live="polite" aria-relevant="additions text" className={cn("space-y-3 overflow-y-auto rounded-xl border border-border bg-bg p-3", compact ? "max-h-52 min-h-24" : "max-h-80 min-h-32")}>
          {transcript.length === 0 ? <p className="text-sm text-text-muted">{active ? "Your conversation will appear here when available." : name === "Taylor" ? "Try explaining a recent project, then ask for feedback on your answer." : "Ask about a candidate, interview, or recruiting task."}</p> : transcript.map((entry, index) => <div key={entry.id || `${entry.at || index}-${entry.role}`} className="text-sm"><p className="text-xs font-semibold text-brand mb-1">{["user", "candidate", "recruiter"].includes(entry.role.toLowerCase()) ? "You" : entry.role === "system" ? "Session" : name}</p><p className="whitespace-pre-wrap break-words leading-relaxed text-text-primary">{entry.text}</p></div>)}
        </div>
      </section>
    </div>
  );
}
