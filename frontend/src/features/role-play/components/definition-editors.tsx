"use client";
import { useState } from "react";
import type { Definition, Persona, Scenario, Phase } from "../api";
const field="block w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm";
const button="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-50";

export function PersonaEditor({initial,onSave,pending}:{initial?:Definition<Persona>;onSave:(value:Persona)=>void;pending:boolean}) {
  const [value,setValue]=useState<Persona>(initial?.definition || {name:"",description:"",personality:"",communication_style:"",objectives:[],concerns:[],allowed_information:[],restricted_information:[]});
  return <form className="space-y-3" onSubmit={e=>{e.preventDefault();onSave(value);}}>
    <h3 className="font-semibold">{initial?"Edit persona":"Create a reusable persona"}</h3>
    {([ ["name","Name"],["description","Character background"],["personality","Personality"],["communication_style","Communication style"] ] as const).map(([key,label])=><label key={key} className="block text-sm">{label}<input className={field} required minLength={key==="name"?1:key==="description"?10:3} maxLength={key==="name"?100:600} value={value[key]} onChange={e=>setValue({...value,[key]:e.target.value})}/></label>)}
    {([ ["objectives","Character objectives"],["concerns","Concerns and objections"],["allowed_information","Information the character may share"],["restricted_information","Private information that must never be shared"] ] as const).map(([key,label])=><label key={key} className="block text-sm">{label}<textarea className={field} placeholder="One item per line" value={value[key].join("\n")} onChange={e=>setValue({...value,[key]:e.target.value.split("\n")})}/></label>)}
    <p className="text-xs text-text-muted">By default, hostility increases tension; empathy and clarification reduce it.</p>
    <button className={button} disabled={pending}>{pending?"Saving...":"Save persona"}</button>
  </form>;
}

const newPhase=(id:string):Phase=>({id,title:"",brief:"",objectives:[],advance_on:["solution"],min_turns:1,max_turns:4,reveal_keys:[]});
export function ScenarioEditor({personas,initial,onSave,pending}:{personas:Definition<Persona>[];initial?:Definition<Scenario>;onSave:(value:Scenario)=>void;pending:boolean}) {
  const [value,setValue]=useState<Scenario>(initial?.definition || {title:"",description:"",candidate_role:"",persona_id:personas[0]?.id || "",phases:[newPhase("phase-1")],competencies:["communication","empathy","problem_solving"],hidden_information:{},max_turns:12,duration_seconds:900,policy_query:""});
  const [hidden,setHidden]=useState(Object.entries(value.hidden_information).map(([key,text])=>({key,text})));
  function updatePhase(index:number,change:Partial<Phase>) {setValue({...value,phases:value.phases.map((p,i)=>i===index?{...p,...change}:p)});}
  return <form className="space-y-4" onSubmit={e=>{e.preventDefault();onSave({...value,hidden_information:Object.fromEntries(hidden.filter(row=>row.key.trim()&&row.text.trim()).map(row=>[row.key.trim(),row.text.trim()])),phases:value.phases.map(p=>({...p,objectives:p.objectives.map(v=>v.trim()).filter(Boolean),reveal_keys:p.reveal_keys.filter(Boolean)}))});}}>
    <h3 className="font-semibold">{initial?"Edit scenario":"Create a reusable scenario"}</h3>
    <label className="block text-sm">Title<input className={field} required maxLength={160} value={value.title} onChange={e=>setValue({...value,title:e.target.value})}/></label>
    <label className="block text-sm">Candidate brief<textarea className={field} required minLength={10} maxLength={1500} value={value.description} onChange={e=>setValue({...value,description:e.target.value})}/></label>
    <label className="block text-sm">Candidate role<input className={field} required minLength={2} maxLength={160} value={value.candidate_role} onChange={e=>setValue({...value,candidate_role:e.target.value})}/></label>
    <label className="block text-sm">Persona<select className={field} required value={value.persona_id} onChange={e=>setValue({...value,persona_id:e.target.value})}><option value="">Choose a persona</option>{personas.map(p=><option value={p.id} key={p.id}>{p.definition.name}</option>)}</select></label>
    <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">Duration (minutes)<input className={field} type="number" min={1} max={60} value={value.duration_seconds/60} onChange={e=>setValue({...value,duration_seconds:Number(e.target.value)*60})}/></label><label className="text-sm">Maximum candidate turns<input className={field} type="number" min={2} max={40} value={value.max_turns} onChange={e=>setValue({...value,max_turns:Number(e.target.value)})}/></label></div>
    <label className="block text-sm">Competencies (one per line)<textarea className={field} value={value.competencies.join("\n")} onChange={e=>setValue({...value,competencies:e.target.value.split("\n")})}/></label>
    <label className="block text-sm">Company policy search terms (optional)<input className={field} maxLength={250} placeholder="Refund policy" value={value.policy_query} onChange={e=>setValue({...value,policy_query:e.target.value})}/></label>
    <fieldset className="space-y-3 rounded-lg border border-border p-4"><legend className="px-1 text-sm font-semibold">Private scenario facts</legend><p className="text-xs text-text-muted">A fact is shared only when a phase explicitly releases its label.</p>
      {hidden.map((row,i)=><div key={i} className="grid gap-2 sm:grid-cols-[1fr_2fr_auto]"><input aria-label={`Private fact ${i+1} label`} className={field} placeholder="delivery_window" value={row.key} onChange={e=>setHidden(hidden.map((r,n)=>n===i?{...r,key:e.target.value}:r))}/><input aria-label={`Private fact ${i+1} text`} className={field} placeholder="Private fact" value={row.text} onChange={e=>setHidden(hidden.map((r,n)=>n===i?{...r,text:e.target.value}:r))}/><button type="button" className="text-sm text-error" onClick={()=>setHidden(hidden.filter((_,n)=>n!==i))}>Remove</button></div>)}
      <button type="button" className="text-sm text-brand underline" disabled={hidden.length>=20} onClick={()=>setHidden([...hidden,{key:"",text:""}])}>Add private fact</button>
    </fieldset>
    {value.phases.map((phase,i)=><fieldset key={phase.id} className="space-y-3 rounded-lg border border-border p-4"><legend className="px-1 text-sm font-semibold">Phase {i+1}</legend>
      <label className="block text-sm">Name<input className={field} required value={phase.title} onChange={e=>updatePhase(i,{title:e.target.value})}/></label><label className="block text-sm">Candidate-visible prompt<textarea className={field} required minLength={10} value={phase.brief} onChange={e=>updatePhase(i,{brief:e.target.value})}/></label>
      <label className="block text-sm">Objectives (one per line)<textarea className={field} required value={phase.objectives.join("\n")} onChange={e=>updatePhase(i,{objectives:e.target.value.split("\n")})}/></label>
      <label className="block text-sm">Advance when the candidate shows<select className={field} value={phase.advance_on[0]} onChange={e=>updatePhase(i,{advance_on:[e.target.value]})}>{["solution","clarification","empathy","commitment"].map(s=><option key={s} value={s}>{s}</option>)}</select></label>
      <label className="block text-sm">Private fact labels to release on entering this phase<input className={field} placeholder="delivery_window" value={phase.reveal_keys.join(", ")} onChange={e=>updatePhase(i,{reveal_keys:e.target.value.split(",").map(s=>s.trim())})}/></label>
      {value.phases.length>1&&<button type="button" className="text-sm text-error underline" onClick={()=>setValue({...value,phases:value.phases.filter((_,n)=>n!==i)})}>Remove phase</button>}
    </fieldset>)}
    <div className="flex flex-wrap gap-4"><button type="button" className="text-sm text-brand underline" disabled={value.phases.length>=8} onClick={()=>setValue({...value,phases:[...value.phases,newPhase(crypto.randomUUID())]})}>Add phase</button><button className={button} disabled={pending||!personas.length}>{pending?"Saving...":"Save scenario"}</button></div>
  </form>;
}
