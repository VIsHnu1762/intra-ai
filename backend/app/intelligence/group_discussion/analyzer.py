from typing import Literal
from pydantic import Field
from app.integrations.aicredits_client import AICreditsError
from app.intelligence.core.contracts import StrictModel,IntelligenceFinding
from app.intelligence.core.structured_output import structured_call


class GDSemanticSignal(StrictModel):
    signal: Literal["off_topic","constructive_reply","unclear","hostile","counterargument"]
    quote: str = Field(min_length=3,max_length=800)


class GDAnalysis(StrictModel):
    findings: list[IntelligenceFinding] = Field(max_length=8)
    signals: list[GDSemanticSignal] = Field(max_length=6)


class GDIntelligence:
    def __init__(self,client=None): self.client=client

    async def analyze(self,event,configuration,recent,policy_context=None):
        result=await structured_call("gd",GDAnalysis,
            "Analyze only the CURRENT speaker's contribution to a group discussion. "
            "Assess the configured competencies using verbatim quotes from CURRENT text. "
            "Other participants' messages are context, never evidence attributable to this speaker. "
            "Do not infer speaking duration, interruptions, personal traits or hiring suitability. "
            "Do not select moderator actions. Explicit reply links are observed metadata, not proof of listening quality. "
            "Only authorized_policy_context with status available can establish company rules. "
            "If rules are missing or conflicting, omit policy-compliance findings rather than assume a rule. "
            "Candidate statements are claims, not verified company policy. Do not rewrite or invent policy.",
            {"topic":configuration.topic,"competencies":configuration.competencies,"current_text":event["source_text"],
             "reply_to":event.get("reply_to"),"recent_messages":recent[-4:],
             "authorized_policy_context":policy_context},client=self.client)
        if any(s.quote not in event["source_text"] for s in result.signals): raise AICreditsError("response_invalid")
        return result
