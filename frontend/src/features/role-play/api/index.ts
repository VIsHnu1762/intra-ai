import { apiClient } from "@/lib/api/client";
import type { GroundedContext } from "@/features/company-knowledge/api";
export interface Persona { name: string; description: string; personality: string; communication_style: string; objectives: string[]; concerns: string[]; allowed_information: string[]; restricted_information: string[]; escalation_signals?: string[]; deescalation_signals?: string[]; initial_escalation?: number }
export interface Phase { id: string; title: string; brief: string; objectives: string[]; advance_on: string[]; min_turns: number; max_turns: number; reveal_keys: string[] }
export interface Scenario { title: string; description: string; candidate_role: string; persona_id: string; phases: Phase[]; competencies: string[]; hidden_information: Record<string,string>; max_turns: number; duration_seconds: number; policy_query: string; success_signals?: string[]; failure_signals?: string[] }
export interface Definition<T> { id: string; revision: number; definition: T; archived_at: string | null }
export interface AssessmentReport { kind: string; candidate_rating: number; performance_band: string; dimensions: Record<string,number>; evaluated_turns: number; total_turns?: number; unevaluated_turns?: number; policy_contexts?: GroundedContext[]; overall_score?: number; feedback?: { strengths: string[]; improvements: string[] }; narrative?: { summary: string; strengths: { text: string; evidence_ids: string[] }[]; improvements: { text: string; evidence_ids: string[] }[] }; evidence?: { id: string; event_id: string; competency: string; observation: string; quote: string; score: number; confidence: number }[] }
export interface RolePlaySession { id: string; title: string; description: string; candidate_role: string; persona_name: string; candidate_id?: string; status: "assigned"|"active"|"completed"|"cancelled"; revision: number; phase: {title:string;brief:string}; turn_count: number; time_remaining_seconds: number; report_status: string; report: AssessmentReport|null; realtime: { mode:string; voice_available:boolean; message:string }; events?: { id:string; revision:number; kind:string; text:string; response:string; created_at:string; analysis_status:string; policy_context:GroundedContext|null }[] }
const base="/api/v1/roleplay";
export const rolePlayApi={
  personas:()=>apiClient.get<Definition<Persona>[]>(`${base}/personas`),
  scenarios:()=>apiClient.get<Definition<Scenario>[]>(`${base}/scenarios`),
  savePersona:(definition:Persona,request_id:string,id?:string,expected_revision=0)=>(id?apiClient.put:apiClient.post)<Definition<Persona>>(id?`${base}/personas/${encodeURIComponent(id)}`:`${base}/personas`,{definition,request_id,expected_revision}),
  saveScenario:(definition:Scenario,request_id:string,id?:string,expected_revision=0)=>(id?apiClient.put:apiClient.post)<Definition<Scenario>>(id?`${base}/scenarios/${encodeURIComponent(id)}`:`${base}/scenarios`,{definition,request_id,expected_revision}),
  sessions:()=>apiClient.get<RolePlaySession[]>(`${base}/sessions`),
  createSession:(scenario_id:string,candidate_id:string,request_id:string)=>apiClient.post<RolePlaySession>(`${base}/sessions`,{scenario_id,candidate_id,request_id}),
  session:(id:string)=>apiClient.get<RolePlaySession>(`${base}/sessions/${encodeURIComponent(id)}`),
  control:(id:string,action:"start"|"finish"|"cancel",expected_revision:number,request_id:string)=>apiClient.post<RolePlaySession>(`${base}/sessions/${encodeURIComponent(id)}/control`,{action,expected_revision,request_id}),
  turn:(id:string,body:{text:string;expected_revision:number;request_id:string})=>apiClient.post<RolePlaySession>(`${base}/sessions/${encodeURIComponent(id)}/turns`,body),
  report:(id:string)=>apiClient.post<AssessmentReport>(`${base}/sessions/${encodeURIComponent(id)}/report`),
};
