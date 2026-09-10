from pydantic import Field
from app.intelligence.core.contracts import StrictModel
from app.intelligence.core.structured_output import structured_call
from app.group_discussion.models import GDModeratorActionType as Action


class ModeratorResponse(StrictModel):
    text: str = Field(min_length=1,max_length=800)


class GDResponseGenerator:
    @staticmethod
    def policy_response(action):
        """Policy-grounded sessions never use free-form generation for policy prose."""
        return {
            "CONTINUE":"",
            "ENCOURAGE_PARTICIPATION":"Let us make room for someone who has contributed less so far.",
            "REDIRECT_DISCUSSION":"Please return to the discussion topic and distinguish proposals from the quoted policy sources.",
            "ASK_CLARIFICATION":"Could you clarify your proposal and the assumptions behind it?",
            "INTRODUCE_NEW_ANGLE":"What alternative would you consider, and what trade-off would it introduce?",
            "REQUEST_RESPONSE":"Who would like to respond to the previous contribution?",
            "WARN_TIME":"We are approaching the end. Please summarize your main proposal.",
            "END_DISCUSSION":"The discussion has ended. Thank you for contributing.",
        }[action.action.value]

    def __init__(self,client=None): self.client=client

    async def generate(self,action,configuration,recent,participants):
        if action.action==Action.CONTINUE:return ""
        if action.action==Action.END_DISCUSSION:return "The discussion time has ended. Thank you for your contributions."
        if action.action==Action.WARN_TIME:return "About one minute remains. Please bring your discussion toward a conclusion."
        target=next((p["display_name"] for p in participants if p["id"]==action.target_participant_id),None)
        result=await structured_call("gd",ModeratorResponse,
            "Express the supplied moderator decision in one or two short neutral sentences. "
            "Do not score participants, mention private assessments, invent company policy, or claim audio timing observations. "
            "Use the supplied participant display name only when a target is provided. Let the human participants do the discussing.",
            {"topic":configuration.topic,"action":action.action.value,"target_name":target,"recent_messages":recent[-4:]},client=self.client)
        return result.text
