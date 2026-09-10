from app.integrations.feature_db import execute, rpc, tenant_key


class CompanyKnowledgeRepository:
    def __init__(self, sb): self.sb = sb

    async def documents(self, actor):
        return await execute(self.sb.table("company_documents").select("*").eq("created_by", actor.user_id)
                             .eq("tenant_key", tenant_key(actor)).order("created_at", desc=True).limit(100))

    async def document(self, actor, document_id):
        rows = await execute(self.sb.table("company_documents").select("*").eq("id", document_id)
                             .eq("created_by", actor.user_id).eq("tenant_key", tenant_key(actor)).limit(1))
        return rows[0] if rows else None

    async def versions(self, document_id):
        return await execute(self.sb.table("company_document_versions").select("*").eq("document_id", document_id)
                             .order("version", desc=True).limit(100))

    async def save(self, actor, document_id, payload, revision):
        return await rpc(self.sb, "save_company_document", p_actor=actor.user_id, p_document_id=document_id,
                         p_expected_revision=revision, p_payload=payload)

    async def retrieve(self, owner_id, scope, query, effective_at, candidate_visible):
        return await rpc(self.sb, "retrieve_company_chunks", p_owner_id=owner_id, p_tenant_key=scope,
                         p_query=query, p_effective_at=effective_at.isoformat(), p_candidate_visible=candidate_visible)
