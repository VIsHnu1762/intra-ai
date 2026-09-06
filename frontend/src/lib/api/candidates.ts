/**
 * Intra AI — Candidates API Client Endpoints
 *
 * Verifiably mapped to backend/app/routes/candidates.py:
 * - GET /api/v1/candidates                           (EXISTING, admin/recruiter)
 * - GET /api/v1/candidates/{candidate_id}              (EXISTING, admin/recruiter)
 * - GET /api/v1/candidates/{candidate_id}/applications (EXISTING, admin/recruiter)
 */

import { apiClient } from "./client";
import type {
  BackendCandidateResponse,
  BackendCandidateListResponse,
  BackendApplicationResponse,
} from "@/types/api";

export interface CandidateListParams {
  page?: number;
  per_page?: number;
  search?: string;
}

export interface CandidateApplicationsResponse {
  applications: BackendApplicationResponse[];
  total: number;
}

/**
 * List all candidates (admin/recruiter).
 * Backend: GET /api/v1/candidates
 */
export async function getCandidates(
  params?: CandidateListParams
): Promise<BackendCandidateListResponse> {
  return apiClient<BackendCandidateListResponse>("/api/v1/candidates", {
    params: {
      page: params?.page,
      per_page: params?.per_page,
      search: params?.search,
    },
  });
}

/**
 * Get candidate dossier with parsed resume.
 * Backend: GET /api/v1/candidates/{candidate_id}
 */
export async function getCandidate(
  candidateId: string
): Promise<BackendCandidateResponse> {
  return apiClient<BackendCandidateResponse>(`/api/v1/candidates/${candidateId}`);
}

/**
 * Get all applications submitted by a specific candidate.
 * Backend: GET /api/v1/candidates/{candidate_id}/applications
 */
export async function getCandidateApplications(
  candidateId: string
): Promise<CandidateApplicationsResponse> {
  return apiClient<CandidateApplicationsResponse>(
    `/api/v1/candidates/${candidateId}/applications`
  );
}

/**
 * Get all applications submitted by the currently authenticated candidate.
 * Backend: GET /api/v1/candidates/me/applications (P4-013)
 */
export async function getMyApplications(): Promise<CandidateApplicationsResponse> {
  return apiClient<CandidateApplicationsResponse>("/api/v1/candidates/me/applications");
}

