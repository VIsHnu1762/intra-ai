import { ApiError, apiClient } from "./client";
import type { TaylorPracticeFeedback, TaylorPracticeOptions } from "@/lib/taylor-practice";

export type VoiceAgent = "taylor" | "morgan";
export type VoiceContext = {
  job_id?: string;
  candidate_id?: string;
  application_id?: string;
  interview_id?: string;
};
export type VoiceTranscriptEntry = { id?: string; role: string; text: string; at?: string };
export type VoicePendingAction = {
  confirmation_id: string;
  tool: string;
  summary?: string;
  details?: Record<string, unknown>;
  expires_at?: string;
};
export type VoiceSession = {
  session_id: string;
  agent_type: string;
  agent_name?: string;
  status: string;
  expires_at?: string;
  transcript?: VoiceTranscriptEntry[];
  pending_action?: VoicePendingAction | null;
  error?: string | null;
  message?: string;
  last_tool_result?: VoiceToolResult | null;
};
/** Short-lived RTC join material; kept in the owning hook's memory only. */
export type VoiceCredentials = VoiceSession & {
  app_id: string;
  channel_name: string;
  rtc_uid: number;
  rtc_token: string;
  agent_rtc_uid: string;
  rtm_token?: string;
  rtm_user_id?: string;
};
export type VoiceToolResult = {
  status?: string;
  message?: string;
  confirmation_id?: string;
  tool?: string;
  outcome_unknown?: boolean;
  result?: unknown;
  pending_action?: VoicePendingAction | null;
};

const path = (id: string) => `/api/v1/voice/sessions/${encodeURIComponent(id)}`;
const timeout = (milliseconds = 10_000) => ({ signal: AbortSignal.timeout(milliseconds) });
async function safeVoiceRequest<T>(request: Promise<T>): Promise<T> {
  try { return await request; }
  catch (error) {
    if (error instanceof ApiError) {
      const detail = (error.data as { detail?: { message?: unknown } } | undefined)?.detail;
      if (detail && typeof detail === "object" && typeof detail.message === "string") {
        throw new ApiError(detail.message, error.status);
      }
    }
    throw error;
  }
}
export const voiceAssistantsApi = {
  start: (agent: VoiceAgent, context: VoiceContext, practice?: TaylorPracticeOptions) => safeVoiceRequest(apiClient.post<VoiceCredentials>(`/api/v1/voice/${agent}/sessions`, { context, ...(agent === "taylor" && practice ? { practice } : {}) }, timeout(40_000))),
  finishPractice: (id: string) => safeVoiceRequest(apiClient.post<TaylorPracticeFeedback>(`${path(id)}/feedback`, {}, timeout(60_000))),
  practiceFeedback: (id: string) => safeVoiceRequest(apiClient.get<TaylorPracticeFeedback>(`${path(id)}/feedback`, timeout())),
  get: (id: string) => safeVoiceRequest(apiClient.get<VoiceSession>(path(id), timeout())),
  transcript: (id: string, events: VoiceTranscriptEntry[]) => safeVoiceRequest(apiClient.post<VoiceSession>(`${path(id)}/transcript-events`, { events }, timeout(5_000))),
  context: (id: string, context: VoiceContext) => safeVoiceRequest(apiClient.post<VoiceSession>(`${path(id)}/context`, { context }, timeout())),
  heartbeat: (id: string) => safeVoiceRequest(apiClient.post<VoiceSession>(`${path(id)}/heartbeat`, undefined, timeout())),
  end: (id: string) => safeVoiceRequest(apiClient.post<VoiceSession>(`${path(id)}/end`, undefined, { ...timeout(), keepalive: true })),
  confirm: (id: string, confirmationId: string, approved: boolean) => safeVoiceRequest(apiClient.post<VoiceToolResult>(`${path(id)}/confirm`, { confirmation_id: confirmationId, approved }, timeout(30_000))),
};
