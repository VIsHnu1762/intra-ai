"use client";
import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import { getCandidates } from "@/lib/api/candidates";
import { rolePlayApi as api, type Definition, type Persona, type Scenario } from "../api";
import { PersonaEditor, ScenarioEditor } from "./definition-editors";

export default function RolePlayPage({recruiter=false}:{recruiter?:boolean}) {
  const {user}=useAuth();const cache=useQueryClient();const [editor,setEditor]=useState<"persona"|"scenario"|null>(null);
  const [persona,setPersona]=useState<Definition<Persona>>();const [scenario,setScenario]=useState<Definition<Scenario>>();
  const [candidateId,setCandidateId]=useState("");const [scenarioId,setScenarioId]=useState("");
  const sessions=useQuery({queryKey:["roleplay-sessions",user?.id],queryFn:api.sessions,retry:false});
  const personas=useQuery({queryKey:["roleplay-personas",user?.id],queryFn:api.personas,enabled:recruiter,retry:false});
  const scenarios=useQuery({queryKey:["roleplay-scenarios",user?.id],queryFn:api.scenarios,enabled:recruiter,retry:false});
  const candidates=useQuery({queryKey:["roleplay-candidates",user?.id],queryFn:()=>getCandidates({per_page:100}),enabled:recruiter,retry:false});
  const savePersona=useMutation({mutationFn:(definition:Persona)=>api.savePersona({...definition,objectives:definition.objectives.filter(Boolean),concerns:definition.concerns.filter(Boolean),allowed_information:definition.allowed_information.filter(Boolean),restricted_information:definition.restricted_information.filter(Boolean)},crypto.randomUUID(),persona?.id,persona?.revision),onSuccess:()=>{setEditor(null);void cache.invalidateQueries({queryKey:["roleplay-personas"]});}});
  const saveScenario=useMutation({mutationFn:(definition:Scenario)=>api.saveScenario({...definition,competencies:definition.competencies.filter(Boolean)},crypto.randomUUID(),scenario?.id,scenario?.revision),onSuccess:()=>{setEditor(null);void cache.invalidateQueries({queryKey:["roleplay-scenarios"]});}});
  const assign=useMutation({mutationFn:()=>api.createSession(scenarioId,candidateId,crypto.randomUUID()),onSuccess:()=>{void cache.invalidateQueries({queryKey:["roleplay-sessions"]});}});
  return <div className={recruiter?"space-y-6 p-4 sm:p-8":"space-y-6"}>
    <div><h1 className="text-3xl font-semibold">Role-play simulations</h1><p className="mt-2 text-text-muted">Work through realistic conversations with a simulated character. Sessions use text; voice will be added separately.</p></div>
    {recruiter&&<section className="space-y-5 rounded-2xl border border-border bg-surface p-5">
      <div className="flex flex-wrap gap-4"><button className="text-sm text-brand underline" onClick={()=>{setPersona(undefined);setEditor("persona");}}>Create persona</button><button className="text-sm text-brand underline" onClick={()=>{setScenario(undefined);setEditor("scenario");}}>Create scenario</button></div>
      <div className="grid gap-5 sm:grid-cols-2"><div><h2 className="font-semibold">Personas</h2>{personas.data?.map(p=><button className="mt-2 block text-sm text-brand" key={p.id} onClick={()=>{setPersona(p);setEditor("persona");}}>{p.definition.name} (v{p.revision})</button>)}</div><div><h2 className="font-semibold">Scenarios</h2>{scenarios.data?.map(s=><button className="mt-2 block text-sm text-brand" key={s.id} onClick={()=>{setScenario(s);setEditor("scenario");}}>{s.definition.title} (v{s.revision})</button>)}</div></div>
      {(personas.error||scenarios.error||candidates.error)&&<p role="alert" className="text-error">{personas.error?.message||scenarios.error?.message||candidates.error?.message}</p>}
      {editor&&<div className="rounded-xl border border-border p-4"><button className="mb-4 text-sm underline" onClick={()=>setEditor(null)}>Close editor</button>{editor==="persona"?<PersonaEditor key={persona?.id||"new-persona"} initial={persona} onSave={v=>savePersona.mutate(v)} pending={savePersona.isPending}/>:<ScenarioEditor key={scenario?.id||"new-scenario"} initial={scenario} personas={personas.data||[]} onSave={v=>saveScenario.mutate(v)} pending={saveScenario.isPending}/>} {(savePersona.error||saveScenario.error)&&<p role="alert" className="mt-3 text-error">{savePersona.error?.message||saveScenario.error?.message}</p>}</div>}
      <form className="grid gap-3 border-t border-border pt-5 sm:grid-cols-[1fr_1fr_auto]" onSubmit={e=>{e.preventDefault();assign.mutate();}}>
        <label className="text-sm">Scenario<select required className="mt-1 block w-full rounded-lg border border-border bg-bg p-2" value={scenarioId} onChange={e=>setScenarioId(e.target.value)}><option value="">Choose scenario</option>{scenarios.data?.map(s=><option key={s.id} value={s.id}>{s.definition.title}</option>)}</select></label>
        <label className="text-sm">Candidate<select required className="mt-1 block w-full rounded-lg border border-border bg-bg p-2" value={candidateId} onChange={e=>setCandidateId(e.target.value)}><option value="">Choose candidate</option>{candidates.data?.candidates.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <button className="self-end rounded-lg bg-brand px-4 py-2 text-sm text-white disabled:opacity-50" disabled={assign.isPending}>Assign simulation</button>
      </form>{assign.error&&<p role="alert" className="text-error">{assign.error.message}</p>}{assign.isSuccess&&<p role="status" className="text-sm text-success">Simulation assigned. It is available in the candidate&apos;s portal.</p>}
    </section>}
    {sessions.isPending&&<p role="status">Loading simulations...</p>}{sessions.error&&<p role="alert" className="text-error">{sessions.error.message}</p>}
    {!sessions.isPending&&!sessions.data?.length&&<p className="rounded-xl border border-border bg-surface p-6 text-text-muted">{recruiter?"Assign a scenario to an existing candidate to begin.":"Your assigned simulations will appear here."}</p>}
    <div className="grid gap-4 sm:grid-cols-2">{sessions.data?.map(s=><Link key={s.id} href={`${recruiter?"/admin":""}/role-play/${s.id}`} className="rounded-2xl border border-border bg-surface p-5 transition-colors hover:border-brand"><p className="text-xs uppercase tracking-wide text-text-muted">{s.status}</p><h2 className="mt-2 text-lg font-semibold">{s.title}</h2><p className="mt-1 text-sm text-text-muted">{s.candidate_role} with {s.persona_name}</p><p className="mt-3 text-sm text-brand">{s.status==="completed"?"View feedback":"Open simulation"}</p></Link>)}</div>
  </div>;
}
