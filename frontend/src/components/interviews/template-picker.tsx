"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useInterviewTemplates } from "@/hooks/queries/useInterviewTemplates";
import { copyTemplateRounds } from "@/lib/interview-templates";
import type { InterviewRoundConfig } from "@/types";

export function InterviewTemplatePicker({ onApply }: { onApply: (rounds: InterviewRoundConfig[]) => void }) {
  const templates = useInterviewTemplates();
  const [selectedId, setSelectedId] = useState("");
  const [notice, setNotice] = useState("");
  const selected = templates.data?.find(template => template.id === selectedId);
  return <section className="rounded-xl border border-brand/20 bg-brand-light/40 p-4" aria-label="Use an interview template"><h3 className="text-sm font-semibold text-text-primary">Start from an interview template</h3><p className="mt-1 text-xs text-text-muted">Choose saved rounds and interviewers, then adjust anything below before saving the job.</p><div className="mt-3 flex flex-wrap gap-2"><select aria-label="Saved interview template" value={selectedId} onChange={event => { setSelectedId(event.target.value); setNotice(""); }} className="min-w-0 max-w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary"><option value="">{templates.isLoading ? "Loading templates…" : "Choose a template"}</option>{templates.data?.map(template => <option key={template.id} value={template.id}>{template.name} · {template.duration_minutes} min</option>)}</select><Button type="button" size="sm" variant="secondary" disabled={!selected} onClick={() => { if (!selected) return; onApply(copyTemplateRounds(selected.rounds)); setNotice(`${selected.name} applied. Review the rounds below.`); }}>Use Template</Button></div>{selected && <p className="mt-2 text-xs text-text-muted">This replaces the rounds currently shown below.</p>}{notice && <p role="status" className="mt-2 text-xs text-brand">{notice}</p>}{templates.isError && <p role="alert" className="mt-2 text-xs text-error">Templates could not be loaded. <button type="button" className="underline" onClick={() => void templates.refetch()}>Try again</button></p>}<Link href="/admin/interviews/templates" className="mt-3 inline-block text-xs font-medium text-brand underline">Manage Interview Templates</Link></section>;
}

export function SchedulingTemplateSelect({ value, onChange, disabled }: { value: string; onChange: (id: string) => void; disabled?: boolean }) {
  const templates = useInterviewTemplates();
  return <div><label className="sr-only" htmlFor="schedule-template">Interview template</label><select id="schedule-template" value={value} onChange={event => onChange(event.target.value)} disabled={disabled || templates.isLoading} className="h-8 max-w-[230px] rounded-md border border-border bg-surface px-2 text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-brand/30"><option value="">Use job&apos;s interview rounds</option>{templates.data?.map(template => <option key={template.id} value={template.id}>{template.name} · {template.duration_minutes} min</option>)}</select>{templates.isError && <p className="mt-1 text-xs text-error">Saved templates unavailable; job rounds can still be used.</p>}</div>;
}
