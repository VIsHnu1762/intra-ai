/**
 * Intra AI — Applications Server-State Query & Mutation Hooks
 *
 * Provides TanStack Query hooks for job applications list, single application
 * inspection, shortlisting, rejecting, and submitting applications.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getJobApplications,
  getApplication,
  replaceApplicationResume,
  shortlistApplication,
  rejectApplication,
  inviteApplication,
  applyToJob,
  type JobApplicationListParams,
  type ApplyJobPayload,
} from "@/lib/api/applications";
import type {
  BackendApplicationResponse,
  BackendApplicationListResponse,
} from "@/types/api";

export const APPLICATION_QUERY_KEYS = {
  all: ["applications"] as const,
  byJob: (jobId: string, params?: JobApplicationListParams) =>
    [...APPLICATION_QUERY_KEYS.all, "by-job", jobId, params] as const,
  details: () => [...APPLICATION_QUERY_KEYS.all, "detail"] as const,
  detail: (id: string) => [...APPLICATION_QUERY_KEYS.details(), id] as const,
};

/**
 * Hook to fetch applications for a specific job.
 */
export function useJobApplications(jobId: string, params?: JobApplicationListParams) {
  return useQuery<BackendApplicationListResponse, Error>({
    queryKey: APPLICATION_QUERY_KEYS.byJob(jobId, params),
    queryFn: () => getJobApplications(jobId, params),
    enabled: Boolean(jobId),
  });
}

/**
 * Hook to fetch a single application dossier.
 */
export function useApplication(appId: string, options?: { enabled?: boolean }) {
  return useQuery<BackendApplicationResponse, Error>({
    queryKey: APPLICATION_QUERY_KEYS.detail(appId),
    queryFn: () => getApplication(appId),
    enabled: Boolean(appId) && (options?.enabled ?? true),
  });
}

/**
 * Mutation hook to apply to a job (multipart form with resume upload).
 */
export function useApplyToJob() {
  const queryClient = useQueryClient();

  return useMutation<BackendApplicationResponse, Error, ApplyJobPayload>({
    mutationFn: (payload) => applyToJob(payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({
        queryKey: APPLICATION_QUERY_KEYS.byJob(data.job_id),
      });
    },
  });
}

/**
 * Mutation hook to shortlist an application.
 */
export function useShortlistApplication() {
  const queryClient = useQueryClient();

  return useMutation<BackendApplicationResponse, Error, string>({
    mutationFn: (appId) => shortlistApplication(appId),
    onSuccess: (data, appId) => {
      queryClient.setQueryData(APPLICATION_QUERY_KEYS.detail(appId), data);
      queryClient.invalidateQueries({ queryKey: APPLICATION_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

/** Replace, parse, and rescore a resume from the recruiter dossier. */
export function useReplaceApplicationResume() {
  const queryClient = useQueryClient();

  return useMutation<BackendApplicationResponse, Error, { appId: string; resumeFile: File }>({
    mutationFn: ({ appId, resumeFile }) => replaceApplicationResume(appId, resumeFile),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(APPLICATION_QUERY_KEYS.detail(variables.appId), data);
      queryClient.invalidateQueries({ queryKey: APPLICATION_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

/**
 * Mutation hook to reject an application.
 */
export function useRejectApplication() {
  const queryClient = useQueryClient();

  return useMutation<BackendApplicationResponse, Error, string>({
    mutationFn: (appId) => rejectApplication(appId),
    onSuccess: (data, appId) => {
      queryClient.setQueryData(APPLICATION_QUERY_KEYS.detail(appId), data);
      queryClient.invalidateQueries({ queryKey: APPLICATION_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

/**
 * Mutation hook to invite an applicant to schedule an interview (P4-016).
 */
export function useInviteApplication() {
  const queryClient = useQueryClient();

  return useMutation<BackendApplicationResponse, Error, string>({
    mutationFn: (appId) => inviteApplication(appId),
    onSuccess: (data, appId) => {
      queryClient.setQueryData(APPLICATION_QUERY_KEYS.detail(appId), data);
      queryClient.invalidateQueries({ queryKey: APPLICATION_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}
