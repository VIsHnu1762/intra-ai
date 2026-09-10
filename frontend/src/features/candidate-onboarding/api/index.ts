import { apiClient } from "@/lib/api/client";

export interface Profile { skills: string[]; experience: { company: string; role: string }[]; education: { institution: string; degree: string }[]; projects: { name: string; description: string }[]; certifications: string[] }
export interface ResumeVersion { id: string; version: number; filename: string; extension: string; parse_source: string; created_at: string; profile: Profile }
export interface OnboardingStatus { needs_onboarding: boolean; source: string; current: ResumeVersion | null; profile: Profile | null; revision: number }
const base = "/api/v1/candidate/onboarding";
export const onboardingApi = {
  status: () => apiClient.get<OnboardingStatus>(`${base}/status`),
  versions: () => apiClient.get<ResumeVersion[]>(`${base}/resumes`),
  upload: (file: File, revision: number, requestId: string) => {
    const body = new FormData(); body.set("file", file); body.set("expected_revision", String(revision)); body.set("request_id", requestId);
    return apiClient.post<ResumeVersion>(`${base}/resumes`, body);
  },
  download: (id: string) => apiClient.get<Blob>(`${base}/resumes/${encodeURIComponent(id)}/download`, { responseType: "blob" }),
  apply: (jobId: string, details: { phone: string; years_experience: number; current_role?: string; current_company?: string; expected_salary_min?: number; expected_salary_max?: number; linkedin_url?: string; resume_version_id?: string }) => apiClient.post<{ id: string }>(`${base}/apply/${encodeURIComponent(jobId)}`, details),
};
