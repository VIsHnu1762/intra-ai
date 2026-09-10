from uuid import UUID
from fastapi import APIRouter,Depends
from app.core.deps import get_supabase
from app.services.workspace_access import current_actor,recruiter_actor
from app.group_discussion.models import SessionCreate,InviteInput,AcceptInvite,DiscussionMessage,ParticipantAction,GDControl,RemoveParticipant
from app.group_discussion.service import GDService

router=APIRouter(prefix="/group-discussions",tags=["group-discussions"])


def service(sb=Depends(get_supabase)):return GDService(sb)


@router.get("")
async def sessions(actor=Depends(current_actor),svc=Depends(service)):
    rows=await svc.repo.sessions(actor)
    return [{"id":r["id"],"title":r["configuration"]["title"],"topic":r["configuration"]["topic"],"status":r["status"],"created_at":r["created_at"]} for r in rows]


@router.post("",status_code=201)
async def create(body:SessionCreate,actor=Depends(recruiter_actor),svc=Depends(service)):
    row=await svc.create(actor,body)
    return await svc.view(actor,row["id"])


@router.get("/{key}")
async def view(key:UUID,actor=Depends(current_actor),svc=Depends(service)):
    return await svc.view(actor,str(key))


@router.post("/{key}/invitations",status_code=201)
async def invite(key:UUID,body:InviteInput,actor=Depends(recruiter_actor),svc=Depends(service)):
    return await svc.invite(actor,str(key),body)


@router.post("/{key}/join")
async def join(key:UUID,body:AcceptInvite,actor=Depends(current_actor),svc=Depends(service)):
    return await svc.accept(actor,str(key),body)


@router.post("/{key}/control")
async def control(key:UUID,body:GDControl,actor=Depends(recruiter_actor),svc=Depends(service)):
    return await svc.control(actor,str(key),body)


@router.post("/{key}/participation")
async def attendance(key:UUID,body:ParticipantAction,actor=Depends(current_actor),svc=Depends(service)):
    return await svc.attendance(actor,str(key),body)


@router.post("/{key}/participants/{participant_id}/remove")
async def remove(key:UUID,participant_id:UUID,body:RemoveParticipant,actor=Depends(recruiter_actor),svc=Depends(service)):
    return await svc.remove(actor,str(key),str(participant_id),body.request_id)


@router.post("/{key}/messages",status_code=201)
async def message(key:UUID,body:DiscussionMessage,actor=Depends(current_actor),svc=Depends(service)):
    return await svc.message(actor,str(key),body)


@router.post("/{key}/participants/{participant_id}/report")
async def report(key:UUID,participant_id:UUID,actor=Depends(current_actor),svc=Depends(service)):
    return await svc.generate_report(actor,str(key),str(participant_id))
