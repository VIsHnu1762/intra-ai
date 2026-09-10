"use client";
import { useRef, useState } from "react";
import { useMutation,useQuery,useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import { PolicySources } from "@/components/knowledge/policy-sources";
import { rolePlayApi as api, type AssessmentReport } from "../api";

export function AssessmentFeedback({report}:{report:AssessmentReport}) {
  const strengths=report.feedback?.strengths||report.narrative?.strengths.map(i=>i.text)||[];
  const improvements=report.feedback?.improvements||report.narrative?.improvements.map(i=>i.text)||[];
  return <section className="space-y-4 rounded-2xl border border-border bg-surface p-5"><h2 className="text-lg font-semibold">Performance feedback</h2><p className="text-2xl font-semibold text-brand">{report.candidate_rating.toFixed(1)} / 5</p><p className="text-sm text-text-muted">{report.evaluated_turns} evaluated turns. Ratings describe observed behavior in this exercise.</p>{report.narrative&&<p>{report.narrative.summary}</p>}
    <div className="grid gap-5 sm:grid-cols-2"><div><h3 className="font-medium">Strengths</h3><ul className="mt-2 list-disc space-y-2 pl-5 text-sm">{strengths.map((text,i)=><li key={i}>{text}</li>)}</ul></div><div><h3 className="font-medium">Next steps</h3><ul className="mt-2 list-disc space-y-2 pl-5 text-sm">{improvements.map((text,i)=><li key={i}>{text}</li>)}</ul></div></div>
    {report.evidence&&<details><summary className="cursor-pointer text-sm font-medium">Supporting evidence</summary><ul className="mt-3 space-y-3">{report.evidence.map(e=><li key={e.id} className="border-t border-border pt-3 text-sm"><a className="text-brand underline" href={`#event-${e.event_id}`}>{e.competency}</a><blockquote className="mt-1 border-l-2 border-border pl-3">{e.quote}</blockquote><p className="mt-1 text-text-muted">{e.observation}</p></li>)}</ul></details>}
    {!!report.unevaluated_turns&&<p className="text-sm text-text-muted">{report.unevaluated_turns} saved responses could not be evaluated and did not contribute to this rating.</p>}
    {report.policy_contexts?.map((context,index)=><PolicySources key={index} context={context}/>)}
  </section>;
}

export default function RolePlaySessionPage({id,recruiter=false}:{id:string;recruiter?:boolean}) {
  const {user}=useAuth();const cache=useQueryClient();const [text,setText]=useState("");
  const request=useRef<{text:string;expected_revision:number;request_id:string}|null>(null);
  const key=["roleplay-session",id,user?.id];
  const session=useQuery({queryKey:key,queryFn:()=>api.session(id),retry:false,refetchInterval:q=>q.state.data?.status==="active"?3000:false});
  const turn=useMutation({mutationFn:()=>{
    if(!request.current||request.current.text!==text)request.current={text,expected_revision:session.data!.revision,request_id:crypto.randomUUID()};
    return api.turn(id,request.current);
  },onSuccess:data=>{cache.setQueryData(key,data);setText("");request.current=null;},onError:()=>{void cache.invalidateQueries({queryKey:key});}});
  const control=useMutation({mutationFn:(action:"start"|"finish"|"cancel")=>api.control(id,action,session.data!.revision,crypto.randomUUID()),onSuccess:data=>cache.setQueryData(key,data),onError:()=>{void cache.invalidateQueries({queryKey:key});}});
  const report=useMutation({mutationFn:()=>api.report(id),onSuccess:()=>{void cache.invalidateQueries({queryKey:key});}});
  if(session.isPending)return <p role="status" className="p-6">Loading simulation...</p>;
  if(session.error)return <p role="alert" className="p-6 text-error">{session.error.message}</p>;
  const data=session.data;const busy=turn.isPending||control.isPending;
  return <div className={recruiter?"space-y-6 p-4 sm:p-8":"space-y-6"}>
    <div><p className="text-xs uppercase tracking-wide text-text-muted">{data.status} - Text simulation</p><h1 className="mt-2 text-3xl font-semibold">{data.title}</h1><p className="mt-2 text-text-muted">{data.description}</p><p className="mt-2 text-sm">Your role: {data.candidate_role} | Character: {data.persona_name}</p></div>
    <aside className="rounded-xl border border-border bg-surface p-4 text-sm"><strong>{data.phase.title}</strong><p className="mt-1">{data.phase.brief}</p>{data.status==="active"&&<p className="mt-2 text-text-muted">About {Math.ceil(data.time_remaining_seconds/60)} minutes remaining. {data.turn_count} responses saved.</p>}</aside>
    <div className="flex flex-wrap gap-3">{!recruiter&&data.status==="assigned"&&<button className="rounded-lg bg-brand px-4 py-2 text-white" disabled={busy} onClick={()=>control.mutate("start")}>Start simulation</button>}{data.status==="active"&&<button className="rounded-lg border border-border px-4 py-2 text-sm" disabled={busy} onClick={()=>control.mutate("finish")}>Finish simulation</button>}{recruiter&&["assigned","active"].includes(data.status)&&<button className="text-sm text-error underline" disabled={busy} onClick={()=>control.mutate("cancel")}>Cancel assignment</button>}</div>
    <section aria-label="Conversation" aria-live="polite" className="space-y-4">{data.events?.map(event=><article id={`event-${event.id}`} key={event.id} className="space-y-3">
      {event.text&&<div className="ml-4 rounded-2xl border border-brand/15 bg-brand-light p-4 sm:ml-16"><p className="text-xs font-semibold text-brand">Candidate</p><p className="mt-1 whitespace-pre-wrap">{event.text}</p>{event.analysis_status==="unavailable"&&<p className="mt-2 text-xs text-text-muted">Response saved; AI evaluation was unavailable for this turn.</p>}</div>}
      <div className="mr-4 rounded-2xl border border-border bg-surface p-4 sm:mr-16"><p className="text-xs font-semibold text-text-muted">{data.persona_name}</p><p className="mt-1 whitespace-pre-wrap">{event.response}</p></div>
      <PolicySources context={event.policy_context}/>
    </article>)}</section>
    {!recruiter&&data.status==="active"&&<form className="space-y-3 rounded-2xl border border-border bg-surface p-4" onSubmit={e=>{e.preventDefault();turn.mutate();}}><label htmlFor="roleplay-response" className="text-sm font-medium">Your response</label><textarea id="roleplay-response" className="block min-h-28 w-full rounded-lg border border-border bg-bg p-3" maxLength={4000} required value={text} onChange={e=>setText(e.target.value)}/><button className="rounded-lg bg-brand px-5 py-2 text-white disabled:opacity-50" disabled={busy||!text.trim()||data.time_remaining_seconds<=0}>{turn.isPending?"Responding...":"Send response"}</button>{turn.error&&<button type="button" className="ml-4 text-sm underline" onClick={()=>{request.current=null;void session.refetch();}}>Refresh before retry</button>}</form>}
    {(turn.error||control.error||report.error)&&<p role="alert" className="text-error">{turn.error?.message||control.error?.message||report.error?.message}</p>}
    {data.status==="completed"&&!data.report&&<section className="rounded-xl border border-border bg-surface p-5"><p className="mb-3 text-sm text-text-muted">Feedback requires at least two evaluated responses. Your conversation is saved.</p><button className="rounded-lg bg-brand px-4 py-2 text-white disabled:opacity-50" disabled={report.isPending} onClick={()=>report.mutate()}>{report.isPending?"Preparing feedback...":data.report_status==="failed"?"Retry feedback":"Generate feedback"}</button></section>}
    {data.report&&<AssessmentFeedback report={data.report}/>}
  </div>;
}
