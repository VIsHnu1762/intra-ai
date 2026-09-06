"""Deterministic post-interview evidence aggregation; no model or voice calls.

Only same-interview data contributes to the assessment. Recorded round/agent
identity is retained, and configured coverage is not treated as observed work.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
import math
from typing import Any

from app.core.exceptions import ValidationError
from app.models.enums import InterviewRoundType
from app.services.round_agents import decode_round_agents

MAX_SOURCE_RECORDS = 5000


class ReportEvidenceUnavailable(ValidationError):
    code = "REPORT_EVIDENCE_UNAVAILABLE"
    message = "No scored interview evidence is available for this report"


class ReportSourceInvalid(ValidationError):
    code = "REPORT_SOURCE_INVALID"
    message = "The interview report source could not be verified"


def _dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    if len(value) > MAX_SOURCE_RECORDS:
        raise ReportSourceInvalid("Interview evidence exceeds the complete-source limit")
    return [_dict(item) for item in value if _dict(item)]


def _strings(value: Any) -> list[str]:
    return list(dict.fromkeys(_text(item) for item in value if _text(item))) if isinstance(value, list) else []


def _score(value: Any) -> float | None:
    # A genuine zero is valid; missing, bool, NaN and infinity are not scores.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and 0 <= value <= 10 else None


def _timestamp(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _text(value) or None


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _check_scope(row: dict[str, Any], interview: dict[str, Any]) -> None:
    for field in ("interview_id", "candidate_id"):
        expected = interview.get("id") if field == "interview_id" else interview.get(field)
        if row.get(field) is not None and str(row[field]) != str(expected):
            raise ReportSourceInvalid("Report evidence belongs to a different interview or candidate")


def _configured_rounds(interview: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = _dict(interview.get("template_snapshot"))
    metadata = _dict(context.get("metadata"))
    job = _dict(interview.get("jobs") or interview.get("job"))
    source = (snapshot.get("rounds") if snapshot else None) or metadata.get("round_configs") or job.get("interview_rounds") or job.get("job_rounds") or []
    result = []
    seen = set()
    for index, row in enumerate(_rows(source)):
        if not row.get("is_active", row.get("enabled", True)):
            continue
        rid = _text(row.get("id") or row.get("round_id")) or f"configured-round-{index + 1}"
        if rid in seen:
            raise ReportSourceInvalid("Configured interview round identities are duplicated")
        seen.add(rid)
        agent_config = {"type": _text(row.get("type") or row.get("round_type")),
                        "agent_id": _text(row.get("agent_id")),
                        "agent_ids": _strings(row.get("agent_ids")),
                        "focus_areas": _strings(row.get("focus_areas"))}
        agents, focus = decode_round_agents(agent_config)
        result.append({"round_id": rid, "round_type": _text(row.get("type") or row.get("round_type")) or "unknown",
                       "round_name": _text(row.get("name")) or _text(row.get("type")) or "Interview round",
                       "configured_agent_ids": agents, "focus_areas": focus,
                       "duration_minutes": _number(row.get("duration_minutes")), "order_index": _number(row.get("order_index", index))})
    return result


def _round_descriptor(rid: str, configured: list[dict[str, Any]], observed: list[dict[str, Any]]) -> dict[str, Any]:
    exact = next((row for row in configured if row["round_id"] == rid), None)
    observed_row = next((row for row in observed if _text(row.get("round_id")) == rid), {})
    round_type = _text(observed_row.get("round_type")) or (exact or {}).get("round_type")
    if not round_type and rid in {item.value for item in InterviewRoundType}:
        round_type = rid
    candidates = [row for row in configured if row["round_type"] == (round_type or rid)]
    matched = exact or (candidates[0] if len(candidates) == 1 else None)
    return {"round_id": rid, "round_type": round_type or "unknown",
            "round_name": (matched or {}).get("round_name") or _text(observed_row.get("name")) or rid,
            "configured_round_id": matched["round_id"] if matched else None,
            "identity_resolution": "exact" if exact else "unique_round_type" if matched else "unresolved",
            "configured_agent_ids": (matched or {}).get("configured_agent_ids", [])}


def _answers(interview: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        _check_scope(row, interview)
        question = _dict(row.get("interview_questions"))
        _check_scope(question, interview)
        aid = _text(row.get("id") or row.get("answer_id"))
        transcript = _text(row.get("transcript") or row.get("answer_text"))
        if not aid or not transcript:
            continue
        result[aid] = {"answer_id": aid, "question_id": _text(row.get("question_id") or question.get("id")) or None,
                       "question_text": _text(row.get("question_text") or question.get("text") or question.get("question_text")),
                       "answer_text": transcript, "round_id": _text(row.get("round_id") or question.get("round_id") or question.get("round_type")) or None,
                       "agent_id": _text(row.get("agent_id") or question.get("agent_id") or _dict(row.get("metadata")).get("agent_id")) or None,
                       "created_at": _timestamp(row.get("created_at")), "duration_seconds": _number(row.get("duration_seconds"))}
    return list(result.values())


def build_evaluation(interview: dict[str, Any], context_dict: dict[str, Any] | None,
                     evaluations: list[dict[str, Any]], answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the existing overall metric plus transparent, same-session sources.

    Context: mean of all unique scored M1 evidence, multiplied by ten.
    Legacy: mean of per-round-TYPE evaluation means, multiplied by ten.
    Configured but unobserved rounds are retained only as coverage, never scored.
    """
    if not interview.get("id") or not interview.get("candidate_id"):
        raise ReportSourceInvalid("A persisted interview and candidate are required")
    context = deepcopy(_dict(context_dict))
    _check_scope(context, interview)
    metadata = _dict(context.get("metadata"))
    configured = _configured_rounds(interview, context)
    observed = _rows(metadata.get("observed_rounds"))
    evaluation_rows = _rows(evaluations)
    answer_rows = _rows(answers)
    for row in evaluation_rows:
        _check_scope(row, interview)
        linked = _dict(row.get("candidate_answers"))
        if linked:
            answer_rows.append(linked)
    actual_answers = _answers(interview, answer_rows)
    answer_lookup = {row["answer_id"]: row for row in actual_answers}
    question_rows = _rows(context.get("question_history"))
    question_answer_ids = set()
    evidence_answer_links = {}
    for question in question_rows:
        _check_scope(question, interview)
        qmeta = _dict(question.get("metadata"))
        aid = _text(qmeta.get("answered_by"))
        if not aid:
            continue
        question_answer_ids.add(aid)
        for eid in _strings(_dict(qmeta.get("assessment_outcome")).get("evidence_ids")):
            if eid in evidence_answer_links and evidence_answer_links[eid] != aid:
                raise ReportSourceInvalid("Recorded assessment answer links conflict")
            evidence_answer_links[eid] = aid

    evidence_by_id = {}
    invalid_evidence_count = 0
    for row in _rows(context.get("accumulated_evidence")):
        _check_scope(row, interview)
        eid = _text(row.get("id") or row.get("evidence_id"))
        signal = _text(row.get("signal"))
        if not eid or not signal:
            invalid_evidence_count += 1
            continue
        ev_metadata = _dict(row.get("metadata"))
        aid = _text(row.get("answer_id") or ev_metadata.get("answer_id"))
        recorded_aid = evidence_answer_links.get(eid)
        if aid and recorded_aid and aid != recorded_aid:
            raise ReportSourceInvalid("Recorded assessment answer links conflict")
        aid = aid or recorded_aid or ""
        linked = answer_lookup.get(aid, {})
        # Missing history cannot be assigned to the final active round/agent.
        evidence_by_id[eid] = {"id": eid, "signal": signal, "score": _score(row.get("score")),
            "competency": _text(row.get("competency")) or "general", "answer_id": aid or None,
            "round_id": _text(row.get("round_id") or linked.get("round_id")) or "unknown",
            "source_agent_id": _text(row.get("source_agent_id") or linked.get("agent_id")) or None,
            "timestamp": _timestamp(row.get("timestamp")), "source": "m1"}
    evidence = list(evidence_by_id.values())
    scored = [row for row in evidence if row["score"] is not None]
    score_method = "m1_evidence_mean"
    legacy_type_scores: dict[str, list[float]] = defaultdict(list)
    if not scored:
        legacy_by_id = {}
        for row in evaluation_rows:
            score = _score(row.get("overall"))
            eid = _text(row.get("id"))
            if score is None or not eid:
                continue
            answer = _dict(row.get("candidate_answers"))
            question = _dict(answer.get("interview_questions"))
            aid = _text(row.get("answer_id") or answer.get("id"))
            linked = answer_lookup.get(aid, {})
            rt = _text(question.get("round_type")) or "technical"
            legacy_by_id[eid] = {"id": eid, "signal": _text(row.get("feedback")), "score": score,
                "competency": _text(question.get("topic") or question.get("competency")) or "general",
                "answer_id": aid or None, "round_id": _text(question.get("round_id") or linked.get("round_id")) or rt,
                "round_type": rt, "source_agent_id": _text(question.get("agent_id") or linked.get("agent_id")) or None,
                "timestamp": _timestamp(row.get("created_at")), "source": "legacy_evaluation"}
        scored = list(legacy_by_id.values())
        if not scored:
            raise ReportEvidenceUnavailable()
        evidence = scored
        score_method = "legacy_round_type_mean"
        for row in scored:
            legacy_type_scores[row["round_type"]].append(row["score"])
            observed.append({"round_id": row["round_id"], "round_type": row["round_type"]})

    overall = (sum(sum(vals) / len(vals) for vals in legacy_type_scores.values()) / len(legacy_type_scores)
               if legacy_type_scores else sum(row["score"] for row in scored) / len(scored)) * 10
    grouped = defaultdict(list)
    competencies = defaultdict(list)
    for row in evidence:
        grouped[row["round_id"]].append(row)
        competencies[row["competency"]].append(row)
    round_assessments = []
    for rid, rows in grouped.items():
        vals = [row["score"] for row in rows if row["score"] is not None]
        if not vals:
            continue
        round_assessments.append({**_round_descriptor(rid, configured, observed),
            "score": round(sum(vals) / len(vals) * 10, 2),
            "agent_ids": sorted({row["source_agent_id"] for row in rows if row["source_agent_id"]}),
            "evidence_ids": [row["id"] for row in rows],
            "observations": [row["signal"] for row in rows if row["signal"]],
            "strengths": [row["signal"] for row in rows if row["score"] is not None and row["score"] >= 7 and row["signal"]],
            "weaknesses": [row["signal"] for row in rows if row["score"] is not None and row["score"] < 7 and row["signal"]]})
    competency_findings = []
    for competency, rows in competencies.items():
        vals = [row["score"] for row in rows if row["score"] is not None]
        competency_findings.append({"competency_id": competency, "score": round(sum(vals) / len(vals) * 10, 2) if vals else None,
            "evidence_ids": [row["id"] for row in rows], "observations": [row["signal"] for row in rows if row["signal"]],
            "agent_ids": sorted({row["source_agent_id"] for row in rows if row["source_agent_id"]}),
            "round_ids": list(dict.fromkeys(row["round_id"] for row in rows))})
    questions = []
    for row in question_rows:
        qmeta = _dict(row.get("metadata"))
        questions.append({"id": _text(row.get("id")) or None, "question_text": _text(row.get("question_text")),
            "agent_id": _text(row.get("agent_id")) or None, "round_id": _text(row.get("round_id") or qmeta.get("round_id")) or None,
            "competency": _text(row.get("competency")), "exploration_status": _text(row.get("exploration_status")) or None,
            "answer_id": _text(qmeta.get("answered_by")) or None, "timestamp": _timestamp(row.get("timestamp"))})
    handoffs = []
    for row in _rows(metadata.get("handoff_history") or metadata.get("handoffs")):
        _check_scope(row, interview)
        handoffs.append({key: _timestamp(row[key]) if key == "timestamp" else _text(row[key]) or None
                         for key in ("from_agent_id", "to_agent_id", "source_agent_id", "target_agent_id", "round_id", "status", "timestamp") if key in row})
    matched_round_ids = {row["configured_round_id"] for row in round_assessments if row["configured_round_id"]}
    scored_answer_ids = {row["answer_id"] for row in scored if row["answer_id"]}
    evaluated_answer_ids = scored_answer_ids | question_answer_ids
    unlinked_scored_evidence = [row["id"] for row in scored if not row["answer_id"]]
    missing_answer_ids = sorted(scored_answer_ids - set(answer_lookup))
    warnings = []
    if missing_answer_ids or not actual_answers:
        warnings.append("Some evaluated answer transcripts are unavailable; evidence is retained without inventing transcript text.")
    if unlinked_scored_evidence:
        warnings.append("Some scored evidence lacks a verified answer identity; evidence count cannot establish the number of evaluated answers.")
    if any(row["round_id"] == "unknown" or row["identity_resolution"] == "unresolved" for row in round_assessments):
        warnings.append("Some observed round identities cannot be matched uniquely to configured rounds.")
    unobserved = [row for row in configured if row["round_id"] not in matched_round_ids]
    if unobserved:
        warnings.append("Configured rounds without identifiable scored evidence are not scored as completed rounds.")
    return {"interview_id": str(interview["id"]), "candidate_id": str(interview["candidate_id"]),
        "provenance": {"canonical_interview_id": str(interview["id"]),
            "source_interview_id": _text(context.get("source_interview_id")) or str(interview["id"]),
            "graph_interview_ids": _strings(metadata.get("graph_interview_ids"))},
        "overall_score": round(overall, 2), "scoring_method": score_method,
        "round_assessments": round_assessments, "competency_findings": competency_findings,
        "evidence": evidence, "answers": actual_answers, "question_history": questions, "handoffs": handoffs,
        "strengths": list(dict.fromkeys(row["signal"] for row in scored if row["score"] >= 7 and row["signal"])),
        "improvements": list(dict.fromkeys([row["signal"] for row in scored if row["score"] < 7 and row["signal"]]
            + _strings(context.get("open_questions")) + [_text(row.get("contradiction")) for row in _rows(context.get("detected_contradictions")) if _text(row.get("contradiction"))])),
        "coverage": {"configured_rounds": configured, "unobserved_rounds": unobserved,
            "evaluated_answer_count": len(evaluated_answer_ids), "evaluated_answer_ids": sorted(evaluated_answer_ids),
            "scored_answer_count": len(scored_answer_ids), "scored_answer_ids": sorted(scored_answer_ids),
            "answer_identity_complete": not unlinked_scored_evidence,
            "unlinked_scored_evidence_ids": unlinked_scored_evidence,
            "answer_identity_sources": {"scored_evidence": sorted(scored_answer_ids), "recorded_question_assessment": sorted(question_answer_ids)},
            "observed_round_ids": list(grouped), "observed_agent_ids": sorted({row["source_agent_id"] for row in evidence if row["source_agent_id"]}),
            "missing_answer_ids": missing_answer_ids, "warnings": warnings},
        "counts": {"evidence": len(evidence), "scored_evidence": len(scored), "invalid_evidence": invalid_evidence_count,
            "answers": len(actual_answers), "evaluated_answers": len(evaluated_answer_ids), "scored_answers": len(scored_answer_ids),
            "rounds": len(grouped), "questions": len(questions), "handoffs": len(handoffs)}}


def recover_source_from_graph(interview: dict[str, Any], repository: Any) -> dict[str, Any]:
    """Read existing KG entities, strictly scoped by verified interview rounds.

    Invoke only when no saved/live source context is available. This helper is
    synchronous so callers can move graph I/O to a worker thread. It does not
    alter the graph, traverse candidate history for scoring or invent handoffs.
    """
    cid, iid = _text(interview.get("candidate_id")), _text(interview.get("id"))
    if not cid or not iid or repository is None:
        raise ReportEvidenceUnavailable()
    # SessionStore's sole channel mapping is deterministic and remains known
    # after restart. The graph stores that exact channel as interview_id.
    # No fuzzy suffix or candidate-history match is permitted.
    from app.sessions.models import _make_channel_name
    allowed_interview_ids = {iid, _make_channel_name(iid)}
    rounds = repository.get_candidate_interview_rounds(cid, limit=MAX_SOURCE_RECORDS + 1)
    if len(rounds) > MAX_SOURCE_RECORDS:
        raise ReportSourceInvalid("Interview graph recovery cannot verify complete round coverage")
    rounds = [_dict(row) for row in rounds if _dict(row).get("interview_id") in allowed_interview_ids]
    graph_interview_ids = sorted({row["interview_id"] for row in rounds})
    evidence, answers, questions, observed = [], {}, {}, []
    for row in rounds:
        _check_scope({**row, "interview_id": iid}, interview)
        rid = _text(row.get("round_id"))
        if not rid:
            raise ReportSourceInvalid()
        observed.append({"round_id": rid, "round_type": row.get("round_type")})
        rows = repository.get_candidate_evidence(cid, round_id=rid, limit=MAX_SOURCE_RECORDS + 1)
        if len(rows) + len(evidence) > MAX_SOURCE_RECORDS:
            raise ReportSourceInvalid("Interview graph recovery cannot verify complete evidence coverage")
        for item in rows:
            ev = _dict(item)
            if ev.get("candidate_id") != cid or ev.get("round_id") != rid:
                raise ReportSourceInvalid()
            aid = _text(ev.get("answer_id"))
            if aid in answers and answers[aid]["round_id"] != rid:
                raise ReportSourceInvalid("The same graph answer is linked to conflicting interview rounds")
            if aid not in answers:
                answer = _dict(repository.get_answer(aid))
                if not aid or answer.get("answer_id") != aid or answer.get("candidate_id") != cid or answer.get("round_id") != rid:
                    raise ReportSourceInvalid()
                question = _dict(repository.get_question(answer.get("question_id")))
                if not answer.get("question_id") or question.get("question_id") != answer.get("question_id") or question.get("round_id") != rid:
                    raise ReportSourceInvalid()
                answers[aid] = {"id": aid, "interview_id": iid, "candidate_id": cid,
                    "round_id": rid, "question_id": question.get("question_id"), "question_text": question.get("question_text"),
                    "agent_id": question.get("agent_id"), "transcript": answer.get("answer_text"), "created_at": answer.get("created_at"),
                    "duration_seconds": answer.get("duration_seconds")}
                qid = question.get("question_id")
                questions[qid] = {"id": qid, "round_id": rid, "question_text": question.get("question_text"),
                    "agent_id": question.get("agent_id"), "competency": question.get("competency"), "timestamp": question.get("created_at")}
            evidence.append({"id": ev.get("evidence_id"), "signal": ev.get("signal"), "score": ev.get("score"),
                "competency": ev.get("competency"), "round_id": rid, "source_agent_id": ev.get("source_agent_id"),
                "timestamp": ev.get("timestamp"), "metadata": {"answer_id": aid}})
    if not evidence:
        raise ReportEvidenceUnavailable()
    return {"source_kind": "knowledge_graph", "context": {"interview_id": iid, "candidate_id": cid,
            "accumulated_evidence": evidence, "question_history": list(questions.values()),
            "metadata": {"observed_rounds": observed, "graph_interview_ids": graph_interview_ids}},
            "answers": list(answers.values()), "evaluations": []}
