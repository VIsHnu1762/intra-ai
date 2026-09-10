import { apiClient } from "@/lib/api/client";
import type { GroundedPolicyContext } from "@/types/company-knowledge";

export type DiscussionStatus = "lobby" | "active" | "completed" | "cancelled";
export interface DiscussionSummary { id: string; title: string; topic: string; status: DiscussionStatus; created_at: string }
export interface Participant {
  id: string;
  display_name: string;
  status: "invited" | "joined" | "left" | "removed";
  hand_raised: boolean;
  candidate_id?: string;
  report_status?: string;
}
export interface DiscussionEvent {
  id: string;
  sequence: number;
  participant_id: string | null;
  kind: string;
  text: string;
  response: string;
  reply_to: string | null;
  created_at: string;
  analysis_status?: string | null;
  policy_context?: GroundedPolicyContext | null;
}
export interface IndividualReport {
  kind: "group_discussion";
  candidate_rating: number;
  performance_band: string;
  evaluated_turns: number;
  total_turns: number;
  unevaluated_turns: number;
  participation: Record<string, number | boolean | string | null>;
  feedback?: { strengths: string[]; improvements: string[] };
  narrative?: { summary: string; strengths: { text: string; evidence_ids: string[] }[]; improvements: { text: string; evidence_ids: string[] }[] };
  evidence?: { id: string; competency: string; quote: string; event_id: string }[];
  policy_contexts?: GroundedPolicyContext[];
}
export interface Discussion extends Omit<DiscussionSummary, "created_at"> {
  revision: number;
  min_participants: number;
  max_participants: number;
  duration_seconds: number;
  time_remaining_seconds: number;
  realtime: { mode: string; voice_available: boolean; message?: string };
  own_participant_id: string | null;
  participants: Participant[];
  events: DiscussionEvent[];
  analysis_pending: number;
  report_status: string | null;
  report: IndividualReport | null;
}
export interface DiscussionConfiguration {
  title: string;
  topic: string;
  duration_seconds: number;
  min_participants: number;
  max_participants: number;
  competencies: string[];
  policy_query: string;
}
export interface Invitation { participant_id: string; expires_at: string; join_url: string }
const base = "/api/v1/group-discussions";
const sessionPath = (id: string) => `${base}/${encodeURIComponent(id)}`;
export const discussions = {
  list: () => apiClient.get<DiscussionSummary[]>(base),
  get: (id: string) => apiClient.get<Discussion>(sessionPath(id)),
  create: (configuration: DiscussionConfiguration, request_id: string) => apiClient.post<Discussion>(base, { configuration, request_id }),
  invite: (id: string, candidate_id: string, request_id: string) => apiClient.post<Invitation>(`${sessionPath(id)}/invitations`, { candidate_id, request_id }),
  join: (id: string, token: string, request_id: string) => apiClient.post<Discussion>(`${sessionPath(id)}/join`, { token, request_id }),
  control: (id: string, action: "start" | "finish" | "cancel", expected_revision: number, request_id: string) => apiClient.post<Discussion>(`${sessionPath(id)}/control`, { action, expected_revision, request_id }),
  participate: (id: string, action: "leave" | "rejoin" | "raise_hand" | "lower_hand", request_id: string) => apiClient.post<Discussion>(`${sessionPath(id)}/participation`, { action, request_id }),
  remove: (id: string, participant: string, request_id: string) => apiClient.post<Discussion>(`${sessionPath(id)}/participants/${encodeURIComponent(participant)}/remove`, { request_id }),
  message: (id: string, text: string, reply_to: string | null, request_id: string) => apiClient.post<Discussion>(`${sessionPath(id)}/messages`, { text, reply_to, request_id }),
  report: (id: string, participant: string) => apiClient.post<IndividualReport>(`${sessionPath(id)}/participants/${encodeURIComponent(participant)}/report`),
};
