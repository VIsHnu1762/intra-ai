/**
 * Intra AI — Candidates Server-State Query Hooks
 *
 * Provides TanStack Query hooks for candidate listings, candidate dossier,
 * and candidate application history.
 */

import { useQuery } from "@tanstack/react-query";
import {
  getCandidates,
  getCandidate,
  getCandidateApplications,
  getMyApplications,
  type CandidateListParams,
  type CandidateApplicationsResponse,
} from "@/lib/api/candidates";
import type {
  BackendCandidateResponse,
  BackendCandidateListResponse,
} from "@/types/api";

export const CANDIDATE_QUERY_KEYS = {
  all: ["candidates"] as const,
  lists: () => [...CANDIDATE_QUERY_KEYS.all, "list"] as const,
  list: (params?: CandidateListParams) => [...CANDIDATE_QUERY_KEYS.lists(), params] as const,
  details: () => [...CANDIDATE_QUERY_KEYS.all, "detail"] as const,
  detail: (id: string) => [...CANDIDATE_QUERY_KEYS.details(), id] as const,
  applications: (id: string) => [...CANDIDATE_QUERY_KEYS.detail(id), "applications"] as const,
  myApplications: () => [...CANDIDATE_QUERY_KEYS.all, "me", "applications"] as const,
};

/**
 * Hook to fetch candidate list for ATS Kanban / Table views.
 */
export function useCandidates(params?: CandidateListParams) {
  return useQuery<BackendCandidateListResponse, Error>({
    queryKey: CANDIDATE_QUERY_KEYS.list(params),
    queryFn: () => getCandidates(params),
  });
}

/**
 * Hook to fetch detailed candidate dossier including parsed resume.
 */
export function useCandidate(candidateId: string, options?: { enabled?: boolean }) {
  return useQuery<BackendCandidateResponse, Error>({
    queryKey: CANDIDATE_QUERY_KEYS.detail(candidateId),
    queryFn: () => getCandidate(candidateId),
    enabled: Boolean(candidateId) && (options?.enabled ?? true),
  });
}

/**
 * Hook to fetch all applications submitted by a specific candidate.
 */
export function useCandidateApplications(candidateId: string, options?: { enabled?: boolean }) {
  return useQuery<CandidateApplicationsResponse, Error>({
    queryKey: CANDIDATE_QUERY_KEYS.applications(candidateId),
    queryFn: () => getCandidateApplications(candidateId),
    enabled: Boolean(candidateId) && (options?.enabled ?? true),
  });
}

/**
 * Hook to fetch applications for the currently authenticated candidate (P4-013).
 */
export function useMyApplications(options?: { enabled?: boolean }) {
  return useQuery<CandidateApplicationsResponse, Error>({
    queryKey: CANDIDATE_QUERY_KEYS.myApplications(),
    queryFn: () => getMyApplications(),
    enabled: options?.enabled ?? true,
    // Recruiter invitations and instant meeting deadlines are time-sensitive;
    // keep an open candidate portal current without requiring a manual refresh.
    refetchInterval: 15000,
  });
}
