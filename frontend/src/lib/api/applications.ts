/**
 * Intra AI — Applications API Client Endpoints
 *
 * Verifiably mapped to backend/app/routes/applications.py:
 * - POST /api/v1/jobs/{job_id}/apply             (EXISTING, public multipart)
 * - GET /api/v1/jobs/{job_id}/applications       (EXISTING, admin/recruiter)
 * - GET /api/v1/applications/{app_id}            (EXISTING, admin/recruiter)
 * - POST /api/v1/applications/{app_id}/shortlist (EXISTING, admin/recruiter)
 * - POST /api/v1/applications/{app_id}/reject    (EXISTING, admin/recruiter)
 */

import { apiClient } from "./client";
import type {
  BackendApplicationResponse,
  BackendApplicationListResponse,
} from "@/types/api";

export interface JobApplicationListParams {
  page?: number;
  per_page?: number;
  status?: string;
}

export interface ApplyJobPayload {
  jobId: string;
  name: string;
  email: string;
  phone: string;
  yearsExperience: number;
  resumeFile: File;
  currentRole?: string;
  currentCompany?: string;
  expectedSalaryMin?: number;
  expectedSalaryMax?: number;
  linkedinUrl?: string;
}

/**
 * Submit a job application with resume file upload.
 * Backend: POST /api/v1/jobs/{job_id}/apply (multipart/form-data)
 */
export async function applyToJob(payload: ApplyJobPayload): Promise<BackendApplicationResponse> {
  const formData = new FormData();
  formData.append("name", payload.name);
  formData.append("email", payload.email);
  formData.append("phone", payload.phone);
  formData.append("years_experience", String(payload.yearsExperience));
  formData.append("resume", payload.resumeFile);

  if (payload.currentRole) formData.append("current_role", payload.currentRole);
  if (payload.currentCompany) formData.append("current_company", payload.currentCompany);
  if (payload.expectedSalaryMin !== undefined)
    formData.append("expected_salary_min", String(payload.expectedSalaryMin));
  if (payload.expectedSalaryMax !== undefined)
    formData.append("expected_salary_max", String(payload.expectedSalaryMax));
  if (payload.linkedinUrl) formData.append("linkedin_url", payload.linkedinUrl);

  return apiClient<BackendApplicationResponse>(`/api/v1/jobs/${payload.jobId}/apply`, {
    method: "POST",
    body: formData,
    skipAuth: true,
  });
}

/**
 * List applications for a specific job posting.
 * Backend: GET /api/v1/jobs/{job_id}/applications
 */
export async function getJobApplications(
  jobId: string,
  params?: JobApplicationListParams
): Promise<BackendApplicationListResponse> {
  return apiClient<BackendApplicationListResponse>(`/api/v1/jobs/${jobId}/applications`, {
    params: {
      page: params?.page,
      per_page: params?.per_page,
      status: params?.status,
    },
  });
}

/**
 * Get a single application detail.
 * Backend: GET /api/v1/applications/{app_id}
 */
export async function getApplication(appId: string): Promise<BackendApplicationResponse> {
  return apiClient<BackendApplicationResponse>(`/api/v1/applications/${appId}`);
}

/** Replace and reparse a resume from the recruiter dossier. */
export async function replaceApplicationResume(
  appId: string,
  resumeFile: File,
): Promise<BackendApplicationResponse> {
  const formData = new FormData();
  formData.append("resume", resumeFile);
  return apiClient<BackendApplicationResponse>(`/api/v1/applications/${appId}/resume`, {
    method: "POST",
    body: formData,
  });
}

/**
 * Manually shortlist an application.
 * Backend: POST /api/v1/applications/{app_id}/shortlist
 */
export async function shortlistApplication(appId: string): Promise<BackendApplicationResponse> {
  return apiClient<BackendApplicationResponse>(`/api/v1/applications/${appId}/shortlist`, {
    method: "POST",
  });
}

/**
 * Manually reject an application.
 * Backend: POST /api/v1/applications/{app_id}/reject
 */
export async function rejectApplication(appId: string): Promise<BackendApplicationResponse> {
  return apiClient<BackendApplicationResponse>(`/api/v1/applications/${appId}/reject`, {
    method: "POST",
  });
}

/**
 * Invite an applicant to schedule an interview.
 * Backend: POST /api/v1/applications/{app_id}/invite (P4-016)
 */
export async function inviteApplication(appId: string): Promise<BackendApplicationResponse> {
  return apiClient<BackendApplicationResponse>(`/api/v1/applications/${appId}/invite`, {
    method: "POST",
  });
}
