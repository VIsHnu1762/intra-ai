from app.intelligence.core.contracts import EvidenceSignal


def ground_findings(findings, *, text, competencies, event_id, candidate_id, session_id, source_type,
                    observed_at, participant_id=None, phase_id=None):
    """Bind identity/provenance on the server; accept only verbatim source quotes."""
    from uuid import NAMESPACE_URL, uuid5

    seen, evidence = set(), []
    normalized_competencies = {comp.strip().lower() for comp in competencies}
    for finding in findings:
        competency = finding.competency.strip().lower()
        if competency not in normalized_competencies or competency in seen:
            continue
        if finding.quote not in text:
            continue
        seen.add(competency)
        evidence.append(EvidenceSignal(**finding.model_dump(),
            id=str(uuid5(NAMESPACE_URL, event_id + ":" + competency)), event_id=event_id,
            candidate_id=candidate_id, session_id=session_id, source_type=source_type, observed_at=observed_at,
            participant_id=participant_id, phase_id=phase_id))
    return evidence
