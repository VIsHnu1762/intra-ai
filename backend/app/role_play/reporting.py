from app.core.exceptions import ValidationError
from app.integrations.aicredits_client import AICreditsError
from app.integrations.feature_db import rpc
from app.intelligence.core.contracts import EvidenceSignal
from app.intelligence.core.reporting import assessment, ReportNarrative, validate_narrative, narrative_payload
from app.intelligence.core.structured_output import structured_call


class RolePlayReporting:
    def __init__(self, repo, client=None): self.repo, self.client = repo, client

    async def generate(self, session, actor):
        if session["status"] != "completed": raise ValidationError("Complete the role-play before generating a report")
        if session.get("report_status") == "ready": return session["report"]
        events = await self.repo.events(session["id"])
        turns = [event for event in events if event["kind"] == "turn"]
        evidence = [EvidenceSignal.model_validate(item) for event in turns for item in event.get("evidence", [])]
        try:
            result = assessment(evidence, candidate_id=str(session["candidate_id"]), session_id=session["id"])
            narrative = await structured_call("role_play", ReportNarrative,
                "Format a role-play coaching report from the supplied saved evidence and deterministic scores. "
                "Do not rescore. Distinguish observed behavior from inference. Every strength/improvement must cite supplied evidence IDs. "
                "Do not make hiring recommendations or disclose hidden scenario state. "
                "Do not restate or invent company policy; exact saved source snapshots are attached separately.",
                {"assessment": narrative_payload(result), "scenario_title": session["scenario_snapshot"]["definition"]["title"]}, client=self.client)
            result["narrative"] = validate_narrative(narrative, evidence)
            result["kind"] = "role_play"
            result["total_turns"] = len(turns)
            result["unevaluated_turns"] = sum(event["analysis"].get("status") != "evaluated" for event in turns)
            result["policy_contexts"] = []
            seen = set()
            for event in turns:
                context = event.get("policy_context") or {}
                source_key = tuple(source["chunk_id"] for source in context.get("excerpts", []))
                if context.get("status") == "available" and source_key not in seen:
                    seen.add(source_key)
                    result["policy_contexts"].append(context)
            result["policy_contexts"] = result["policy_contexts"][:4]
            return await rpc(self.repo.sb, "publish_roleplay_report", p_actor=actor.user_id,
                p_session_id=session["id"], p_report=result, p_error=None)
        except (AICreditsError, ValidationError) as exc:
            await rpc(self.repo.sb, "publish_roleplay_report", p_actor=actor.user_id,
                p_session_id=session["id"], p_report=None, p_error=getattr(exc, "code", "INSUFFICIENT_EVIDENCE"))
            raise ValidationError("A role-play report is not ready. Saved evidence is preserved; sufficient evaluated turns and valid provider output are required") from None


def report_view(report, candidate=False):
    if not report: return None
    if not candidate: return report
    # No raw evidence, source identities or private evaluation notes in candidate responses.
    return {"kind": "role_play", "candidate_rating": report["candidate_rating"],
            "performance_band": report["performance_band"], "dimensions": report["dimensions"],
            "evaluated_turns": report["evaluated_turns"],
            "total_turns": report.get("total_turns", report["evaluated_turns"]),
            "unevaluated_turns": report.get("unevaluated_turns", 0),
            "policy_contexts": report.get("policy_contexts", []),
            "feedback": {"strengths": [i["text"] for i in report["narrative"]["strengths"]],
                         "improvements": [i["text"] for i in report["narrative"]["improvements"]]}}
