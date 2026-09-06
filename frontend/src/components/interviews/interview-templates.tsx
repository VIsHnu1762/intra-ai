"use client";

import { useState } from "react";
import Link from "next/link";
import { Archive, Copy, Edit3, Layers, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/client";
import type { InterviewTemplate, InterviewTemplateDraft } from "@/lib/api/interview-templates";
import { useApplyInterviewTemplate, useArchiveInterviewTemplate, useInterviewAgents, useInterviewTemplates, useSaveInterviewTemplate } from "@/hooks/queries/useInterviewTemplates";
import { useJobs } from "@/hooks/queries/useJobs";
import { copyTemplateRounds, interviewRoundLabels, newTemplateRound, validateTemplateRounds } from "@/lib/interview-templates";
import { TemplateRoundEditor } from "./template-round-editor";

const inputStyle = "mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand";
type Editor = { id?: string; version?: number; draft: InterviewTemplateDraft };

export function InterviewTemplates() {
  const [includeArchived, setIncludeArchived] = useState(false);
  const [search, setSearch] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<InterviewTemplate | null>(null);
  const [applyTarget, setApplyTarget] = useState<InterviewTemplate | null>(null);
  const [jobId, setJobId] = useState("");
  const [jobSearch, setJobSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const templates = useInterviewTemplates(includeArchived);
  const catalog = useInterviewAgents();
  const jobs = useJobs({ per_page: 100, search: jobSearch || undefined });
  const save = useSaveInterviewTemplate();
  const archive = useArchiveInterviewTemplate();
  const apply = useApplyInterviewTemplate();
  const agents = catalog.data || [];
  const edit = (template?: InterviewTemplate, duplicate = false) => {
    setError(null);
    setEditor(template ? { ...(duplicate ? {} : { id: template.id, version: template.version }), draft: { name: duplicate ? `${template.name.slice(0, 153)} (copy)` : template.name, description: template.description, rounds: copyTemplateRounds(template.rounds) } } : { draft: { name: "", description: "", rounds: [newTemplateRound(1, agents)] } });
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!editor || save.isPending) return;
    const draft = { ...editor.draft, name: editor.draft.name.trim(), description: editor.draft.description.trim(), rounds: copyTemplateRounds(editor.draft.rounds) };
    const invalid = !draft.name ? "Give this template a name." : validateTemplateRounds(draft.rounds);
    if (invalid) { setError(invalid); return; }
    if (draft.rounds.some(round => round.enabled && round.agent_ids?.some(id => !agents.some(agent => agent.agent_id === id)))) { setError("Remove unavailable interviewers before saving this template."); return; }
    setError(null);
    try { const result = await save.mutateAsync({ ...editor, draft }); setNotice(`${result.name} ${editor.id ? "updated" : "created"}.`); setEditor(null); }
    catch (cause) { setError(cause instanceof ApiError && cause.status === 409 ? "This template was changed elsewhere. Close the editor and reopen it to load the latest version before saving." : cause instanceof Error ? cause.message : "The template could not be saved."); void templates.refetch(); }
  };
  const visible = (templates.data || []).filter(template => `${template.name} ${template.description}`.toLowerCase().includes(search.toLowerCase()));
  const availableJobs = (jobs.data?.jobs || []).filter(job => !["archived", "closed"].includes(job.status));
  const selectedJob = availableJobs.find(job => job.id === jobId);
  const closeDialogs = () => { setEditor(null); setArchiveTarget(null); setApplyTarget(null); setError(null); };
  return <div className="space-y-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h1 className="text-2xl font-bold text-text-primary">Interview Templates</h1><p className="mt-1 max-w-2xl text-sm text-text-muted">Save interview rounds, interviewers, and focus areas once. Reuse them when creating a job or scheduling a candidate.</p></div><Button onClick={() => edit()} disabled={catalog.isLoading || !agents.length}><Plus className="h-4 w-4" />Create Template</Button></div>
    <nav className="flex gap-4 border-b border-border text-sm" aria-label="Interview views"><Link href="/admin/interviews" className="pb-3 text-text-muted hover:text-brand">Scheduled Interviews</Link><span aria-current="page" className="border-b-2 border-brand pb-3 font-semibold text-brand">Interview Templates</span></nav>
    {notice && <p role="status" className="rounded-xl border border-brand/20 bg-brand-light p-3 text-sm text-brand">{notice}</p>}
    <div className="flex flex-wrap items-center justify-between gap-3"><label className="w-full max-w-md text-xs font-medium text-text-muted">Find a template<input className={inputStyle} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search by name or description" /></label><label className="flex items-center gap-2 text-sm text-text-muted"><input type="checkbox" checked={includeArchived} onChange={event => setIncludeArchived(event.target.checked)} className="accent-brand" />Show archived templates</label></div>
    {catalog.isError && <p role="alert" className="text-sm text-error">Interviewers could not be loaded. <button className="underline" onClick={() => void catalog.refetch()}>Try again</button></p>}
    {templates.isLoading ? <p role="status" className="py-12 text-center text-text-muted">Loading templates…</p> : templates.isError ? <div role="alert" className="rounded-xl border border-error/20 p-5 text-sm text-error"><p>{templates.error.message}</p><Button variant="secondary" className="mt-3" onClick={() => void templates.refetch()}>Try Again</Button></div> : visible.length === 0 ? <div className="rounded-xl border border-dashed border-border p-10 text-center"><Layers className="mx-auto h-8 w-8 text-brand" /><h2 className="mt-3 font-semibold text-text-primary">{search ? "No matching templates" : "Build your first interview template"}</h2><p className="mt-2 text-sm text-text-muted">{search ? "Try another name or include archived templates." : "Choose the interviewers, set a duration, and add the topics you want to cover."}</p></div> : <div className="grid gap-4 lg:grid-cols-2">{visible.map(template => <article key={template.id} className="rounded-xl border border-border bg-surface p-5">
      <div className="flex items-start justify-between gap-3"><h2 className="font-semibold text-text-primary">{template.name}</h2><span className="shrink-0 rounded-full bg-bg px-2 py-1 text-xs text-text-muted">{template.archived_at ? "Archived" : `${template.duration_minutes} minutes`}</span></div>{template.description && <p className="mt-2 text-sm leading-relaxed text-text-muted">{template.description}</p>}
      <ol className="my-4 space-y-2">{template.rounds.filter(round => round.enabled !== false).map((round, index) => <li key={index} className="rounded-lg bg-bg p-3 text-sm"><div className="flex justify-between gap-2"><span className="font-medium text-text-primary">{index + 1}. {interviewRoundLabels[round.type] || round.type}</span><span className="shrink-0 text-xs text-text-muted">{round.duration_minutes} min</span></div><p className="mt-1 text-xs text-brand">{(round.agent_ids || (round.agent_id ? [round.agent_id] : [])).map(id => agents.find(agent => agent.agent_id === id)?.name || "Unavailable interviewer").join(" + ")}</p><p className="mt-1 text-xs text-text-muted">{round.focus_areas.map(area => area.replaceAll("_", " ")).join(" · ")}</p></li>)}</ol>
      <div className="flex flex-wrap gap-2">{!template.archived_at && <><Button size="sm" onClick={() => { setError(null); setApplyTarget(template); setJobId(""); }}>Use for a Job</Button><Button size="sm" variant="secondary" onClick={() => edit(template)}><Edit3 className="h-3.5 w-3.5" />Edit</Button></>}<Button size="sm" variant="ghost" onClick={() => edit(template, true)}><Copy className="h-3.5 w-3.5" />Duplicate</Button>{!template.archived_at && <Button size="sm" variant="ghost" onClick={() => { setError(null); setArchiveTarget(template); }}><Archive className="h-3.5 w-3.5" />Archive</Button>}</div>
    </article>)}</div>}
    <Dialog open={Boolean(editor)} onOpenChange={open => { if (!open && !save.isPending) closeDialogs(); }}><DialogContent className="max-w-3xl max-h-[90dvh] overflow-y-auto"><DialogHeader><DialogTitle>{editor?.id ? "Edit Interview Template" : "Create Interview Template"}</DialogTitle><DialogDescription>Set up a reusable interview. You can select several interviewers in the same round.</DialogDescription></DialogHeader>{editor && <form onSubmit={submit} className="space-y-5"><label className="block text-xs font-medium text-text-muted">Template name<input required maxLength={160} className={inputStyle} value={editor.draft.name} onChange={event => setEditor({ ...editor, draft: { ...editor.draft, name: event.target.value } })} placeholder="e.g. Software Engineer · First Interview" /></label><label className="block text-xs font-medium text-text-muted">Description <span className="font-normal">(optional)</span><textarea maxLength={2000} className={`${inputStyle} min-h-20`} value={editor.draft.description} onChange={event => setEditor({ ...editor, draft: { ...editor.draft, description: event.target.value } })} placeholder="When your team should use this interview" /></label><TemplateRoundEditor rounds={editor.draft.rounds} onChange={rounds => setEditor({ ...editor, draft: { ...editor.draft, rounds } })} agents={agents} disabled={save.isPending} />{error && <p role="alert" className="text-sm text-error">{error}</p>}<DialogFooter><Button type="button" variant="secondary" disabled={save.isPending} onClick={closeDialogs}>Cancel</Button><Button type="submit" loading={save.isPending} disabled={catalog.isLoading || !agents.length}>Save Template</Button></DialogFooter></form>}</DialogContent></Dialog>
    <Dialog open={Boolean(archiveTarget)} onOpenChange={open => { if (!open && !archive.isPending) closeDialogs(); }}><DialogContent><DialogHeader><DialogTitle>Archive {archiveTarget?.name}?</DialogTitle><DialogDescription>It will be removed from the template picker. Jobs and interviews already using it keep their existing configuration.</DialogDescription></DialogHeader>{error && <p role="alert" className="text-sm text-error">{error}</p>}<DialogFooter><Button variant="secondary" disabled={archive.isPending} onClick={closeDialogs}>Keep Template</Button><Button loading={archive.isPending} onClick={async () => { if (!archiveTarget) return; try { await archive.mutateAsync(archiveTarget.id); setNotice(`${archiveTarget.name} archived.`); closeDialogs(); } catch (cause) { setError(cause instanceof Error ? cause.message : "The template could not be archived."); } }}>Archive Template</Button></DialogFooter></DialogContent></Dialog>
    <Dialog open={Boolean(applyTarget)} onOpenChange={open => { if (!open && !apply.isPending) closeDialogs(); }}><DialogContent><DialogHeader><DialogTitle>Use {applyTarget?.name}</DialogTitle><DialogDescription>Replace the selected job&apos;s interview rounds with this template. Already scheduled interviews keep their saved configuration.</DialogDescription></DialogHeader><label className="block text-xs font-medium text-text-muted">Find a job<input className={inputStyle} value={jobSearch} onChange={event => { setJobSearch(event.target.value); setJobId(""); }} placeholder="Search job titles" /></label><label className="mt-3 block text-xs font-medium text-text-muted">Job<select className={inputStyle} value={jobId} onChange={event => setJobId(event.target.value)}><option value="">{jobs.isLoading ? "Loading jobs…" : "Choose a job"}</option>{availableJobs.map(job => <option key={job.id} value={job.id}>{job.title} · {job.department}</option>)}</select></label>{selectedJob && <p className="mt-4 rounded-lg bg-brand-light p-3 text-sm text-text-primary">Apply {applyTarget?.duration_minutes} minutes of interview rounds to <strong>{selectedJob.title}</strong>.</p>}{jobs.isError && <p role="alert" className="mt-3 text-sm text-error">Jobs could not be loaded.</p>}{error && <p role="alert" className="mt-3 text-sm text-error">{error}</p>}<DialogFooter><Button variant="secondary" disabled={apply.isPending} onClick={closeDialogs}>Cancel</Button><Button loading={apply.isPending} disabled={!selectedJob} onClick={async () => { if (!applyTarget || !selectedJob) return; try { await apply.mutateAsync({ id: applyTarget.id, jobId }); setNotice(`${applyTarget.name} applied to ${selectedJob.title}.`); closeDialogs(); } catch (cause) { setError(cause instanceof Error ? cause.message : "The template could not be applied."); } }}>Apply Template</Button></DialogFooter></DialogContent></Dialog>
  </div>;
}
