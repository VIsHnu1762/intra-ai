"""One persisted post-interview report workflow, outside the live voice path."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import math
import re
import time
from typing import Any, Awaitable
import uuid

import structlog

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.integrations import aicredits_client
from app.repositories.interview_repo import InterviewRepo
from app.repositories.job_repo import JobRepo
from app.schemas.reports import CandidatePerformanceResponse, ReportListResponse, ReportResponse, ReportStatusResponse

logger = structlog.stdlib.get_logger("intra_ai.service.report")
_workers: set[asyncio.Task] = set()
_MESSAGES = {
    "REPORT_EVIDENCE_UNAVAILABLE": "There is not enough evaluated interview evidence to produce an overall report.",
    "REPORT_SOURCE_INVALID": "The saved interview evidence could not be verified. No overall assessment was published.",
    "REPORT_GENERATION_INTERRUPTED": "Report generation was interrupted. Retry to resume from the saved interview data.",
    "REPORT_OUTPUT_INVALID": "The generated report did not pass validation. Retry generation.",
    "REPORT_GENERATION_FAILED": "Report generation failed. Your completed interview data is preserved; you can retry.",
}


def rating_from_score(score: float) -> float:
    """Map the existing 0–100 overall assessment to 1–5, without rescoring."""
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValidationError("Overall score must be between 0 and 100")
    # PostgreSQL numeric round uses half-up, unlike Python's binary/banker's
    # round. Publication and read readiness must use exactly the same mapping.
    return float((Decimal(1) + Decimal(str(score)) / 25).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def performance_band(score: float) -> str:
    return "strong" if score >= 80 else "good" if score >= 65 else "developing" if score >= 50 else "needs improvement"


def _ready(row: dict[str, Any] | None) -> bool:
    if not row or not isinstance(row.get("candidate_feedback"), list):
        return False
    rating = row.get("candidate_rating")
    try:
        expected = rating_from_score(row.get("overall_score"))
    except ValidationError:
        return False
    return (len(row["candidate_feedback"]) == 3 and all(isinstance(x, str) and x.strip() for x in row["candidate_feedback"])
            and isinstance(rating, (int, float)) and not isinstance(rating, bool) and math.isfinite(rating)
            and 1 <= rating <= 5 and abs(rating - expected) <= 0.0001
            and isinstance(row.get("analysis"), dict) and bool(row["analysis"]))


def _snapshot_fields(record: Any, fields: set[str]) -> dict:
    """Keep known scalar/list fields, never arbitrary nested model metadata."""
    if not isinstance(record, dict):
        return {}
    def scalar(value):
        return value is None or isinstance(value, (str, bool)) or isinstance(value, (int, float)) and math.isfinite(value)
    result = {}
    for key in fields & record.keys():
        value = record[key]
        if scalar(value):
            result[key] = value
        elif isinstance(value, list):
            result[key] = [item for item in value if scalar(item)]
    return result


_ASSESSMENT_FIELDS = {"status", "reason", "objective_id", "answer_id", "performance", "confidence", "missing_information", "evidence_ids"}


def _capture_source(interview_id: str) -> dict[str, Any] | None:
    """Snapshot existing stores at completion; never change live voice state."""
    from app.interview_context.store import interview_session_store
    from app.transcript.store import transcript_store
    from app.sessions.store import session_store
    context = interview_session_store.get(interview_id)
    meeting = session_store.get(interview_id)
    if context is None and meeting:
        context = interview_session_store.get(meeting.channel_name)
    saved = deepcopy(context.to_dict()) if context else None
    if saved:
        # Live voice deliberately keys context by the Agora channel. Translate
        # only the alias proven by this actual meeting; never relabel arbitrary
        # foreign context, and never mutate the live context's identity.
        if (meeting and meeting.interview_id == interview_id
                and saved.get("interview_id") == meeting.channel_name
                and saved.get("candidate_id") == meeting.candidate_id):
            saved["source_interview_id"] = saved["interview_id"]
            saved["interview_id"] = interview_id
        metadata = saved.get("metadata", {})
        safe = _snapshot_fields(metadata, {"completed", "completion_reason"})
        history_fields = {"from_agent_id", "to_agent_id", "source_agent_id", "target_agent_id", "agent_id", "round_id", "round_type", "name", "status", "timestamp"}
        round_fields = {"id", "round_id", "name", "type", "round_type", "agent_id", "agent_ids", "focus_areas", "duration_minutes", "order_index", "is_active", "enabled"}
        for key in ("handoff_history", "handoffs", "agent_history", "round_history", "observed_rounds", "round_configs"):
            if isinstance(metadata.get(key), list):
                safe[key] = [_snapshot_fields(row, round_fields if key == "round_configs" else history_fields) for row in metadata[key] if isinstance(row, dict)]
        if isinstance(metadata.get("assessed_insufficient"), dict):
            safe["assessed_insufficient"] = {key: _snapshot_fields(row, _ASSESSMENT_FIELDS) for key, row in metadata["assessed_insufficient"].items() if isinstance(key, str)}
        saved["metadata"] = safe
        for item in saved.get("accumulated_evidence", []):
            item["metadata"] = _snapshot_fields(item.get("metadata"), {"answer_id", "provider_answer_id", "subject"})
        for item in saved.get("question_history", []):
            original = item.get("metadata") or {}
            item["metadata"] = _snapshot_fields(original, {"round_id", "answered_by", "objective_id"})
            if isinstance(original.get("assessment_outcome"), dict):
                item["metadata"]["assessment_outcome"] = _snapshot_fields(original["assessment_outcome"], _ASSESSMENT_FIELDS)
        for item in saved.get("detected_contradictions", []):
            item["metadata"] = _snapshot_fields(item.get("metadata"), {"answer_id"})
    events = transcript_store.get_transcript(interview_id)
    if not events and meeting:
        events = transcript_store.get_transcript(meeting.channel_name)
    transcripts = [{"id": e.id, "speaker": e.speaker.value, "agent_id": e.agent_id,
                    "text": e.text, "timestamp": e.timestamp, "sequence": e.sequence} for e in events]
    if not saved and not transcripts:
        return None
    return {"version": 1, "context": saved, "transcripts": transcripts}


def _narrative_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    """Supply each answer/evidence once; retain the complete stored assessment.

    Answer rows already contain their questions, and evaluated evidence is the
    report's authority. Repeating the raw transcript and question history adds
    substantial input without adding scored facts. No answer, evidence item,
    observed agent/round, coverage gap, or computed score is sampled away.
    """
    omitted = {"candidate_id", "interview_id", "provenance"}
    coverage = assessment.get("coverage") or {}
    answers = assessment.get("answers")
    if isinstance(answers, list) and answers and coverage.get("missing_answer_ids") == []:
        omitted.update({"transcripts", "question_history"})
    return deepcopy({key: value for key, value in assessment.items() if key not in omitted})


class ReportService:
    def __init__(self, interview_repo: InterviewRepo, job_repo: JobRepo) -> None:
        self._interview_repo, self._job_repo = interview_repo, job_repo

    async def resolve_interview_id(self, key: str) -> str:
        report = await self._interview_repo.get_report_by_id(key)
        return str(report["interview_id"]) if report else key

    async def status(self, interview_id: str) -> ReportStatusResponse:
        interview = await self._interview_repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError("Interview not found")
        if interview.get("status") != "completed":
            return ReportStatusResponse(interview_id=interview_id, status="not_completed")
        report = await self._interview_repo.get_report(interview_id)
        if _ready(report):
            return ReportStatusResponse(interview_id=interview_id, status="ready", report_id=report["id"])
        state = interview.get("report_generation") or {}
        if not isinstance(state, dict):
            state = {"status": "failed", "error_code": "REPORT_GENERATION_INTERRUPTED"}
        status = state.get("status", "not_started")
        code = state.get("error_code")
        if not isinstance(code, str):
            code = None
        if status == "generating":
            try:
                if not isinstance(state.get("attempt_id"), str) or not state["attempt_id"].strip():
                    raise ValueError("Missing report attempt")
                started = datetime.fromisoformat(state["started_at"].replace("Z", "+00:00"))
                if started < datetime.now(timezone.utc) - timedelta(minutes=5):
                    status, code = "failed", "REPORT_GENERATION_INTERRUPTED"
            except (KeyError, TypeError, ValueError):
                status, code = "failed", "REPORT_GENERATION_INTERRUPTED"
        if status not in {"not_started", "generating", "failed"}:
            status, code = "failed", "REPORT_GENERATION_FAILED"
        message = _MESSAGES.get(code) if code else None
        if code and code.startswith("AICREDITS_"):
            message = state.get("message") or "The post-interview AI provider is unavailable. Check server configuration and retry."
            if code == "AICREDITS_TIMEOUT":
                message = "Report preparation timed out. Your interview answers are saved; retry to prepare the report."
        return ReportStatusResponse(interview_id=interview_id, status=status, error_code=code,
                                    message=message, retryable=status in {"not_started", "failed"})

    async def request_report(self, interview_id: str) -> ReportStatusResponse:
        """Persist the claim/source, then return while the post-interview worker runs."""
        source = _capture_source(interview_id)
        attempt = str(uuid.uuid4())
        state = await asyncio.to_thread(lambda: asyncio.run(self._claim(interview_id, attempt, source)))
        if state.get("attempt_id") == attempt:
            task = asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(self._generate_claimed(interview_id, attempt))))
            _workers.add(task)
            task.add_done_callback(_workers.discard)
        return await self.status(interview_id)

    async def _claim(self, interview_id: str, attempt: str, source: dict | None) -> dict:
        interview = await self._interview_repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError("Interview not found")
        if interview.get("status") != "completed":
            raise ConflictError("Complete the interview before generating its report")
        return await self._interview_repo.claim_report(interview_id, attempt, source)

    async def generate_report(self, interview_id: str) -> ReportResponse:
        """Await the same worker for administrative callers; not a second workflow."""
        attempt = str(uuid.uuid4())
        state = await self._claim(interview_id, attempt, _capture_source(interview_id))
        if state.get("status") == "ready":
            return await self.get_report(interview_id)
        if state.get("attempt_id") != attempt:
            raise ConflictError("Report generation is already in progress")
        await self._generate_claimed(interview_id, attempt)
        result = await self.status(interview_id)
        if result.status != "ready":
            raise ValidationError(result.message or "Report generation failed", details={"code": result.error_code})
        return await self.get_report(interview_id)

    async def _generate_claimed(self, interview_id: str, attempt: str) -> None:
        try:
            await self._build_report(interview_id, attempt)
        except Exception as exc:
            if isinstance(exc, aicredits_client.AICreditsError):
                code, message = "AICREDITS_" + exc.code.upper(), str(exc)
            else:
                code = getattr(exc, "code", "REPORT_GENERATION_FAILED")
                if code not in _MESSAGES:
                    code = "REPORT_GENERATION_FAILED"
                message = _MESSAGES[code]
            try:
                await self._interview_repo.save_report_progress(interview_id, attempt, {"report_generation": {
                    "status": "failed", "attempt_id": attempt, "error_code": code, "message": message,
                    "stage": getattr(exc, "report_stage", "assessment"),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }})
            except Exception:
                logger.error("report_failure_state_unavailable", interview_id=interview_id, attempt_id=attempt)
            logger.warning("report_generation_failed", interview_id=interview_id, attempt_id=attempt,
                           code=code, stage=getattr(exc, "report_stage", "assessment"))

    async def _build_report(self, interview_id: str, attempt: str) -> None:
        from app.services.report_evaluation import build_evaluation, ReportEvidenceUnavailable, ReportSourceInvalid
        interview = await self._interview_repo.get_by_id(interview_id)
        if not interview:
            raise NotFoundError("Interview not found")
        source = deepcopy(interview.get("report_source") or {})
        if not isinstance(source, dict):
            raise ReportSourceInvalid()
        assessment = source.get("evaluation")
        if assessment is not None:
            if (not isinstance(assessment, dict) or assessment.get("interview_id") != interview_id
                    or assessment.get("candidate_id") != interview.get("candidate_id")):
                raise ReportSourceInvalid("The saved assessment belongs to a different interview or candidate")
        if not assessment or not self._overall_coverage(assessment):
            evaluations = await self._interview_repo.get_evaluations(interview_id)
            answers = await self._interview_repo.get_answers(interview_id)
            context = source.get("context")
            recovered = None
            if not (context or {}).get("accumulated_evidence") and not evaluations:
                recovered = self._recover_graph(interview)
                context = recovered.get("context")
                answers = recovered.get("answers") or answers
                evaluations = recovered.get("evaluations") or evaluations
            assessment = build_evaluation(interview, context, evaluations, answers)
            if context and not self._overall_coverage(assessment):
                # Context evidence may omit answer IDs. Read the already-written
                # same-interview graph to link those exact IDs, without rescoring
                # or replacing the authoritative context with a partial graph.
                recovered = self._recover_graph(interview)
                links = {e["id"]: e.get("metadata", {}).get("answer_id")
                         for e in recovered.get("context", {}).get("accumulated_evidence", [])}
                context = deepcopy(context)
                for evidence in context.get("accumulated_evidence", []):
                    if links.get(evidence.get("id")):
                        existing_answer = evidence.get("answer_id") or evidence.get("metadata", {}).get("answer_id")
                        if existing_answer and existing_answer != links[evidence["id"]]:
                            raise ReportSourceInvalid("The saved evidence and graph answer identities conflict")
                        evidence["metadata"] = {**evidence.get("metadata", {}), "answer_id": links[evidence["id"]]}
                answers = self._merge_graph_answers(answers, recovered.get("answers") or [])
                context["metadata"] = {**context.get("metadata", {}), "graph_interview_ids": recovered.get("context", {}).get("metadata", {}).get("graph_interview_ids", [])}
                assessment = build_evaluation(interview, context, evaluations, answers)
            if context and assessment.get("coverage", {}).get("missing_answer_ids"):
                # Transcripts are optional enrichment when scored identities
                # already establish coverage. KG absence must not rescore the
                # interview or invent text; conflicting sources fail closed.
                try:
                    if recovered is None:
                        recovered = self._recover_graph(interview)
                except ReportSourceInvalid:
                    raise
                except Exception as exc:
                    logger.info("report_transcript_recovery_unavailable", interview_id=interview_id, error_type=type(exc).__name__)
                if recovered:
                    known_ids = set(assessment["coverage"].get("scored_answer_ids", []))
                    graph_answers = [row for row in recovered.get("answers", []) if row.get("id") in known_ids]
                    answers = self._merge_graph_answers(answers, graph_answers)
                    context["metadata"] = {**context.get("metadata", {}), "graph_interview_ids": recovered.get("context", {}).get("metadata", {}).get("graph_interview_ids", [])}
                    assessment = build_evaluation(interview, context, evaluations, answers)
            assessment["transcripts"] = source.get("transcripts", [])
            source["evaluation"] = assessment
            await self._save_progress(interview_id, attempt, {"report_source": source})
        if not self._overall_coverage(assessment):
            raise ReportEvidenceUnavailable("At least two evaluated answers are needed for an overall performance assessment")
        score = float(assessment["overall_score"])
        assessment = {**assessment, "star_rating": rating_from_score(score), "performance_band": performance_band(score)}
        draft = interview.get("report_draft")
        if not draft:
            draft = self._validate_narrative(await self._provider_step(interview_id, attempt, "narrative",
                aicredits_client.generate_report_narrative(_narrative_assessment(assessment))), assessment)
            await self._save_progress(interview_id, attempt, {"report_draft": draft})
        else:
            draft = self._validate_narrative(draft, assessment)
        feedback = self._validate_feedback(await self._provider_step(interview_id, attempt, "candidate_feedback",
            aicredits_client.generate_candidate_feedback(assessment, draft)), score, assessment, draft)
        existing = await self._interview_repo.get_report(interview_id)
        recommendation = "strong_hire" if score >= 80 else "hire" if score >= 65 else "maybe" if score >= 50 else "no_hire"
        report = {
            "id": existing["id"] if existing else str(uuid.uuid4()), "interview_id": interview_id,
            "overall_score": score, "recommendation": recommendation,
            "round_assessments": assessment["round_assessments"],
            "strengths": [row["text"] for row in draft["strengths"]],
            "improvements": [row["text"] for row in draft["improvements"]],
            "salary_recommendation": (existing or {}).get("salary_recommendation"),
            "proctoring_summary": (existing or {}).get("proctoring_summary"),
            "pdf_url": (existing or {}).get("pdf_url"),
            "created_at": (existing or {}).get("created_at") or datetime.now(timezone.utc).isoformat(),
            "candidate_rating": rating_from_score(score), "candidate_feedback": feedback,
            "analysis": {**assessment, "overall_summary": draft["overall_summary"],
                         "narrative_evidence": {key: draft[key] for key in ("strengths", "improvements")},
                         "rating_mapping": "round(1 + overall_score / 25, 1)"},
        }
        # Database locking and attempt ownership fence publication from stale workers.
        await self._interview_repo.finish_report(interview_id, attempt, report)
        logger.info("report_generated", interview_id=interview_id, report_id=report["id"])

    @staticmethod
    def _overall_coverage(assessment: dict) -> bool:
        coverage = assessment.get("coverage", {})
        if not isinstance(coverage, dict) or coverage.get("answer_identity_complete") is not True:
            return False
        # Cached counters are descriptive. Actual distinct scored answer links
        # establish coverage, so a partial snapshot cannot bypass the gate.
        evidence = assessment.get("evidence")
        if not isinstance(evidence, list):
            return False
        answer_ids = set()
        for item in evidence:
            if not isinstance(item, dict):
                return False
            score = item.get("score")
            if score is None:
                continue
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 10:
                return False
            aid = item.get("answer_id")
            if not isinstance(aid, str) or not aid.strip():
                return False
            answer_ids.add(aid)
        return len(answer_ids) >= 2 and coverage.get("scored_answer_count") == len(answer_ids)

    async def _provider_step(self, interview_id: str, attempt: str, stage: str, request: Awaitable[dict]) -> dict:
        started = time.perf_counter()
        logger.info("report_provider_stage_started", interview_id=interview_id, attempt_id=attempt, stage=stage)
        try:
            result = await request
        except Exception as exc:
            exc.report_stage = stage
            logger.warning("report_provider_stage_failed", interview_id=interview_id, attempt_id=attempt,
                           stage=stage, duration_ms=round((time.perf_counter() - started) * 1000),
                           error_code=getattr(exc, "code", "REPORT_GENERATION_FAILED"))
            raise
        logger.info("report_provider_stage_completed", interview_id=interview_id, attempt_id=attempt,
                    stage=stage, duration_ms=round((time.perf_counter() - started) * 1000))
        return result

    async def _save_progress(self, interview_id: str, attempt: str, data: dict) -> None:
        # Each provider step can take up to 180s. Renew the 5-minute lease at
        # durable phase boundaries, without changing the attempt ownership fence.
        await self._interview_repo.save_report_progress(interview_id, attempt, {**data, "report_generation": {
            "status": "generating", "attempt_id": attempt, "started_at": datetime.now(timezone.utc).isoformat(),
        }})

    @staticmethod
    def _merge_graph_answers(answers: list[dict], recovered: list[dict]) -> list[dict]:
        from app.services.report_evaluation import ReportSourceInvalid
        existing = {row.get("id") or row.get("answer_id"): row for row in answers}
        for row in recovered:
            previous = existing.get(row.get("id") or row.get("answer_id"))
            if previous:
                for key, alias in (("transcript", "answer_text"), ("question_id", "question_id")):
                    before = previous.get(key) or previous.get(alias)
                    after = row.get(key) or row.get(alias)
                    if before and after and before != after:
                        raise ReportSourceInvalid("The saved answer and graph source conflict")
        return answers + recovered

    @staticmethod
    def _recover_graph(interview: dict) -> dict:
        from app.knowledge_graph.neo4j_repository import Neo4jKnowledgeGraphRepository
        from app.services.report_evaluation import recover_source_from_graph
        repository = Neo4jKnowledgeGraphRepository.from_settings()
        try:
            return recover_source_from_graph(interview, repository)
        finally:
            repository.close()

    @staticmethod
    def _validate_narrative(value: dict, assessment: dict) -> dict:
        def invalid():
            error = ValidationError("Report narrative did not pass evidence validation")
            error.code = "REPORT_OUTPUT_INVALID"
            raise error
        if not isinstance(value, dict) or not isinstance(value.get("overall_summary"), str) or not 20 <= len(value["overall_summary"].strip()) <= 2400:
            invalid()
        ids = {str(e.get("id") or e.get("evidence_id")) for e in assessment.get("evidence", [])}
        for field in ("strengths", "improvements"):
            items = value.get(field)
            if not isinstance(items, list) or len(items) > 8:
                invalid()
            for item in items:
                if (not isinstance(item, dict) or not isinstance(item.get("text"), str)
                        or not 5 <= len(item["text"].strip()) <= 600 or not isinstance(item.get("evidence_ids"), list)
                        or not item["evidence_ids"] or not all(isinstance(e, str) and e in ids for e in item["evidence_ids"])):
                    invalid()
        if not value["strengths"] and not value["improvements"]:
            invalid()
        return {key: value[key] for key in ("overall_summary", "strengths", "improvements")}

    @staticmethod
    def _validate_feedback(value: dict, score: float, assessment: dict | None = None, narrative: dict | None = None) -> list[str]:
        internal_ids = set()
        for collection, key in (("evidence", "id"), ("answers", "answer_id"), ("question_history", "id")):
            for item in (assessment or {}).get(collection, []):
                identifier = item.get(key) if isinstance(item, dict) else None
                if isinstance(identifier, str) and len(identifier) >= 6:
                    internal_ids.add(identifier.casefold())
        lines = []
        for key in ("strength", "improvement"):
            text = value.get(key) if isinstance(value, dict) else None
            if (not isinstance(text, str) or not 10 <= len(text.strip()) <= 400 or "\n" in text or "\r" in text
                    or re.search(r"\b(strong[_ -]hire|no[_ -]hire|hire|hired|reject(?:ed|ion)?|salary|chain.of.thought)\b", text, re.I)
                    or any(identifier in text.casefold() for identifier in internal_ids)):
                error = ValidationError("Candidate feedback did not pass validation")
                error.code = "REPORT_OUTPUT_INVALID"
                raise error
            lines.append(text.strip())
        if narrative is not None:
            # A request for a supportive sentence must not manufacture a
            # positive finding when the evidence-backed narrative has none.
            if not narrative.get("strengths"):
                lines[0] = "This interview did not provide enough evidence to identify a clear overall strength."
            if not narrative.get("improvements"):
                lines[1] = "Continue supporting your explanations with specific examples and measurable outcomes."
        label = performance_band(score)
        first = ("Your overall performance in this interview needs improvement." if label == "needs improvement"
                 else f"Your overall performance in this interview was {label}.")
        return [first, *lines]

    async def get_report(self, interview_id: str) -> ReportResponse:
        stored = await self._interview_repo.get_report(interview_id)
        if not stored:
            raise NotFoundError("The report is not available yet")
        return await self._response(stored)

    async def get_report_by_key(self, key: str) -> ReportResponse:
        stored = await self._interview_repo.get_report_by_id(key) or await self._interview_repo.get_report(key)
        if not stored:
            raise NotFoundError("The report is not available yet")
        return await self._response(stored)

    async def ensure_access(self, key: str, user: dict[str, Any]) -> None:
        from app.voice.authorization import identity, require_report, require_recruiter
        actor = await identity(user, self._interview_repo._sb)
        require_recruiter(actor)
        await require_report(actor, key, self._interview_repo._sb)

    async def candidate_performance(self, interview_id: str) -> CandidatePerformanceResponse:
        state = await self.status(interview_id)
        if state.status != "ready":
            message = {"not_completed": "Your interview is not complete yet.", "not_started": "Your interview is complete. Feedback has not been prepared yet.",
                       "generating": "Your overall interview feedback is being prepared.",
                       "failed": "Your interview is complete, but feedback is currently unavailable. The hiring team can retry its preparation."}[state.status]
            return CandidatePerformanceResponse(interview_id=interview_id, status=state.status, message=message)
        report = await self._interview_repo.get_report(interview_id)
        return CandidatePerformanceResponse(interview_id=interview_id, status="ready", rating=report["candidate_rating"],
                                            feedback=report["candidate_feedback"], created_at=report["created_at"])

    async def list_reports(self, filters: dict | None = None, page: int = 1, per_page: int = 20) -> ReportListResponse:
        rows, total = await self._interview_repo.list_reports(filters=filters, page=page, per_page=per_page)
        return ReportListResponse(reports=[await self._response(row) for row in rows], total=total)

    async def _response(self, row: dict) -> ReportResponse:
        interview = await self._interview_repo.get_by_id(row["interview_id"])
        candidate = (interview or {}).get("candidates") or {}
        job = (interview or {}).get("jobs") or {}
        return self._to_response({**row, "candidate": {key: candidate[key] for key in ("id", "name") if key in candidate},
                                 "job": {key: job[key] for key in ("id", "title") if key in job}})

    @staticmethod
    def _to_response(stored: dict[str, Any]) -> ReportResponse:
        return ReportResponse.model_validate(stored)
