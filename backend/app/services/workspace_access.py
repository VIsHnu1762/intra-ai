"""Persisted recruiter identity and scoped IDs for ATS list pagination."""

from typing import Any

from fastapi import Depends

from app.core.deps import get_current_user, get_supabase
from app.voice.authorization import Actor, identity, require_recruiter, _job_owned


async def current_actor(user: dict[str, Any] = Depends(get_current_user), supabase: Any = Depends(get_supabase)) -> Actor:
    return await identity(user, supabase)


async def recruiter_actor(actor: Actor = Depends(current_actor)) -> Actor:
    require_recruiter(actor)
    return actor


class WorkspaceAccess:
    def __init__(self, supabase: Any, actor: Actor):
        require_recruiter(actor)
        self._sb, self.actor = supabase, actor

    async def job_ids(self) -> list[str]:
        """Filter ownership at the database; never read all other recruiters' jobs."""
        rows = []
        offset = 0
        while True:
            query = self._sb.table("jobs").select("*").eq("created_by", self.actor.user_id)
            # Some hosted legacy schemas omit tenant_id. Ownership is always
            # filtered by SQL; optional tenant tags are checked on these rows.
            page = query.order("id").range(offset, offset + 99).execute().data or []
            rows.extend(row for row in page if _job_owned(self.actor, row))
            if len(page) < 100:
                return [str(row["id"]) for row in rows]
            offset += 100

    async def related_ids(self, table: str, column: str, job_ids: list[str]) -> list[str]:
        """Only internal callers choose table/column; never interpolated from requests."""
        if not job_ids:
            return []
        ids = []
        # Bound PostgREST URLs and retain all rows across its default row cap.
        for start in range(0, len(job_ids), 100):
            offset = 0
            while True:
                page = (
                    self._sb.table(table).select(f"id,{column}").in_("job_id", job_ids[start:start + 100])
                    .order("id").range(offset, offset + 99).execute().data or []
                )
                ids.extend(str(row[column]) for row in page if row.get(column))
                if len(page) < 100:
                    break
                offset += 100
        return list(dict.fromkeys(ids))
