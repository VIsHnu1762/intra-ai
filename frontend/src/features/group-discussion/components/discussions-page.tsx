"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { decodeAuthToken } from "@/lib/auth/token-storage";
import { discussions, type DiscussionConfiguration } from "../api";
import { requestTicket, type RequestTicket } from "../state";

const inputClass = "w-full rounded-lg border bg-background px-3 py-2 text-sm";
const buttonClass = "rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50";

export function DiscussionsPage({ recruiter = false }: { recruiter?: boolean }) {
  const queryClient = useQueryClient();
  const owner = decodeAuthToken()?.sub;
  const key = ["group-discussions", owner];
  const sessions = useQuery({ queryKey: key, queryFn: discussions.list });
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [minutes, setMinutes] = useState(20);
  const [maximum, setMaximum] = useState(6);
  const [competencies, setCompetencies] = useState("communication, collaboration, reasoning");
  const [policyQuery, setPolicyQuery] = useState("");
  const ticket = useRef<RequestTicket | null>(null);
  const create = useMutation({ mutationFn: () => {
    const configuration: DiscussionConfiguration = { title: title.trim(), topic: topic.trim(), duration_seconds: minutes * 60, min_participants: 2, max_participants: maximum, competencies: [...new Set(competencies.split(",").map((v) => v.trim()).filter(Boolean))], policy_query: policyQuery.trim() };
    ticket.current = requestTicket(configuration, ticket.current);
    return discussions.create(configuration, ticket.current.request_id);
  }, onSuccess: () => { ticket.current = null; setTitle(""); setTopic(""); queryClient.invalidateQueries({ queryKey: key }); } });
  const prefix = recruiter ? "/admin/group-discussions" : "/group-discussions";
  return <main className="mx-auto max-w-5xl space-y-8 p-4 sm:p-8">
    <header className="space-y-2"><p className="text-sm font-medium text-muted-foreground">Collaborative assessment</p><h1 className="text-3xl font-semibold tracking-tight">Group discussions</h1><p className="max-w-2xl text-muted-foreground">Discuss a shared topic, build on other perspectives, and receive individual evidence-backed feedback.</p></header>
    <aside className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm"><strong>Text-only pilot.</strong> Agora voice, ASR, TTS, and realtime media are not connected for GD. Standard Interview voice is unchanged.</aside>
    {recruiter && <form className="grid gap-4 rounded-xl border bg-card p-5 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
      <h2 className="text-lg font-semibold sm:col-span-2">Create a discussion</h2>
      <label className="space-y-1 text-sm sm:col-span-2">Title<input className={inputClass} required minLength={3} maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} disabled={create.isPending} /></label>
      <label className="space-y-1 text-sm sm:col-span-2">Discussion topic<textarea className={inputClass} required minLength={10} maxLength={2000} rows={3} value={topic} onChange={(e) => setTopic(e.target.value)} disabled={create.isPending} /></label>
      <label className="space-y-1 text-sm">Duration in minutes<input className={inputClass} type="number" min={1} max={60} required value={minutes} onChange={(e) => setMinutes(Number(e.target.value))} /></label>
      <label className="space-y-1 text-sm">Participant limit<input className={inputClass} type="number" min={2} max={12} required value={maximum} onChange={(e) => setMaximum(Number(e.target.value))} /></label>
      <label className="space-y-1 text-sm sm:col-span-2">Competencies, separated by commas<input className={inputClass} value={competencies} required maxLength={500} onChange={(e) => setCompetencies(e.target.value)} /></label>
      <label className="space-y-1 text-sm sm:col-span-2">Company-policy context (optional)<input className={inputClass} value={policyQuery} maxLength={250} placeholder="For example: customer pilot approval" onChange={(e) => setPolicyQuery(e.target.value)} /><span className="block text-xs text-muted-foreground">Only authorized, candidate-visible source excerpts will be shared. The first usable snapshot is pinned for this discussion.</span></label>
      {create.error && <p role="alert" className="text-sm text-destructive sm:col-span-2">{create.error.message}</p>}
      <div><button className={buttonClass} disabled={create.isPending}>{create.isPending ? "Creating..." : "Create discussion"}</button></div>
    </form>}
    <section aria-label="Your discussion sessions" className="space-y-3">
      {sessions.isPending && <p role="status">Loading discussions...</p>}
      {sessions.error && <p role="alert" className="text-destructive">{sessions.error.message}</p>}
      {sessions.data?.length === 0 && <div className="rounded-xl border p-8 text-center text-muted-foreground">{recruiter ? "Create a session, then invite candidates from your workspace." : "Your invited discussions will appear here. Use your invitation link to join."}</div>}
      {sessions.data?.map((session) => <Link href={`${prefix}/${session.id}`} key={session.id} className="block rounded-xl border bg-card p-5 transition-colors hover:bg-muted/30"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">{session.title}</h2><span className="rounded-full bg-muted px-3 py-1 text-xs capitalize">{session.status}</span></div><p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{session.topic}</p></Link>)}
    </section>
  </main>;
}
