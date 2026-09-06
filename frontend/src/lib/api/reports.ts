/**
 * Intra AI — Reports API Client Endpoints
 *
 * Recruiter assessment reads and explicit generation are separate from the
 * candidate-owned overall performance endpoint. All calls use bearer auth.
 */

import { apiClient } from "./client";
import type { BackendReportResponse, BackendReportListResponse, BackendReportStatusResponse, BackendCandidatePerformanceResponse } from "@/types/api";

export interface ReportListParams {
  page?: number;
  per_page?: number;
  recommendation?: string;
  job_id?: string;
  interview_id?: string;
}

/**
 * List assessment reports with optional filters and pagination.
 * Backend: GET /api/v1/reports
 */
export async function getReports(
  params?: ReportListParams
): Promise<BackendReportListResponse> {
  return apiClient<BackendReportListResponse>("/api/v1/reports", {
    params: {
      page: params?.page,
      per_page: params?.per_page,
      recommendation: params?.recommendation,
      job_id: params?.job_id,
      interview_id: params?.interview_id,
    },
  });
}

/**
 * Explicitly request generation; the 202 response contains its persisted status.
 * Backend: POST /api/v1/interviews/{interview_id}/report/generate
 */
export async function generateReport(interviewId: string): Promise<BackendReportStatusResponse> {
  return apiClient<BackendReportStatusResponse>(
    `/api/v1/interviews/${encodeURIComponent(interviewId)}/report/generate`,
    {
      method: "POST",
    }
  );
}

/**
 * Get the assessment report by report ID or interview ID.
 * Backend: GET /api/v1/reports/{id_or_interview_id}
 */
export async function getReport(idOrInterviewId: string): Promise<BackendReportResponse> {
  return apiClient<BackendReportResponse>(
    `/api/v1/reports/${encodeURIComponent(idOrInterviewId)}`
  );
}

/**
 * Get the assessment report explicitly by interview ID.
 * Backend: GET /api/v1/interviews/{interview_id}/report
 */
export async function getInterviewReport(interviewId: string): Promise<BackendReportResponse> {
  return apiClient<BackendReportResponse>(
    `/api/v1/interviews/${encodeURIComponent(interviewId)}/report`
  );
}

/** Read persisted generation state; never starts evaluation. */
export async function getReportStatus(idOrInterviewId: string): Promise<BackendReportStatusResponse> {
  return apiClient<BackendReportStatusResponse>(`/api/v1/reports/${encodeURIComponent(idOrInterviewId)}/status`);
}

/** Candidate-owned overall feedback only, separate from recruiter report data. */
export async function getCandidatePerformance(interviewId: string): Promise<BackendCandidatePerformanceResponse> {
  return apiClient<BackendCandidatePerformanceResponse>(`/api/v1/interviews/${encodeURIComponent(interviewId)}/performance`);
}
