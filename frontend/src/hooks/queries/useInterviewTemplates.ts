import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { interviewTemplatesApi, type InterviewTemplateDraft } from "@/lib/api/interview-templates";

export const INTERVIEW_TEMPLATE_QUERY_KEY = ["interview-templates"] as const;
export function useInterviewTemplates(includeArchived = false) {
  return useQuery({ queryKey: [...INTERVIEW_TEMPLATE_QUERY_KEY, { includeArchived }], queryFn: () => interviewTemplatesApi.list(includeArchived) });
}
export function useInterviewAgents() {
  return useQuery({ queryKey: ["interview-agents"], queryFn: interviewTemplatesApi.agents });
}
export function useSaveInterviewTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, draft, version }: { id?: string; draft: InterviewTemplateDraft; version?: number }) => id ? interviewTemplatesApi.update(id, draft, version || 1) : interviewTemplatesApi.create(draft),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INTERVIEW_TEMPLATE_QUERY_KEY }),
  });
}
export function useArchiveInterviewTemplate() {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: interviewTemplatesApi.archive, onSuccess: () => queryClient.invalidateQueries({ queryKey: INTERVIEW_TEMPLATE_QUERY_KEY }) });
}
export function useApplyInterviewTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, jobId }: { id: string; jobId: string }) => interviewTemplatesApi.applyToJob(id, jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
