from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_supabase
from app.company_knowledge.grounding import CompanyPolicyEnricher
from app.company_knowledge.models import GroundedContext
from app.integrations.feature_db import tenant_key
from app.intelligence.company.selector import CompanyKnowledgeIntelligence
from app.intelligence.core.contracts import StrictModel
from app.services.workspace_access import recruiter_actor

router = APIRouter(prefix="/company-knowledge", tags=["company-knowledge"])


class PolicyQuestion(StrictModel):
    question: str = Field(min_length=3, max_length=500)


def intelligence():
    return CompanyKnowledgeIntelligence()


@router.post("/answer", response_model=GroundedContext)
async def answer(body: PolicyQuestion, actor=Depends(recruiter_actor), sb=Depends(get_supabase), selector=Depends(intelligence)):
    # Ownership, audience and effective dates are enforced before any LLM call.
    context = await CompanyPolicyEnricher(sb).enrich(actor.user_id, tenant_key(actor), body.question)
    return await selector.select(context, body.question)
