/**
 * Intra AI — Jobs API Client Endpoints
 *
 * Verifiably mapped to backend/app/routes/jobs.py:
 * - GET /api/v1/jobs/public           (EXISTING, public)
 * - GET /api/v1/jobs/public/{job_id}  (EXISTING, public)
 * - GET /api/v1/jobs                  (EXISTING, admin/recruiter)
 * - POST /api/v1/jobs                 (EXISTING, admin/recruiter)
 * - PATCH /api/v1/jobs/{job_id}       (EXISTING, admin/recruiter)
 * - POST /api/v1/jobs/{job_id}/publish(EXISTING, admin/recruiter)
 * - POST /api/v1/jobs/{job_id}/archive(EXISTING, admin/recruiter)
 */

import { apiClient } from "./client";
import type {
  BackendJobResponse,
  BackendJobListResponse,
  BackendJobCreatePayload,
  BackendJobUpdatePayload,
  JdParseResponse,
  JdTextParsePayload,
} from "@/types/api";


export interface JobListParams {
  page?: number;
  per_page?: number;
  search?: string;
  department?: string;
  status?: string;
}

/**
 * Fetch public job listings (no auth required).
 * Backend: GET /api/v1/jobs/public
 */
export async function getPublicJobs(params?: JobListParams): Promise<BackendJobListResponse> {
  return apiClient<BackendJobListResponse>("/api/v1/jobs/public", {
    params: {
      page: params?.page,
      per_page: params?.per_page,
      search: params?.search,
      department: params?.department,
    },
    skipAuth: true,
  });
}

/**
 * Fetch a single public job by ID.
 * Backend: GET /api/v1/jobs/public/{job_id}
 */
export async function getPublicJob(jobId: string): Promise<BackendJobResponse> {
  return apiClient<BackendJobResponse>(`/api/v1/jobs/public/${jobId}`, {
    skipAuth: true,
  });
}

/**
 * Fetch a single job by ID (admin/recruiter).
 * Backend: GET /api/v1/jobs/{job_id}
 */
export async function getJob(jobId: string): Promise<BackendJobResponse> {
  return apiClient<BackendJobResponse>(`/api/v1/jobs/${jobId}`);
}

/**
 * Fetch all jobs for administrative dashboard (admin/recruiter only).
 * Backend: GET /api/v1/jobs
 */
export async function getJobs(params?: JobListParams): Promise<BackendJobListResponse> {
  return apiClient<BackendJobListResponse>("/api/v1/jobs", {
    params: {
      page: params?.page,
      per_page: params?.per_page,
      status: params?.status,
      search: params?.search,
      department: params?.department,
    },
  });
}

/**
 * Create a new draft job posting.
 * Backend: POST /api/v1/jobs
 */
export async function createJob(data: BackendJobCreatePayload): Promise<BackendJobResponse> {
  return apiClient<BackendJobResponse>("/api/v1/jobs", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Update an existing job posting.
 * Backend: PATCH /api/v1/jobs/{job_id}
 */
export async function updateJob(
  jobId: string,
  data: BackendJobUpdatePayload
): Promise<BackendJobResponse> {
  return apiClient<BackendJobResponse>(`/api/v1/jobs/${jobId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

/**
 * Publish a draft job posting.
 * Backend: POST /api/v1/jobs/{job_id}/publish
 */
export async function publishJob(jobId: string): Promise<BackendJobResponse> {
  return apiClient<BackendJobResponse>(`/api/v1/jobs/${jobId}/publish`, {
    method: "POST",
  });
}

/**
 * Archive an active or draft job posting.
 * Backend: POST /api/v1/jobs/{job_id}/archive
 */
export async function archiveJob(jobId: string): Promise<BackendJobResponse> {
  return apiClient<BackendJobResponse>(`/api/v1/jobs/${jobId}/archive`, {
    method: "POST",
  });
}

/**
 * Parse an uploaded JD file (PDF or DOCX).
 * Backend: POST /api/v1/jobs/parse-jd
 */
export async function parseJdFile(file: File): Promise<JdParseResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return apiClient<JdParseResponse>("/api/v1/jobs/parse-jd", {
    method: "POST",
    body: formData,
  });
}

/**
 * Parse raw JD text string.
 * Backend: POST /api/v1/jobs/parse-jd
 */
export async function parseJdText(payload: JdTextParsePayload): Promise<JdParseResponse> {
  return apiClient<JdParseResponse>("/api/v1/jobs/parse-jd", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

