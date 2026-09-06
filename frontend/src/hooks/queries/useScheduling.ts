/**
 * Intra AI — Interview Scheduling Query & Mutation Hooks (P4-017)
 *
 * Provides TanStack Query hooks for querying available interview slots,
 * booking an interview slot, and querying scheduled interview details.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getAvailableSlots,
  createInterviewSlots,
  bookInterviewSlot,
  rescheduleInterview,
  startInstantInterview,
  respondToInstantInterview,
  getInterview,
  getInterviews,
  type InterviewListParams,
} from "@/lib/api/scheduling";
import type {
  BackendCreateSlotRequest,
  BackendInterviewSlotResponse,
  BackendScheduledInterviewResponse,
} from "@/types/api";
import { APPLICATION_QUERY_KEYS } from "./useApplications";
import { CANDIDATE_QUERY_KEYS } from "./useCandidates";

export const SCHEDULING_QUERY_KEYS = {
  all: ["scheduling"] as const,
  slots: (jobId: string) => [...SCHEDULING_QUERY_KEYS.all, "slots", jobId] as const,
  interview: (interviewId: string) => [...SCHEDULING_QUERY_KEYS.all, "interview", interviewId] as const,
  list: (params?: InterviewListParams) => [...SCHEDULING_QUERY_KEYS.all, "list", params] as const,
};

/**
 * Hook to query all scheduled interviews for admin/recruiter.
 */
export function useInterviews(params?: InterviewListParams) {
  return useQuery<{ interviews: BackendScheduledInterviewResponse[]; total: number }, Error>({
    queryKey: SCHEDULING_QUERY_KEYS.list(params),
    queryFn: () => getInterviews(params),
  });
}

/**
 * Hook to query available interview slots for a job.
 */
export function useInterviewSlots(
  jobId: string,
  options?: { enabled?: boolean }
) {
  return useQuery<BackendInterviewSlotResponse[], Error>({
    queryKey: SCHEDULING_QUERY_KEYS.slots(jobId),
    queryFn: () => getAvailableSlots(jobId),
    enabled: Boolean(jobId) && (options?.enabled ?? true),
  });
}

/**
 * Hook to query scheduled interview details.
 */
export function useInterview(
  interviewId: string,
  options?: { enabled?: boolean }
) {
  return useQuery<BackendScheduledInterviewResponse, Error>({
    queryKey: SCHEDULING_QUERY_KEYS.interview(interviewId),
    queryFn: () => getInterview(interviewId),
    enabled: Boolean(interviewId) && (options?.enabled ?? true),
  });
}

/**
 * Hook for HR to book an interview slot for an application.
 */
export function useBookInterviewSlot() {
  const queryClient = useQueryClient();

  return useMutation<
    BackendScheduledInterviewResponse,
    Error,
    { applicationId: string; slotId: string; templateId?: string }
  >({
    mutationFn: ({ applicationId, slotId, templateId }) =>
      bookInterviewSlot(applicationId, slotId, templateId),
    onSuccess: (data, variables) => {
      // Invalidate slots for this job if job is known
      if (data.job?.id) {
        queryClient.invalidateQueries({
          queryKey: SCHEDULING_QUERY_KEYS.slots(data.job.id),
        });
      }
      // Invalidate specific scheduled interview if ID returned
      if (data.id) {
        queryClient.invalidateQueries({
          queryKey: SCHEDULING_QUERY_KEYS.interview(data.id),
        });
      }
      // Invalidate all scheduling queries
      queryClient.invalidateQueries({
        queryKey: SCHEDULING_QUERY_KEYS.all,
      });
      // Invalidate application detail and candidate applications
      queryClient.invalidateQueries({
        queryKey: APPLICATION_QUERY_KEYS.detail(variables.applicationId),
      });
      queryClient.invalidateQueries({
        queryKey: CANDIDATE_QUERY_KEYS.myApplications(),
      });
      queryClient.invalidateQueries({
        queryKey: CANDIDATE_QUERY_KEYS.all,
      });
    },
  });
}

/** Hook for HR to move a scheduled interview to another slot. */
export function useRescheduleInterview() {
  const queryClient = useQueryClient();

  return useMutation<
    BackendScheduledInterviewResponse,
    Error,
    { applicationId: string; slotId: string }
  >({
    mutationFn: ({ applicationId, slotId }) =>
      rescheduleInterview(applicationId, slotId),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: SCHEDULING_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: APPLICATION_QUERY_KEYS.detail(variables.applicationId) });
      queryClient.invalidateQueries({ queryKey: CANDIDATE_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: CANDIDATE_QUERY_KEYS.myApplications() });
      if (data.id) {
        queryClient.invalidateQueries({ queryKey: SCHEDULING_QUERY_KEYS.interview(data.id) });
      }
    },
  });
}

/** Hook for HR to send a ten-minute instant interview invitation. */
export function useStartInstantInterview() {
  const queryClient = useQueryClient();

  return useMutation<BackendScheduledInterviewResponse, Error, string | { applicationId: string; templateId?: string }>({
    mutationFn: (input) => typeof input === "string" ? startInstantInterview(input) : startInstantInterview(input.applicationId, input.templateId),
    onSuccess: (data, input) => {
      const applicationId = typeof input === "string" ? input : input.applicationId;
      queryClient.invalidateQueries({ queryKey: SCHEDULING_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: APPLICATION_QUERY_KEYS.detail(applicationId) });
      queryClient.invalidateQueries({ queryKey: CANDIDATE_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: CANDIDATE_QUERY_KEYS.myApplications() });
    },
  });
}

/** Hook for a candidate to accept an instant invitation before expiry. */
export function useRespondToInstantInterview() {
  const queryClient = useQueryClient();

  return useMutation<BackendScheduledInterviewResponse, Error, string>({
    mutationFn: (applicationId) => respondToInstantInterview(applicationId),
    onSuccess: (data, applicationId) => {
      queryClient.invalidateQueries({ queryKey: CANDIDATE_QUERY_KEYS.myApplications() });
      queryClient.invalidateQueries({ queryKey: APPLICATION_QUERY_KEYS.detail(applicationId) });
      if (data.id) {
        queryClient.invalidateQueries({ queryKey: SCHEDULING_QUERY_KEYS.interview(data.id) });
      }
    },
  });
}

/**
 * Hook to create interview slots for a job (admin/recruiter).
 */
export function useCreateInterviewSlots() {
  const queryClient = useQueryClient();

  return useMutation<
    BackendInterviewSlotResponse[],
    Error,
    { jobId: string; slots: BackendCreateSlotRequest[] }
  >({
    mutationFn: ({ jobId, slots }) => createInterviewSlots(jobId, slots),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: SCHEDULING_QUERY_KEYS.slots(variables.jobId),
      });
      queryClient.invalidateQueries({
        queryKey: SCHEDULING_QUERY_KEYS.all,
      });
    },
  });
}
