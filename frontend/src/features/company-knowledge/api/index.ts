import { apiClient } from "@/lib/api/client";
import type { GroundedPolicyContext } from "@/types/company-knowledge";
export interface CompanyDocument { id: string; title: string; policy_key: string; revision: number; archived_at: string | null; created_at: string }
export interface DocumentVersion { id: string; document_id: string; version: number; title: string; content: string; audience: "candidate" | "internal"; effective_from: string; effective_until: string | null; created_at: string }
export type GroundedContext = GroundedPolicyContext;
export interface DocumentDraft { title: string; policy_key: string; content: string; audience: "candidate" | "internal"; effective_from: string; effective_until?: string; expected_revision: number; request_id: string }
const base = "/api/v1/company-knowledge";
export const companyKnowledgeApi = {
  list: () => apiClient.get<CompanyDocument[]>(`${base}/documents`),
  save: (body: DocumentDraft, id?: string) => apiClient.post<DocumentVersion>(id ? `${base}/documents/${encodeURIComponent(id)}/versions` : `${base}/documents`, body),
  versions: (id: string) => apiClient.get<DocumentVersion[]>(`${base}/documents/${encodeURIComponent(id)}/versions`),
  archive: (doc: CompanyDocument) => apiClient.patch(`${base}/documents/${encodeURIComponent(doc.id)}/archive`, { expected_revision: doc.revision, archived: !doc.archived_at }),
  retrieve: (query: string) => apiClient.post<GroundedContext>(`${base}/retrieve`, { query }),
};
