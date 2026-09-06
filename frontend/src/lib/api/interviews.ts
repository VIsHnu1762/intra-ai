/**
 * Intra AI — Interviews & Agora Voice Session Client Endpoints
 *
 * Verifiably mapped to backend/app/routes/interviews.py:
 * - GET  /api/v1/interviews/{interview_id}/agora-token        (EXISTING, public)
 * - GET  /api/v1/interviews/{interview_id}/agora-agent-config (EXISTING, public)
 * - POST /api/v1/interviews/{interview_id}/start             (EXISTING, authenticated)
 * - POST /api/v1/interviews/{interview_id}/end               (EXISTING, authenticated)
 */

import { apiClient } from "./client";
import type {
  BackendAgoraTokenResponse,
  BackendAgoraAgentConfigResponse,
} from "@/types/api";

/**
 * Fetch Agora RTC token for candidate or client joining an interview room.
 * Backend: GET /api/v1/interviews/{interview_id}/agora-token
 * PRESERVES EXISTING AGORA RTC TOKEN FLOW EXACTLY.
 */
export async function getAgoraToken(
  interviewId: string,
  uid: number = 0,
  role: number = 1
): Promise<BackendAgoraTokenResponse> {
  return apiClient<BackendAgoraTokenResponse>(
    `/api/v1/interviews/${interviewId}/agora-token`,
    {
      params: { uid, role },
      skipAuth: true,
    }
  );
}

/**
 * Fetch Agora Conversational AI Agent Studio configuration.
 * Backend: GET /api/v1/interviews/{interview_id}/agora-agent-config
 */
export async function getAgoraAgentConfig(
  interviewId: string,
  agentId: string = "alex",
  agentRtcUid: number = 1001,
  userUid: number = 0
): Promise<BackendAgoraAgentConfigResponse> {
  return apiClient<BackendAgoraAgentConfigResponse>(
    `/api/v1/interviews/${interviewId}/agora-agent-config`,
    {
      params: {
        agent_id: agentId,
        agent_rtc_uid: agentRtcUid,
        user_uid: userUid,
      },
      skipAuth: true,
    }
  );
}

/**
 * Start an interview session.
 * Backend: POST /api/v1/interviews/{interview_id}/start
 */
export async function startInterviewSession(
  interviewId: string
): Promise<Record<string, unknown>> {
  return apiClient<Record<string, unknown>>(
    `/api/v1/interviews/${interviewId}/start`,
    {
      method: "POST",
    }
  );
}

/**
 * End an interview session.
 * Backend: POST /api/v1/interviews/{interview_id}/end
 */
export async function endInterviewSession(
  interviewId: string
): Promise<Record<string, unknown>> {
  return apiClient<Record<string, unknown>>(
    `/api/v1/interviews/${interviewId}/end`,
    {
      method: "POST",
    }
  );
}
