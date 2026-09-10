from pydantic import Field
from app.integrations.aicredits_client import AICreditsError
from app.intelligence.core.contracts import StrictModel
from app.intelligence.core.structured_output import structured_call
from app.role_play.models import RolePlayActionType


class PersonaResponse(StrictModel):
    text: str = Field(min_length=1, max_length=1200)


class RolePlayResponseGenerator:
    def __init__(self, client=None): self.client = client

    @staticmethod
    def policy_response(action):
        # Policy facts are exact source quotations in the separate context panel.
        # Fixed action wording cannot turn generated prose into company policy.
        return {
            RolePlayActionType.END_SCENARIO: "Thank you. This simulation has ended. Your responses and the policy sources used are saved.",
            RolePlayActionType.ESCALATE: "I still have concerns. How would you address them using the supplied policy sources?",
            RolePlayActionType.DEESCALATE: "That helps clarify your approach. How would you confirm the next step against the supplied policy sources?",
            RolePlayActionType.ADVANCE_PHASE: "Let us move to the next part of the situation. Describe your next step using the policy sources shown.",
        }.get(action.action, "Please explain your next step using the policy sources shown. If sources are unavailable, explain how you would ask the company for clarification.")

    async def generate(self, persona, scenario, state, action, text, recent_turns):
        if action.action == RolePlayActionType.END_SCENARIO:
            return "Thank you. This simulation has ended. Your recorded responses will be used for your feedback."
        if action.action == RolePlayActionType.REQUEST_CLARIFICATION:
            return "Please describe the next step you would take in this situation."
        revealed = [scenario.hidden_information[key] for key in state.revealed_keys]
        result = await structured_call("role_play", PersonaResponse,
            "Speak as the simulated persona, following the supplied backend action and stance. "
            "Do not evaluate the candidate, reveal scoring rules, mention hidden state, invent company policies, "
            "or claim real-world actions occurred. Company policy answers are provided separately as source excerpts. "
            "Use only supplied allowed information and the current phase brief.",
            {"persona": {"name": persona.name, "personality": persona.personality, "communication_style": persona.communication_style,
                         "allowed_information": persona.allowed_information + revealed},
             "phase_brief": scenario.phases[state.phase_index].brief, "stance": state.stance,
             "escalation": state.escalation, "action": action.action.value, "candidate_text": text,
             "recent_turns": recent_turns[-4:]}, client=self.client)
        # Secrets are not supplied to NLG, and exact accidental disclosures are rejected too.
        restricted = persona.restricted_information + [value for key,value in scenario.hidden_information.items() if key not in state.revealed_keys]
        if any(secret.strip() and secret.casefold() in result.text.casefold() for secret in restricted):
            raise AICreditsError("response_invalid")
        return result.text
