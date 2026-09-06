"use client";

import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatTemplateFocusAreas, interviewRoundLabels, newTemplateRound, parseTemplateFocusAreas, templateDuration, type InterviewAgent } from "@/lib/interview-templates";
import type { InterviewRoundConfig, InterviewRoundType } from "@/types";

const inputStyle = "mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand";
export function TemplateRoundEditor({ rounds, onChange, agents, disabled = false }: {
  rounds: InterviewRoundConfig[];
  onChange: (rounds: InterviewRoundConfig[]) => void;
  agents: InterviewAgent[];
  disabled?: boolean;
}) {
  const update = (index: number, changes: Partial<InterviewRoundConfig>) => onChange(rounds.map((round, at) => at === index ? { ...round, ...changes } : round));
  const move = (index: number, direction: number) => {
    const next = [...rounds];
    [next[index], next[index + direction]] = [next[index + direction], next[index]];
    onChange(next.map((round, at) => ({ ...round, order_index: at + 1 })));
  };
  const total = templateDuration(rounds);
  return <div className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold text-text-primary">Interview rounds</h3><span className={`text-sm font-medium ${total > 60 ? "text-error" : "text-brand"}`}>{total} / 60 minutes</span></div>
    {rounds.map((round, index) => {
      const selected = round.agent_ids?.length ? round.agent_ids : round.agent_id ? [round.agent_id] : [];
      const unknown = selected.filter(id => !agents.some(agent => agent.agent_id === id));
      return <fieldset key={index} disabled={disabled} className="rounded-xl border border-border bg-bg p-4">
        <legend className="px-1 text-sm font-semibold text-text-primary">Round {index + 1}</legend>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><label className="flex items-center gap-2 text-sm text-text-muted"><input type="checkbox" checked={round.enabled !== false} onChange={event => update(index, { enabled: event.target.checked })} className="accent-brand" />Include this round</label><div className="flex gap-1"><Button type="button" size="icon" variant="ghost" disabled={index === 0} aria-label={`Move round ${index + 1} earlier`} onClick={() => move(index, -1)}><ArrowUp className="h-4 w-4" /></Button><Button type="button" size="icon" variant="ghost" disabled={index === rounds.length - 1} aria-label={`Move round ${index + 1} later`} onClick={() => move(index, 1)}><ArrowDown className="h-4 w-4" /></Button><Button type="button" size="icon" variant="ghost" disabled={rounds.length <= 1} aria-label={`Remove round ${index + 1}`} onClick={() => onChange(rounds.filter((_, at) => at !== index).map((item, at) => ({ ...item, order_index: at + 1 })))}><Trash2 className="h-4 w-4" /></Button></div></div>
        <div className="grid gap-4 sm:grid-cols-[1fr_130px]"><label className="text-xs font-medium text-text-muted">Round type<select className={inputStyle} value={round.type} onChange={event => update(index, { type: event.target.value as InterviewRoundType })}>{Object.entries(interviewRoundLabels).map(([type, label]) => <option key={type} value={type}>{label}</option>)}</select></label><label className="text-xs font-medium text-text-muted">Minutes<input className={inputStyle} type="number" min="1" max="60" value={round.duration_minutes || ""} onChange={event => update(index, { duration_minutes: Number(event.target.value) })} /></label></div>
        <div className="mt-4"><p className="text-xs font-medium text-text-muted">Interviewers · choose one or more</p><div className="mt-2 flex flex-wrap gap-2">{agents.map(agent => <label key={agent.agent_id} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${selected.includes(agent.agent_id) ? "border-brand bg-brand-light text-brand" : "border-border bg-surface text-text-primary"}`}><input type="checkbox" className="accent-brand" checked={selected.includes(agent.agent_id)} onChange={event => { const ids = event.target.checked ? [...selected, agent.agent_id] : selected.filter(id => id !== agent.agent_id); update(index, { agent_ids: ids, agent_id: ids[0] }); }} /><span>{agent.name}<span className="ml-1 text-xs text-text-muted">· {agent.role}</span></span></label>)}</div>{unknown.length > 0 && <p role="alert" className="mt-2 text-xs text-error">A previously selected interviewer is no longer available. <button type="button" className="underline" onClick={() => { const ids = selected.filter(id => !unknown.includes(id)); update(index, { agent_ids: ids, agent_id: ids[0] }); }}>Remove unavailable interviewers</button></p>}</div>
        <label className="mt-4 block text-xs font-medium text-text-muted">Focus areas<textarea className={`${inputStyle} min-h-20`} value={formatTemplateFocusAreas(round.focus_areas)} onChange={event => update(index, { focus_areas: parseTemplateFocusAreas(event.target.value) })} placeholder="Problem solving, communication, relevant project experience" /><span className="mt-1 block text-xs font-normal">Separate each focus area with a comma.</span></label>
      </fieldset>;
    })}
    <Button type="button" variant="secondary" disabled={disabled || rounds.length >= 24} onClick={() => onChange([...rounds, newTemplateRound(rounds.length + 1, agents)])}><Plus className="h-4 w-4" />Add Round</Button>
  </div>;
}
