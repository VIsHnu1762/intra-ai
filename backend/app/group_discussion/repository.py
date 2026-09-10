from app.integrations.feature_db import execute,rpc,tenant_key


class GDRepository:
    def __init__(self,sb):self.sb=sb

    async def session(self,key):
        rows=await execute(self.sb.table("gd_sessions").select("*").eq("id",key).limit(1))
        return rows[0] if rows else None

    async def sessions(self,actor):
        if actor.role=="candidate":
            memberships=await execute(self.sb.table("gd_participants").select("session_id").eq("candidate_id",actor.candidate_id or "__none__").limit(100))
            if not memberships:return []
            return await execute(self.sb.table("gd_sessions").select("*").in_("id",[r["session_id"] for r in memberships]).order("created_at",desc=True).limit(100))
        return await execute(self.sb.table("gd_sessions").select("*").eq("created_by",actor.user_id).eq("tenant_key",tenant_key(actor)).order("created_at",desc=True).limit(100))

    async def participants(self,key):
        return await execute(self.sb.table("gd_participants").select("*").eq("session_id",key).order("created_at").limit(12))

    async def events(self,key):
        return await execute(self.sb.table("gd_events").select("*").eq("session_id",key).order("sequence").limit(1000))

    async def create(self,actor,payload):return await rpc(self.sb,"create_gd_session",p_actor=actor.user_id,p_payload=payload)

    async def invite(self,actor,key,payload):return await rpc(self.sb,"invite_gd_participant",p_actor=actor.user_id,p_session_id=key,p_payload=payload)

    async def accept(self,actor,key,token_hash,request_id):return await rpc(self.sb,"accept_gd_invitation",p_actor=actor.user_id,p_session_id=key,p_token_hash=token_hash,p_request_id=request_id)

    async def control(self,actor,key,body):return await rpc(self.sb,"control_gd_session",p_actor=actor.user_id,p_session_id=key,p_action=body.action,p_expected_revision=body.expected_revision,p_request_id=str(body.request_id))

    async def attendance(self,actor,key,action,request_id,participant_id=None):return await rpc(self.sb,"change_gd_participant",p_actor=actor.user_id,p_session_id=key,p_action=action,p_request_id=request_id,p_participant_id=participant_id)

    async def append(self,actor,key,event):return await rpc(self.sb,"append_gd_message",p_actor=actor.user_id,p_session_id=key,p_event=event)

    async def claim(self,key,lease):return await rpc(self.sb,"claim_gd_analysis",p_session_id=key,p_lease=lease)

    async def finish(self,key,event_id,lease,payload):return await rpc(self.sb,"finish_gd_analysis",p_session_id=key,p_event_id=event_id,p_lease=lease,p_payload=payload)
