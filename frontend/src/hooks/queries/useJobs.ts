/**
 * Intra AI — Jobs Server-State Query & Mutation Hooks
 *
 * Provides TanStack Query hooks for public and administrative job listings,
 * single job retrieval, and automated cache invalidation upon mutations.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getPublicJobs,
  getPublicJob,
  getJob,
  getJobs,
  createJob,
  updateJob,
  publishJob,
  archiveJob,
  parseJdFile,
  parseJdText,
  type JobListParams,
} from "@/lib/api/jobs";
import type {
  BackendJobResponse,
  BackendJobListResponse,
  BackendJobCreatePayload,
  BackendJobUpdatePayload,
  JdParseResponse,
  JdTextParsePayload,
} from "@/types/api";


export const JOB_QUERY_KEYS = {
  all: ["jobs"] as const,
  lists: () => [...JOB_QUERY_KEYS.all, "list"] as const,
  list: (params?: JobListParams) => [...JOB_QUERY_KEYS.lists(), params] as const,
  publicLists: () => [...JOB_QUERY_KEYS.all, "public-list"] as const,
  publicList: (params?: JobListParams) => [...JOB_QUERY_KEYS.publicLists(), params] as const,
  details: () => [...JOB_QUERY_KEYS.all, "detail"] as const,
  detail: (id: string) => [...JOB_QUERY_KEYS.details(), id] as const,
};

/**
 * Hook to fetch public job listings (no auth required).
 */
export function usePublicJobs(params?: JobListParams) {
  return useQuery<BackendJobListResponse, Error>({
    queryKey: JOB_QUERY_KEYS.publicList(params),
    queryFn: () => getPublicJobs(params),
  });
}

/**
 * Hook to fetch a single job by ID (public).
 */
export function usePublicJob(jobId: string, options?: { enabled?: boolean }) {
  return useQuery<BackendJobResponse, Error>({
    queryKey: [...JOB_QUERY_KEYS.details(), "public", jobId] as const,
    queryFn: () => getPublicJob(jobId),
    enabled: Boolean(jobId) && (options?.enabled ?? true),
  });
}

/**
 * Hook to fetch a single job by ID (admin/recruiter).
 */
export function useJob(jobId: string, options?: { enabled?: boolean }) {
  return useQuery<BackendJobResponse, Error>({
    queryKey: JOB_QUERY_KEYS.detail(jobId),
    queryFn: () => getJob(jobId),
    enabled: Boolean(jobId) && (options?.enabled ?? true),
  });
}

/**
 * Hook to fetch administrative jobs list (admin/recruiter only).
 */
export function useJobs(params?: JobListParams) {
  return useQuery<BackendJobListResponse, Error>({
    queryKey: JOB_QUERY_KEYS.list(params),
    queryFn: () => getJobs(params),
  });
}

/**
 * Mutation hook to create a new draft job.
 */
export function useCreateJob() {
  const queryClient = useQueryClient();

  return useMutation<BackendJobResponse, Error, BackendJobCreatePayload>({
    mutationFn: (payload) => createJob(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: JOB_QUERY_KEYS.all });
    },
  });
}

/**
 * Mutation hook to update a job.
 */
export function useUpdateJob(jobId: string) {
  const queryClient = useQueryClient();

  return useMutation<BackendJobResponse, Error, BackendJobUpdatePayload>({
    mutationFn: (payload) => updateJob(jobId, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(JOB_QUERY_KEYS.detail(jobId), data);
      queryClient.invalidateQueries({ queryKey: JOB_QUERY_KEYS.lists() });
    },
  });
}

/**
 * Mutation hook to publish a draft job.
 */
export function usePublishJob() {
  const queryClient = useQueryClient();

  return useMutation<BackendJobResponse, Error, string>({
    mutationFn: (jobId) => publishJob(jobId),
    onSuccess: (data, jobId) => {
      queryClient.setQueryData(JOB_QUERY_KEYS.detail(jobId), data);
      queryClient.invalidateQueries({ queryKey: JOB_QUERY_KEYS.all });
    },
  });
}

/**
 * Mutation hook to archive a job.
 */
export function useArchiveJob() {
  const queryClient = useQueryClient();

  return useMutation<BackendJobResponse, Error, string>({
    mutationFn: (jobId) => archiveJob(jobId),
    onSuccess: (data, jobId) => {
      queryClient.setQueryData(JOB_QUERY_KEYS.detail(jobId), data);
      queryClient.invalidateQueries({ queryKey: JOB_QUERY_KEYS.all });
    },
  });
}

/**
 * Mutation hook to parse a JD file (PDF or DOCX).
 */
export function useParseJdFile() {
  return useMutation<JdParseResponse, Error, File>({
    mutationFn: (file) => parseJdFile(file),
  });
}

/**
 * Mutation hook to parse raw JD text.
 */
export function useParseJdText() {
  return useMutation<JdParseResponse, Error, JdTextParsePayload>({
    mutationFn: (payload) => parseJdText(payload),
  });
}

