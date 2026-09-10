export interface PolicyExcerpt {
  chunk_id: string;
  document_id: string;
  version_id: string;
  version: number;
  title: string;
  policy_key: string;
  effective_from: string;
  effective_until: string | null;
  text: string;
}

export interface GroundedPolicyContext {
  source: "company_policy";
  status: "available" | "unavailable" | "conflict";
  message: string;
  effective_at: string;
  excerpts: PolicyExcerpt[];
}
