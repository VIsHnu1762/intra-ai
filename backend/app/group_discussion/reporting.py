from app.core.exceptions import ConflictError, ValidationError
from app.integrations.aicredits_client import AICreditsError
from app.integrations.feature_db import rpc
from app.intelligence.core.contracts import EvidenceSignal
from app.intelligence.core.reporting import assessment,ReportNarrative,validate_narrative,narrative_payload
from app.intelligence.core.structured_output import structured_call
from app.intelligence.group_discussion.signals import participation_signals


class GDReporting:
    def __init__(self,repo,client=None):self.repo,self.client=repo,client

    async def generate(self,session,participant,actor):
        if session["status"]!="completed":raise ConflictError("Finish the discussion before generating individual feedback")
        if participant["report_status"]=="ready":return participant["report"]
        events=await self.repo.events(session["id"])
        own=[e for e in events if e["participant_id"]==participant["id"] and e["kind"]=="message"]
        if any(e["analysis"].get("status")=="pending" for e in own):raise ConflictError("Saved contributions are still being evaluated. Retry shortly")
        evidence=[EvidenceSignal.model_validate(item) for e in own for item in e["evidence"]]
        try:
            result=assessment(evidence,candidate_id=str(participant["candidate_id"]),session_id=session["id"])
            narrative=await structured_call("gd",ReportNarrative,
                "Format individual group-discussion coaching from this participant's saved evidence and deterministic assessment. "
                "Do not rescore, compare with other participants, invent evidence or make hiring decisions. "
                "Message frequency is not a measure of argument quality or leadership. Every strength/improvement cites supplied evidence IDs. "
                "Do not restate or invent company policy. Exact policy source snapshots are attached separately.",
                {"assessment":narrative_payload(result),"topic":session["configuration"]["topic"]},client=self.client)
            result["narrative"]=validate_narrative(narrative,evidence);result["kind"]="group_discussion"
            signals=participation_signals(events,await self.repo.participants(session["id"]),started_at=session.get("started_at"),duration_seconds=session["configuration"]["duration_seconds"])
            result["participation"]=signals["participants"][participant["id"]]
            result["total_turns"]=len(own);result["unevaluated_turns"]=sum(e["analysis"].get("status")!="evaluated" for e in own)
            policy_contexts=[];seen=set()
            for event in own:
                context=event.get("policy_context") or {}
                if context.get("status")!="available":continue
                source_key=tuple(item["chunk_id"] for item in context.get("excerpts",[]))
                if source_key not in seen:
                    seen.add(source_key);policy_contexts.append(context)
            result["policy_contexts"]=policy_contexts[:4]
            return await rpc(self.repo.sb,"publish_gd_report",p_actor=actor.user_id,p_participant_id=participant["id"],p_report=result,p_error=None)
        except (AICreditsError,ValidationError) as exc:
            await rpc(self.repo.sb,"publish_gd_report",p_actor=actor.user_id,p_participant_id=participant["id"],p_report=None,p_error=getattr(exc,"code","INSUFFICIENT_EVIDENCE"))
            raise ValidationError("Individual feedback is not ready. At least two evaluated contributions and valid provider output are required") from None


def report_view(report,candidate=False):
    if not report:return None
    if not candidate:return report
    return {key:report[key] for key in ("kind","candidate_rating","performance_band","dimensions","evaluated_turns","participation","total_turns","unevaluated_turns")} | {
        "feedback":{"strengths":[i["text"] for i in report["narrative"]["strengths"]],"improvements":[i["text"] for i in report["narrative"]["improvements"]]},
        "policy_contexts":report.get("policy_contexts",[])}
