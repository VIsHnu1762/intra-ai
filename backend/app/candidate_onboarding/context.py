"""Optional saved-profile context for the candidate's own practice sessions."""
import logging

from app.core.config import settings
from app.candidate_onboarding.repository import OnboardingRepository

logger = logging.getLogger(__name__)


async def practice_profile(actor, sb):
    if not settings.CANDIDATE_ONBOARDING_ENABLED or actor.role != "candidate":
        return None
    try:
        repo = OnboardingRepository(sb)
        profile = await repo.profile(actor.user_id)
        if not profile or not profile.get("current_resume_id"):
            return None
        if actor.candidate_id and str(profile["candidate_id"]) != actor.candidate_id:
            return None
        version = await repo.version(actor.user_id, profile["current_resume_id"])
        if not version or str(version["candidate_id"]) != str(profile["candidate_id"]):
            return None
        return {"profile": version["profile"], "resume_version_id": version["id"],
                "source": "candidate_onboarding", "version": version["version"]}
    except Exception as exc:
        # Optional onboarding availability must not take existing practice offline.
        logger.warning("practice_profile_unavailable error_type=%s", type(exc).__name__)
        return None
