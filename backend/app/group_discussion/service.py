import base64
import hashlib
import hmac
import json
from datetime import datetime,timedelta,timezone
from uuid import NAMESPACE_URL,uuid4,uuid5

from app.core.config import settings
from app.core.exceptions import AppError,ForbiddenError,NotFoundError,ValidationError
from app.integrations.assessment_realtime import LocalTextSessionAdapter
from app.integrations.feature_db import tenant_key
from app.voice.authorization import require_candidate,require_recruiter
from app.intelligence.group_discussion.signals import participation_signals
from app.group_discussion.repository import GDRepository
from app.group_discussion.processing import GDProcessing
from app.group_discussion.reporting import GDReporting,report_view


def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()


class GDService:
    def __init__(self,sb,client=None,secret=None,policy_enricher=None):
        self.repo=GDRepository(sb);self.client=client;self.processing=GDProcessing(self.repo,client,policy_enricher)
        self.secret=secret if secret is not None else settings.GD_INVITATION_SECRET or settings.JWT_SECRET
        self.realtime=LocalTextSessionAdapter()

    async def require_session(self,actor,key,owner_only=False):
        row=await self.repo.session(key)
        if not row:raise NotFoundError("Discussion not found")
        participants=await self.repo.participants(key)
        participant=None
        if actor.role=="candidate" and not owner_only:
            participant=next((p for p in participants if str(p["candidate_id"])==actor.candidate_id),None)
            if not participant or participant["status"]=="removed":raise NotFoundError("Discussion not found")
        else:
            require_recruiter(actor)
            if str(row["created_by"])!=actor.user_id or row["tenant_key"]!=tenant_key(actor):raise NotFoundError("Discussion not found")
        return row,participants,participant

    async def create(self,actor,body):
        require_recruiter(actor)
        payload={"id":str(uuid5(NAMESPACE_URL,actor.user_id+":gd-session:"+str(body.request_id))),
            "request_id":str(body.request_id),"request_hash":fingerprint(body.model_dump(mode="json")),
            "configuration":body.configuration.model_dump(mode="json")}
        return await self.repo.create(actor,payload)

    async def invite(self,actor,key,body):
        await self.require_session(actor,key,owner_only=True)
        candidate=await require_candidate(actor,body.candidate_id,self.repo.sb)
        if len(self.secret.encode())<32:raise ValidationError("Configure a GD invitation signing secret of at least 32 bytes")
        # Purpose-separated PRF permits reliable replay without storing plaintext tokens.
        raw=hmac.new(self.secret.encode(),("gd-invitation:"+key+":"+str(body.request_id)).encode(),hashlib.sha256).digest()
        token=base64.urlsafe_b64encode(raw).decode().rstrip("=")
        payload={"id":str(uuid5(NAMESPACE_URL,key+":"+body.candidate_id)),"candidate_id":body.candidate_id,
            "display_name":str(candidate.get("name") or "Participant").split()[0][:80],
            "token_hash":hashlib.sha256(token.encode()).hexdigest(),"request_id":str(body.request_id),
            "request_hash":fingerprint(body.model_dump(mode="json")),
            "expires_at":(datetime.now(timezone.utc)+timedelta(minutes=body.expires_minutes)).isoformat()}
        saved=await self.repo.invite(actor,key,payload)
        if saved["invitation_hash"]!=payload["token_hash"]:raise ValidationError("The invitation signing key changed. Issue a new invitation")
        return {"participant_id":saved["id"],"expires_at":saved["invitation_expires_at"],
            "join_url":settings.FRONTEND_URL.rstrip("/")+"/discussion-invite#session="+key+"&token="+token}

    async def accept(self,actor,key,body):
        if actor.role!="candidate" or not actor.candidate_id:raise ForbiddenError("A linked candidate account is required")
        await self.repo.accept(actor,key,hashlib.sha256(body.token.encode()).hexdigest(),str(body.request_id))
        return await self.view(actor,key)

    async def view(self,actor,key):
        row,participants,own=await self.require_session(actor,key)
        events=await self.repo.events(key) if own is None or own.get("accepted_at") else []
        signals=participation_signals(events,participants,started_at=row.get("started_at"),duration_seconds=row["configuration"]["duration_seconds"])
        config=row["configuration"]
        result={"id":key,"title":config["title"],"topic":config["topic"],"status":row["status"],"revision":row["revision"],
            "max_participants":config["max_participants"],"min_participants":config["min_participants"],
            "duration_seconds":config["duration_seconds"],"time_remaining_seconds":signals["time_remaining_seconds"] if row["status"] not in {"completed","cancelled"} else 0,
            "realtime":self.realtime.describe(key),"own_participant_id":own["id"] if own else None,
            "participants":[{"id":p["id"],"display_name":p["display_name"],"status":p["status"],"hand_raised":p["hand_raised"],
                **({"candidate_id":str(p["candidate_id"]),"report_status":p["report_status"]} if own is None else {})} for p in participants],
            "events":[{"id":e["id"],"sequence":e["sequence"],"participant_id":e["participant_id"],"kind":e["kind"],"text":e["source_text"],
                "response":e["response"],"reply_to":e["reply_to"],"created_at":e["created_at"],"analysis_status":e["analysis"].get("status"),
                "policy_context":e.get("policy_context") or None} for e in events],
            "analysis_pending":sum(e["analysis"].get("status")=="pending" for e in events),
            "participation":signals["participants"].get(own["id"]) if own else signals,
            "report_status":own["report_status"] if own else None,"report":report_view(own.get("report"),True) if own else None}
        return result

    async def control(self,actor,key,body):
        await self.require_session(actor,key,owner_only=True)
        await self.repo.control(actor,key,body)
        return await self.view(actor,key)

    async def attendance(self,actor,key,body):
        await self.require_session(actor,key)
        await self.repo.attendance(actor,key,body.action,str(body.request_id))
        return await self.view(actor,key)

    async def remove(self,actor,key,participant_id,request_id):
        await self.require_session(actor,key,owner_only=True)
        await self.repo.attendance(actor,key,"remove",str(request_id),participant_id)
        return await self.view(actor,key)

    async def message(self,actor,key,body):
        _,_,own=await self.require_session(actor,key)
        if not own or own["status"]!="joined":raise ForbiddenError("Join the discussion before contributing")
        event={"id":str(uuid4()),"request_id":str(body.request_id),"request_hash":fingerprint(body.model_dump(mode="json",exclude={"request_id"})),
            "source_text":body.text,"reply_to":str(body.reply_to) if body.reply_to else None}
        await self.repo.append(actor,key,event)
        # Raw input is already durable. Another worker may own the analysis lease.
        try:await self.processing.drain(key,max_events=1)
        except AppError:pass
        return await self.view(actor,key)

    async def generate_report(self,actor,key,participant_id):
        row,participants,own=await self.require_session(actor,key)
        participant=next((p for p in participants if p["id"]==participant_id),None)
        if not participant or own and own["id"]!=participant_id:raise NotFoundError("Participant report not found")
        await self.processing.drain(key,max_events=3)
        result=await GDReporting(self.repo,self.client).generate(row,participant,actor)
        return report_view(result,actor.role=="candidate")
