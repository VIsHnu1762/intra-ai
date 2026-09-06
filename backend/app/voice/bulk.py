"""Reviewed, bounded HR batches. Every outcome describes a persisted operation."""
from __future__ import annotations

import asyncio
from copy import deepcopy

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.services.interview_template_service import InterviewTemplateService
from app.voice import authorization as auth

BULK_TOOLS = frozenset({"bulk_shortlist_candidates", "bulk_schedule_interviews"})
ACTIVE_INTERVIEWS = {"scheduled", "instant_pending", "instant_active", "in_progress"}


async def application_rows(service, ids: list[str], actor: auth.Actor) -> list[dict]:
    """Authorize a joined batch without loading every candidate's full CV."""
    rows = service.sb.table("applications").select("*, candidates(*), jobs(*)").in_("id", ids).execute().data or []
    indexed = {str(row["id"]): row for row in rows}
    if len(indexed) != len(ids):
        raise NotFoundError("One or more selected applications no longer exist")
    result = []
    for app_id in ids:
        row = indexed[app_id]
        job = row.get("jobs") or await service.job_repo.get_by_id(row["job_id"])
        person = row.get("candidates") or await service.candidate_repo.get_by_id(row["candidate_id"])
        if not job or not person:
            raise NotFoundError("An application is missing its job or candidate")
        if not auth._job_owned(actor, job) or str(job["id"]) != str(row["job_id"]) or str(person["id"]) != str(row["candidate_id"]):
            raise ForbiddenError("An application is outside your recruiter workspace")
        for resource in (row, person, job):
            auth._tenant_match(actor.tenant_id, resource)
        result.append({
            "application": {key: row.get(key) for key in ("id", "job_id", "candidate_id", "status")},
            "candidate": {key: person.get(key) for key in ("id", "name", "email")},
            "job": {key: job.get(key) for key in ("id", "title")},
        })
    return result


async def authorize_existing(service, inputs, actor: auth.Actor, original: dict, result: dict | None) -> None:
    current = await application_rows(service, list(inputs.application_ids), actor)
    old = {row["application"]["id"]: row for row in original["items"]}
    for row in current:
        prior = old.get(row["application"]["id"])
        if not prior or any(row["application"][key] != prior["application"][key] for key in ("id", "job_id", "candidate_id")):
            raise ForbiddenError("The selected application relationships changed")
    if hasattr(inputs, "template_id"):
        await InterviewTemplateService(service.sb).get(actor, inputs.template_id)
    for item in ((result or {}).get("result") or {}).get("items", []):
        if item.get("interview_id"):
            await auth.require_interview(actor, item["interview_id"], service.sb)


async def review(service, name: str, inputs, actor: auth.Actor) -> dict[str, Any]:
    items = await application_rows(service, list(inputs.application_ids), actor)
    active = service.sb.table("scheduled_interviews").select("application_id,status").in_(
        "application_id", list(inputs.application_ids)).in_("status", sorted(ACTIVE_INTERVIEWS)).execute().data or []
    occupied = {row["application_id"] for row in active}
    result: dict[str, Any] = {"count": len(items), "items": items}
    start = None
    duration = 0
    if name == "bulk_schedule_interviews":
        if any(row["application"]["job_id"] != inputs.job_id for row in items):
            raise ValidationError("Choose applications for the selected job only")
        snapshot = await InterviewTemplateService(service.sb).require_snapshot(actor, inputs.template_id)
        try:
            zone = ZoneInfo(inputs.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValidationError("Choose a valid IANA timezone, such as Asia/Kolkata") from None
        start = inputs.start_at
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValidationError("Include the timezone offset in the interview start time")
        if start.utcoffset() != start.astimezone(zone).utcoffset():
            raise ValidationError("The start time offset does not match the selected timezone")
        if start <= datetime.now(timezone.utc):
            raise ValidationError("Choose a future start time")
        duration = snapshot["duration_minutes"]
        result.update(template=snapshot, timezone=inputs.timezone, gap_minutes=inputs.gap_minutes,
                      shortlist_first=inputs.shortlist_first, email_sent=False, external_calendar_created=False)
    eligible_count = 0
    for item in items:
        status = item["application"]["status"]
        allowed = {"applied", "parsing", "rejected", "shortlisted"} if name == "bulk_shortlist_candidates" else {"shortlisted", "invited", "completed"}
        if name == "bulk_schedule_interviews" and inputs.shortlist_first:
            allowed |= {"applied", "parsing", "rejected"}
        reason = None
        if item["application"]["id"] in occupied:
            reason = "An active interview already exists; reschedule it instead."
        elif name == "bulk_shortlist_candidates" and status == "shortlisted":
            reason = "Already shortlisted."
        elif status not in allowed:
            reason = f"Application is {status}; this batch will not change it."
        item["eligible"] = reason is None
        if reason:
            item["skip_reason"] = reason
            continue
        if start is not None:
            slot_start = start + timedelta(minutes=eligible_count * (duration + inputs.gap_minutes))
            utc_start = slot_start.astimezone(timezone.utc)
            if utc_start.date() != (utc_start + timedelta(minutes=duration)).date():
                raise ValidationError("Choose times that keep each interview within one UTC day for the saved slot format")
            item.update(scheduled_at=slot_start.astimezone(timezone.utc).isoformat(), duration_minutes=duration)
        eligible_count += 1
    result.update(eligible_count=eligible_count, skipped_count=len(items) - eligible_count)
    return result


async def execute(service, name: str, inputs, actor: auth.Actor, *, review: dict) -> dict:
    # Keep every approved candidate/time/template fixed. Authorization may be
    # refreshed, but it must never rebuild or shift the reviewed batch payload.
    proposal = deepcopy(review)
    await authorize_existing(service, inputs, actor, proposal, None)
    outcomes = []
    for item in proposal["items"]:
        # Let session polling and worker-lease renewal progress between items.
        await asyncio.sleep(0)
        app = item["application"]
        outcome = {"application_id": app["id"], "candidate_id": app["candidate_id"], "job_id": app["job_id"],
                   "candidate": item["candidate"], "job": item["job"]}
        if not item["eligible"]:
            outcomes.append({**outcome, "status": "skipped", "message": item["skip_reason"]})
            continue
        slot_id = None
        try:
            # Business state may change during an earlier item in the batch.
            current = await auth.require_application(actor, app["id"], service.sb)
            if any(current.get(key) != app.get(key) for key in ("id", "job_id", "candidate_id")):
                raise ForbiddenError("Application relationships changed after review")
            if current.get("status") != app["status"]:
                raise ConflictError("Application changed after review")
            active = service.sb.table("scheduled_interviews").select("id").eq("application_id", app["id"]).in_(
                "status", sorted(ACTIVE_INTERVIEWS)).limit(1).execute().data or []
            if active:
                raise ConflictError("An active interview already exists; reschedule it instead")
            if name == "bulk_shortlist_candidates":
                await service.applications.shortlist(app["id"])
                outcomes.append({**outcome, "status": "succeeded", "new_status": "shortlisted", "message": "Shortlisted."})
                continue
            if current["status"] not in {"shortlisted", "invited", "completed"}:
                await service.applications.shortlist(app["id"])
            start = datetime.fromisoformat(item["scheduled_at"])
            end = start + timedelta(minutes=item["duration_minutes"])
            if start.date() != end.date():
                raise ValidationError("An interview cannot cross UTC midnight in the saved slot format")
            slots = await service.scheduling.create_slots(inputs.job_id, [{"date": start.date().isoformat(),
                "start_time": start.strftime("%H:%M:%S"), "end_time": end.strftime("%H:%M:%S")}])
            slot_id = slots[0].id
            booked = await service.scheduling.book_slot(app["id"], slot_id, template_snapshot=proposal["template"])
            outcomes.append({**outcome, "status": "succeeded", "new_status": "scheduled", "interview_id": booked.id,
                             "scheduled_at": item["scheduled_at"], "message": "Interview scheduled in Intra AI. No email or external calendar event was sent."})
        except Exception:
            # Do not rollback a completed external/durable action on an unknown
            # timeout. Keep the item explicit for the recruiter to inspect.
            outcomes.append({**outcome, "status": "failed", "slot_id": slot_id,
                             "message": "This item could not be fully verified. Check the application and interview before retrying."})
    return {"items": outcomes, **{key: sum(row["status"] == label for row in outcomes)
            for key, label in (("succeeded", "succeeded"), ("failed", "failed"), ("skipped", "skipped"))},
            "email_sent": False, "external_calendar_created": False}
