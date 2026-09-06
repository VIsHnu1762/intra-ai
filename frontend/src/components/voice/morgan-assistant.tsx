"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { morganChangedQueryKeys } from "@/lib/morgan-workflows";
import { ChevronDown, Mic, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useReport } from "@/hooks/queries/useReports";
import { useVoiceAssistant } from "@/hooks/use-voice-assistant";
import { voiceDashboardContext } from "@/lib/voice-assistant-state";
import { VoiceAssistantPanel } from "./voice-assistant-panel";

function AuthorizedMorgan() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const reportId = /^\/admin\/reports\/([a-zA-Z0-9_-]+)\/?$/.exec(pathname)?.[1] || "";
  const { data: report } = useReport(reportId);
  const reportInterviewId = report?.interview_id;
  const context = useMemo(() => reportId && reportInterviewId ? { interview_id: reportInterviewId } : voiceDashboardContext(pathname), [pathname, reportId, reportInterviewId]);
  const assistant = useVoiceAssistant("morgan");
  const queryClient = useQueryClient();
  const lastResultKey = useRef("");
  const resultKey = JSON.stringify([assistant.sessionId, assistant.toolResult]);
  useEffect(() => {
    if (lastResultKey.current === resultKey) return;
    lastResultKey.current = resultKey;
    for (const queryKey of morganChangedQueryKeys(assistant.toolResult?.status, assistant.toolResult?.outcome_unknown)) {
      void queryClient.invalidateQueries({ queryKey });
    }
  }, [resultKey, assistant.toolResult?.status, assistant.toolResult?.outcome_unknown, queryClient]);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const contextKey = JSON.stringify(context);
  const updateContext = assistant.updateContext;
  useEffect(() => { void updateContext(context); }, [contextKey, context, updateContext]);
  useEffect(() => { if (open) panel.current?.focus(); }, [open]);
  const collapse = () => { setOpen(false); trigger.current?.focus(); };
  const contextLabel = context.candidate_id ? "the candidate profile you opened" : context.job_id ? "the job you opened" : context.interview_id ? "the interview you opened" : "your recruiting workspace";
  return <aside className="fixed bottom-4 right-4 z-50 sm:bottom-6 sm:right-6" aria-label="Morgan HR assistant">
    {open && <section id="morgan-assistant-panel" ref={panel} tabIndex={-1} aria-label="Morgan HR assistant conversation" onKeyDown={event => { if (event.key === "Escape") collapse(); }} className="mb-3 w-[calc(100vw-2rem)] max-w-md max-h-[min(78dvh,760px)] overflow-y-auto rounded-2xl border border-border bg-surface shadow-xl focus:outline-none">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-border bg-surface p-4">
        <div><h2 className="font-semibold text-text-primary">Morgan</h2><p className="text-xs text-text-muted">Your HR voice assistant</p></div>
        <div className="flex gap-1"><button onClick={collapse} className="p-2 rounded-lg hover:bg-bg focus-visible:ring-2 focus-visible:ring-brand" aria-label="Minimize Morgan"><ChevronDown className="h-4 w-4" /></button><button onClick={() => { void assistant.end(); collapse(); }} className="p-2 rounded-lg hover:bg-bg focus-visible:ring-2 focus-visible:ring-brand" aria-label="End and close Morgan"><X className="h-4 w-4" /></button></div>
      </div>
      <div className="p-4"><p className="text-xs text-text-muted mb-4">Morgan can help with {contextLabel}. Review and confirm changes before they are made.</p><VoiceAssistantPanel assistant={assistant} name="Morgan" compact onStart={() => void assistant.start(context)} />
        <details className="mt-4 rounded-xl border border-border bg-bg p-3" open={!assistant.connection.active}>
          <summary className="cursor-pointer text-xs font-semibold text-text-primary">Try asking Morgan</summary>
          <ul className="mt-3 space-y-2 text-xs leading-relaxed text-text-muted">
            <li>“{context.job_id ? "List the candidates for this job." : "Show my open jobs and their candidates."}”</li>
            <li>“Shortlist [candidate names] for [job title].”</li>
            <li>“Schedule the shortlisted candidates using [template name].”</li>
            <li>“Show today&apos;s interviews.”</li>
          </ul>
          <p className="mt-3 text-[11px] text-text-muted">Say the candidate names, job, and preferred time. Morgan will show the proposed changes for your approval.</p>
        </details></div>
    </section>}
    <div className="flex justify-end"><button ref={trigger} aria-expanded={open} aria-controls="morgan-assistant-panel" onClick={() => setOpen(value => !value)} className="flex items-center gap-2 rounded-full bg-brand px-5 py-3 text-white shadow-lg hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"><Mic className="h-5 w-5" /><span className="font-semibold text-sm">{assistant.actionPending && !open ? "Morgan · Action in progress" : assistant.connection.active && !open ? `Morgan · ${assistant.muted ? "Muted" : "Mic on"}` : "Ask Morgan"}</span>{assistant.pendingAction && !open && <span className="text-xs rounded-full px-2 py-0.5 bg-white text-brand">Review</span>}</button></div>
  </aside>;
}

export function MorganAssistant() {
  const { isAuthenticated, isLoading, role, user } = useAuth();
  const isRecruiter = ["admin", "recruiter"].includes(role || user?.role || "");
  if (isLoading || !isAuthenticated || !isRecruiter) return null;
  return <AuthorizedMorgan />;
}
