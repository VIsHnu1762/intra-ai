"""Evidence validation and existing report scoring primitives, without domain routing."""
from collections import defaultdict
from pydantic import Field
from app.core.exceptions import ValidationError
from app.intelligence.core.contracts import StrictModel, EvidenceSignal
from app.services.report_service import rating_from_score, performance_band


class CitedObservation(StrictModel):
    text: str = Field(min_length=5, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class ReportNarrative(StrictModel):
    summary: str = Field(min_length=10, max_length=1500)
    strengths: list[CitedObservation] = Field(max_length=8)
    improvements: list[CitedObservation] = Field(max_length=8)


def assessment(evidence: list[EvidenceSignal], *, candidate_id: str, session_id: str):
    if any(e.candidate_id != candidate_id or e.session_id != session_id for e in evidence):
        raise ValidationError("Report evidence identity is invalid")
    if len({e.event_id for e in evidence}) < 2:
        raise ValidationError("At least two evaluated candidate turns are required for a report")
    ids = [e.id for e in evidence]
    if len(set(ids)) != len(ids): raise ValidationError("Duplicate evidence cannot contribute to a report")
    grouped = defaultdict(list)
    for e in evidence: grouped[e.competency].append(e.score)
    dimensions = {key: round(sum(scores)/len(scores)*10, 2) for key, scores in grouped.items()}
    score = round(sum(dimensions.values())/len(dimensions), 2)
    return {"overall_score": score, "candidate_rating": rating_from_score(score), "performance_band": performance_band(score),
            "dimensions": dimensions, "evaluated_turns": len({e.event_id for e in evidence}),
            "evidence_ids": ids, "evidence": [e.model_dump(mode="json") for e in evidence]}


def validate_narrative(narrative: ReportNarrative, evidence: list[EvidenceSignal]):
    ids = {e.id for e in evidence}
    for item in [*narrative.strengths, *narrative.improvements]:
        if not set(item.evidence_ids) <= ids:
            raise ValidationError("Report narrative cites unknown evidence")
    return narrative.model_dump()


def narrative_payload(result):
    """All saved evidence determines scores; a bounded sample supports prose."""
    sampled=[]; seen=set()
    for item in result["evidence"]:
        if item["competency"] not in seen:
            sampled.append(item); seen.add(item["competency"])
    selected_ids={item["id"] for item in sampled}
    sampled += [item for item in result["evidence"] if item["id"] not in selected_ids][:max(0,16-len(sampled))]
    return {"overall_score":result["overall_score"],"performance_band":result["performance_band"],
            "dimensions":result["dimensions"],"evaluated_turns":result["evaluated_turns"],
            "evidence_sample_count":len(sampled),"evidence_total":len(result["evidence"]),
            "evidence":[{key:item[key] for key in ("id","competency","observation","quote","score","confidence")} for item in sampled]}
