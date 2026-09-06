/**
 * Intra AI — Scheduling API Client Endpoints (P4-017)
 *
 * Verifiably mapped to backend routes:
 * - GET /api/v1/jobs/{job_id}/slots
 * - POST /api/v1/applications/{app_id}/schedule
 * - POST /api/v1/applications/{app_id}/reschedule
 * - POST /api/v1/applications/{app_id}/instant
 * - POST /api/v1/applications/{app_id}/instant/respond
 * - GET /api/v1/interviews/{interview_id}
 */

import { apiClient } from "./client";
import type {
  BackendCreateSlotRequest,
  BackendInterviewSlotResponse,
  BackendScheduleInterviewRequest,
  BackendScheduledInterviewResponse,
} from "@/types/api";

/**
 * Fetch all available interview slots for a specific job.
 * Backend: GET /api/v1/jobs/{job_id}/slots
 */
export async function getAvailableSlots(
  jobId: string
): Promise<BackendInterviewSlotResponse[]> {
  return apiClient<BackendInterviewSlotResponse[]>(`/api/v1/jobs/${jobId}/slots`);
}

/**
 * Create available interview slots for a job.
 * Backend: POST /api/v1/jobs/{job_id}/slots
 */
export async function createInterviewSlots(
  jobId: string,
  slots: BackendCreateSlotRequest[]
): Promise<BackendInterviewSlotResponse[]> {
  return apiClient<BackendInterviewSlotResponse[]>(
    `/api/v1/jobs/${jobId}/slots`,
    {
      method: "POST",
      body: JSON.stringify(slots),
    }
  );
}

/**
 * Recruiter books an available interview slot for a shortlisted application.
 * Backend: POST /api/v1/applications/{app_id}/schedule
 */
export async function bookInterviewSlot(
  appId: string,
  slotId: string,
  templateId?: string
): Promise<BackendScheduledInterviewResponse> {
  return apiClient<BackendScheduledInterviewResponse>(
    `/api/v1/applications/${appId}/schedule`,
    {
      method: "POST",
      body: JSON.stringify({ slot_id: slotId, ...(templateId ? { template_id: templateId } : {}) } as BackendScheduleInterviewRequest),
    }
  );
}

/** Recruiter moves a scheduled interview to another available slot. */
export async function rescheduleInterview(
  appId: string,
  slotId: string
): Promise<BackendScheduledInterviewResponse> {
  return apiClient<BackendScheduledInterviewResponse>(
    `/api/v1/applications/${appId}/reschedule`,
    {
      method: "POST",
      body: JSON.stringify({ slot_id: slotId } as BackendScheduleInterviewRequest),
    }
  );
}

/** Recruiter sends a ten-minute instant interview invitation. */
export async function startInstantInterview(
  appId: string,
  templateId?: string
): Promise<BackendScheduledInterviewResponse> {
  return apiClient<BackendScheduledInterviewResponse>(
    `/api/v1/applications/${appId}/instant`,
    { method: "POST", ...(templateId ? { body: JSON.stringify({ template_id: templateId }) } : {}) }
  );
}

/** Candidate accepts a still-valid instant interview invitation. */
export async function respondToInstantInterview(
  appId: string
): Promise<BackendScheduledInterviewResponse> {
  return apiClient<BackendScheduledInterviewResponse>(
    `/api/v1/applications/${appId}/instant/respond`,
    { method: "POST" }
  );
}

/**
 * Fetch detailed scheduled interview metadata for preflight/lobby room.
 * Backend: GET /api/v1/interviews/{interview_id}
 */
export async function getInterview(
  interviewId: string
): Promise<BackendScheduledInterviewResponse> {
  return apiClient<BackendScheduledInterviewResponse>(
    `/api/v1/interviews/${interviewId}`
  );
}

export interface InterviewListParams {
  page?: number;
  per_page?: number;
  status?: string;
  job_id?: string;
}

/**
 * Fetch all interviews for admin/recruiter.
 * Backend: GET /api/v1/interviews
 */
export async function getInterviews(
  params?: InterviewListParams
): Promise<{ interviews: BackendScheduledInterviewResponse[]; total: number }> {
  return apiClient<{ interviews: BackendScheduledInterviewResponse[]; total: number }>(
    "/api/v1/interviews",
    {
      params: {
        page: params?.page,
        per_page: params?.per_page,
        status: params?.status,
        job_id: params?.job_id,
      },
    }
  );
}
