import { apiClient } from "./client";
import type { InterviewRoundConfig } from "@/types";
import type { BackendJobResponse } from "@/types/api";
import type { InterviewAgent } from "@/lib/interview-templates";

export type InterviewTemplate = {
  id: string;
  name: string;
  description: string;
  rounds: InterviewRoundConfig[];
  duration_minutes: number;
  version: number;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
};
export type InterviewTemplateDraft = Pick<InterviewTemplate, "name" | "description" | "rounds">;
const base = "/api/v1/interview-templates";
const url = (id: string) => `${base}/${encodeURIComponent(id)}`;
export const interviewTemplatesApi = {
  list: (includeArchived = false) => apiClient.get<InterviewTemplate[]>(base, { params: { include_archived: includeArchived } }),
  create: (draft: InterviewTemplateDraft) => apiClient.post<InterviewTemplate>(base, draft),
  update: (id: string, draft: InterviewTemplateDraft, expectedVersion: number) => apiClient.patch<InterviewTemplate>(url(id), { ...draft, expected_version: expectedVersion }),
  archive: (id: string) => apiClient.post<InterviewTemplate>(`${url(id)}/archive`),
  applyToJob: (id: string, jobId: string) => apiClient.post<BackendJobResponse>(`${url(id)}/apply-to-job`, { job_id: jobId }),
  agents: () => apiClient.get<InterviewAgent[]>("/api/v1/agents"),
};
