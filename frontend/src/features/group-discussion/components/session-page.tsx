"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getCandidates } from "@/lib/api/candidates";
import { decodeAuthToken } from "@/lib/auth/token-storage";
import { discussions, type IndividualReport, type Invitation } from "../api";
import { requestTicket, type RequestTicket } from "../state";
import { DiscussionReport } from "./report-card";
import { PolicySources } from "@/components/knowledge/policy-sources";

const button = "rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-40";
export function DiscussionSessionPage({ id, recruiter = false }: { id: string; recruiter?: boolean }) {
  const queryClient = useQueryClient();
  const key = ["group-discussion", id, decodeAuthToken()?.sub];
  const query = useQuery({ queryKey: key, queryFn: () => discussions.get(id), refetchInterval: 3000 });
  const candidateQuery = useQuery({ queryKey: ["gd-invite-candidates", decodeAuthToken()?.sub], queryFn: () => getCandidates({ per_page: 100 }), enabled: recruiter });
  const [text, setText] = useState("");
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [candidate, setCandidate] = useState("");
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [report, setReport] = useState<IndividualReport | null>(null);
  const [reportName, setReportName] = useState("");
  const messageTicket = useRef<RequestTicket | null>(null);
  const inviteTicket = useRef<RequestTicket | null>(null);
  const actionTicket = useRef<RequestTicket | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const send = useMutation({ mutationFn: () => {
    const payload = { text: text.trim(), reply_to: replyTo };
    messageTicket.current = requestTicket(payload, messageTicket.current);
    return discussions.message(id, payload.text, replyTo, messageTicket.current.request_id);
  }, onSuccess: (session) => { queryClient.setQueryData(key, session); messageTicket.current = null; setText(""); setReplyTo(null); } });
  const invite = useMutation({ mutationFn: () => {
    inviteTicket.current = requestTicket({ candidate }, inviteTicket.current);
    return discussions.invite(id, candidate, inviteTicket.current.request_id);
  }, onSuccess: (value) => { setInvitation(value); inviteTicket.current = null; refresh(); } });
  const control = useMutation({ mutationFn: (action: "start" | "finish" | "cancel") => {
    const revision = query.data!.revision;
    actionTicket.current = requestTicket({ action, revision }, actionTicket.current);
    return discussions.control(id, action, revision, actionTicket.current.request_id);
  }, onSuccess: () => { actionTicket.current = null; refresh(); }, onError: refresh });
  const attendance = useMutation({ mutationFn: (action: "leave" | "rejoin" | "raise_hand" | "lower_hand") => {
    actionTicket.current = requestTicket({ action }, actionTicket.current);
    return discussions.participate(id, action, actionTicket.current.request_id);
  }, onSuccess: () => { actionTicket.current = null; refresh(); } });
  const remove = useMutation({ mutationFn: (participant: string) => discussions.remove(id, participant, crypto.randomUUID()), onSuccess: refresh });
  const generate = useMutation({ mutationFn: ({ participant }: { participant: string; name: string }) => discussions.report(id, participant), onSuccess: (value, variables) => { setReport(value); setReportName(variables.name); refresh(); } });
  if (query.isPending) return <p className="p-8" role="status">Loading discussion...</p>;
  if (query.error || !query.data) return <p className="p-8 text-destructive" role="alert">{query.error?.message || "Discussion unavailable"}</p>;
  const session = query.data;
  const own = session.participants.find((p) => p.id === session.own_participant_id);
  const active = session.status === "active";
  const editable = active || session.status === "lobby";
  const busy = control.isPending || attendance.isPending || remove.isPending;
  const errors = [send.error, invite.error, control.error, attendance.error, remove.error, generate.error];
  const displayName = (participant: string | null) => session.participants.find((p) => p.id === participant)?.display_name || "Moderator";
  return <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-8">
    <Link className="text-sm text-muted-foreground underline" href={recruiter ? "/admin/group-discussions" : "/group-discussions"}>All discussions</Link>
    <header className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Text discussion / {session.status}</p><h1 className="mt-1 text-3xl font-semibold">{session.title}</h1><p className="mt-2 max-w-3xl text-muted-foreground">{session.topic}</p></div><p className="rounded-xl border px-4 py-2 text-sm">{active ? `${Math.ceil(session.time_remaining_seconds / 60)} min remaining` : `${session.duration_seconds / 60} min session`}</p></header>
    <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">Local text pilot. No microphone is captured. New GD Agora media integration is a placeholder only.</p>
    {errors.filter(Boolean).map((error, index) => <p key={index} role="alert" className="rounded-lg border border-destructive/30 p-3 text-sm text-destructive">{error!.message}</p>)}
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <section className="space-y-4" aria-label="Discussion conversation">
        <div className="max-h-[65vh] min-h-64 space-y-4 overflow-y-auto rounded-xl border bg-card p-4 sm:p-5" role="log" aria-live="polite" aria-relevant="additions">
          {session.events.length === 0 && <p className="py-12 text-center text-sm text-muted-foreground">{own?.status === "invited" ? "Use your secure invitation link to accept before viewing the conversation." : "The discussion will appear here once participants join."}</p>}
          {session.events.map((event) => <article key={event.id} id={`event-${event.id}`} className="space-y-2">
            {event.text ? <div className={`rounded-lg border p-3 ${event.participant_id === own?.id ? "bg-muted/50" : "bg-background"}`}><div className="flex justify-between gap-2 text-xs text-muted-foreground"><strong>{displayName(event.participant_id)}</strong><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></div>{event.reply_to && <a className="mt-1 block text-xs underline" href={`#event-${event.reply_to}`}>In reply to a contribution</a>}<p className="mt-2 whitespace-pre-wrap break-words text-sm">{event.text}</p>{active && own?.status === "joined" && event.participant_id !== own.id && <button className="mt-2 text-xs underline" onClick={() => setReplyTo(event.id)}>Reply to this contribution</button>}</div> : <p className="text-center text-xs text-muted-foreground">{displayName(event.participant_id)}: {event.kind.replaceAll("_", " ")}</p>}
            {event.response && <div className="rounded-lg border-l-4 border-primary bg-muted/30 p-3"><p className="text-xs font-semibold">AI moderator</p><p className="mt-1 whitespace-pre-wrap text-sm">{event.response}</p></div>}
            <PolicySources context={event.policy_context} />
          </article>)}
        </div>
        {!recruiter && active && own?.status === "joined" && <form className="space-y-2" onSubmit={(event) => { event.preventDefault(); send.mutate(); }}>
          {replyTo && <div className="flex items-center justify-between rounded-lg bg-muted p-2 text-xs"><span>Replying to {displayName(session.events.find((e) => e.id === replyTo)?.participant_id || null)}</span><button type="button" onClick={() => setReplyTo(null)}>Cancel reply</button></div>}
          <label htmlFor="gd-message" className="text-sm font-medium">Your contribution</label><textarea id="gd-message" className="w-full rounded-lg border bg-background p-3 text-sm" rows={3} value={text} maxLength={4000} required disabled={send.isPending} onChange={(e) => setText(e.target.value)} />
          <div className="flex items-center justify-between gap-3"><p className="text-xs text-muted-foreground">Contributions are saved and individually evaluated.</p><button className={`${button} bg-primary text-primary-foreground`} disabled={send.isPending || !text.trim() || session.time_remaining_seconds <= 0}>{send.isPending ? "Saving..." : "Send contribution"}</button></div>
        </form>}
        {session.analysis_pending > 0 && <p className="text-xs text-muted-foreground" role="status">{session.analysis_pending} saved contributions awaiting evaluation. Feedback is not ready until sufficient evaluated evidence is available.</p>}
        {(report || session.report) && <div className="space-y-2">{recruiter && <h2 className="font-semibold">Individual report: {reportName}</h2>}<DiscussionReport report={(report || session.report)!} /></div>}
      </section>
      <aside className="space-y-5">
        <section className="space-y-3 rounded-xl border bg-card p-4"><h2 className="font-semibold">Participants <span className="text-sm font-normal text-muted-foreground">{session.participants.filter((p) => p.status === "joined").length} / {session.max_participants}</span></h2>
          <ul className="space-y-3">{session.participants.map((participant) => <li key={participant.id} className="space-y-1 border-b pb-3 last:border-0 last:pb-0"><div className="flex justify-between gap-2"><span className="text-sm font-medium">{participant.display_name}{participant.id === own?.id && " (you)"}</span><span className="text-xs text-muted-foreground">{participant.hand_raised ? "Hand raised" : participant.status}</span></div>{recruiter && editable && participant.status !== "removed" && <button className="text-xs text-destructive underline" disabled={busy} onClick={() => remove.mutate(participant.id)}>Remove participant</button>}{session.status === "completed" && (recruiter || participant.id === own?.id) && <button className="block text-xs underline" disabled={generate.isPending} onClick={() => generate.mutate({ participant: participant.id, name: participant.display_name })}>{generate.isPending ? "Generating..." : "View individual feedback"}</button>}</li>)}</ul>
          {!recruiter && own && editable && own.status !== "invited" && <div className="flex flex-wrap gap-2">{own.status === "joined" ? <><button className={button} disabled={busy} onClick={() => attendance.mutate(own.hand_raised ? "lower_hand" : "raise_hand")}>{own.hand_raised ? "Lower hand" : "Raise hand"}</button><button className={button} disabled={busy} onClick={() => attendance.mutate("leave")}>Leave</button></> : own.status === "left" && <button className={button} disabled={busy} onClick={() => attendance.mutate("rejoin")}>Rejoin</button>}</div>}
        </section>
        {recruiter && editable && <section className="space-y-3 rounded-xl border p-4"><h2 className="font-semibold">Session controls</h2><p className="text-xs text-muted-foreground">At least {session.min_participants} joined participants are required to start.</p><div className="flex flex-wrap gap-2">{session.status === "lobby" && <button className={`${button} bg-primary text-primary-foreground`} disabled={busy || session.participants.filter((p) => p.status === "joined").length < session.min_participants} onClick={() => control.mutate("start")}>Start</button>}{active && <button className={button} disabled={busy} onClick={() => control.mutate("finish")}>Finish discussion</button>}<button className={`${button} text-destructive`} disabled={busy} onClick={() => control.mutate("cancel")}>Cancel session</button></div></section>}
        {recruiter && editable && <form className="space-y-3 rounded-xl border p-4" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}><h2 className="font-semibold">Invite a candidate</h2><label className="block text-sm">Workspace candidate<select className="mt-1 w-full rounded-lg border bg-background p-2 text-sm" value={candidate} required onChange={(e) => { setCandidate(e.target.value); setInvitation(null); }}><option value="">Select candidate</option>{candidateQuery.data?.candidates.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label>{candidateQuery.error && <p role="alert" className="text-xs text-destructive">{candidateQuery.error.message}</p>}<button className={button} disabled={invite.isPending || !candidate}>{invite.isPending ? "Creating link..." : "Create secure invitation"}</button>{invitation && <div className="space-y-2"><label className="block text-xs">Private invitation link<input className="mt-1 w-full rounded border bg-background p-2 text-xs" readOnly value={invitation.join_url} onFocus={(e) => e.target.select()} /></label><p className="text-xs text-muted-foreground">Share only with this candidate. Expires {new Date(invitation.expires_at).toLocaleString()}. Their signed-in account must match the invitation.</p></div>}</form>}
      </aside>
    </div>
  </main>;
}
