from app.integrations.feature_db import execute, rpc, tenant_key


class RolePlayRepository:
    def __init__(self, sb): self.sb = sb

    async def definitions(self, actor, kind):
        return await execute(self.sb.table("roleplay_definitions").select("*").eq("created_by", actor.user_id)
            .eq("tenant_key", tenant_key(actor)).eq("kind", kind).order("created_at", desc=True).limit(100))

    async def definition(self, actor, key, kind):
        rows = await execute(self.sb.table("roleplay_definitions").select("*").eq("id", key)
            .eq("created_by", actor.user_id).eq("tenant_key", tenant_key(actor)).eq("kind", kind).limit(1))
        return rows[0] if rows else None

    async def save_definition(self, actor, key, kind, body, request_hash):
        return await rpc(self.sb, "save_roleplay_definition", p_actor=actor.user_id, p_id=key, p_kind=kind,
            p_expected_revision=body.expected_revision, p_request_id=str(body.request_id), p_request_hash=request_hash,
            p_definition=body.definition.model_dump(mode="json"))

    async def sessions(self, actor):
        query = self.sb.table("roleplay_sessions").select("*")
        if actor.role == "candidate": query = query.eq("candidate_id", actor.candidate_id or "__none__")
        else: query = query.eq("created_by", actor.user_id).eq("tenant_key", tenant_key(actor))
        return await execute(query.order("created_at", desc=True).limit(100))

    async def session(self, key):
        rows = await execute(self.sb.table("roleplay_sessions").select("*").eq("id", key).limit(1))
        return rows[0] if rows else None

    async def create_session(self, actor, payload):
        return await rpc(self.sb, "create_roleplay_session", p_actor=actor.user_id, p_payload=payload)

    async def events(self, key):
        return await execute(self.sb.table("roleplay_events").select("*").eq("session_id", key).order("revision").limit(100))

    async def event_request(self, key, request_id):
        rows = await execute(self.sb.table("roleplay_events").select("*").eq("session_id", key).eq("request_id", request_id).limit(1))
        return rows[0] if rows else None

    async def commit(self, actor, key, expected_revision, event, state):
        return await rpc(self.sb, "commit_roleplay_event", p_actor=actor.user_id, p_session_id=key,
                         p_expected_revision=expected_revision, p_event=event, p_state=state.model_dump(mode="json"))
