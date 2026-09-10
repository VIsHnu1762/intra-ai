from typing import Any
from app.integrations.feature_db import execute, rpc


class OnboardingRepository:
    def __init__(self, sb: Any):
        self.sb = sb

    async def profile(self, user_id: str) -> dict | None:
        rows = await execute(self.sb.table("candidate_profiles").select("*").eq("user_id", user_id).limit(1))
        return rows[0] if rows else None

    async def versions(self, user_id: str) -> list[dict]:
        return await execute(self.sb.table("candidate_resume_versions").select("*").eq("user_id", user_id).order("version", desc=True).limit(50))

    async def version(self, user_id: str, version_id: str) -> dict | None:
        rows = await execute(self.sb.table("candidate_resume_versions").select("*").eq("user_id", user_id).eq("id", version_id).limit(1))
        return rows[0] if rows else None

    async def save(self, actor: Any, data: dict, expected_revision: int) -> dict:
        return await rpc(self.sb, "save_candidate_resume", p_user_id=actor.user_id,
                         p_expected_revision=expected_revision, p_resume=data)
