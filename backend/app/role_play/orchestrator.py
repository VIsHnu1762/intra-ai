from datetime import datetime, timezone
from app.role_play.models import RolePlayAction, RolePlayActionType, RolePlayState, RolePlaySignal


class RolePlayOrchestrator:
    def decide(self, state: RolePlayState, persona, scenario, analysis, *, now=None):
        now = now or datetime.now(timezone.utc)
        next_state = state.model_copy(deep=True)
        phase = scenario.phases[state.phase_index]
        next_state.turn_count += 1; next_state.phase_turns += 1
        signal_set = {item.signal for item in analysis.signals} if analysis else set()
        action, reason = RolePlayActionType.RESPOND, "Continue the current phase"
        if analysis is None:
            action, reason = RolePlayActionType.REQUEST_CLARIFICATION, "Behavioral analysis unavailable; preserve the response without scoring"
        elif signal_set & set(persona.escalation_signals):
            next_state.escalation = min(5, state.escalation+1)
            action, reason = RolePlayActionType.ESCALATE, "Configured escalation signal observed"
        elif signal_set & set(persona.deescalation_signals):
            next_state.escalation = max(0, state.escalation-1)
            action, reason = RolePlayActionType.DEESCALATE, "Configured de-escalation signal observed"
        if analysis:
            for item in analysis.signals:
                if item.signal == RolePlaySignal.COMMITMENT:
                    next_state.commitments = (next_state.commitments + [item.quote])[-12:]
        next_state.stance = "resistant" if next_state.escalation >= 4 else "engaged" if next_state.escalation <= 1 else "guarded"
        elapsed = (now-state.started_at).total_seconds() if state.started_at else 0
        failed = next_state.escalation == 5 and bool(signal_set & set(scenario.failure_signals))
        exhausted = elapsed >= scenario.duration_seconds or next_state.turn_count >= scenario.max_turns
        achieved = bool(signal_set & set(phase.advance_on)) and next_state.phase_turns >= phase.min_turns
        phase_exhausted = next_state.phase_turns >= phase.max_turns
        final_phase = state.phase_index == len(scenario.phases)-1
        if achieved: next_state.achieved_phases = list(dict.fromkeys(next_state.achieved_phases+[phase.id]))
        if failed or exhausted or (final_phase and next_state.turn_count >= 2 and (achieved or phase_exhausted)):
            next_state.status = "completed"; next_state.ended_at = now
            next_state.completion_reason = "escalation_limit" if failed else "time_limit" if elapsed >= scenario.duration_seconds else "turn_limit" if exhausted else "objectives_demonstrated" if achieved and bool(signal_set & set(scenario.success_signals)) else "scenario_exhausted"
            action, reason = RolePlayActionType.END_SCENARIO, next_state.completion_reason
        elif not final_phase and (achieved or phase_exhausted):
            next_state.phase_index += 1; next_state.phase_turns = 0
            next_state.revealed_keys = list(dict.fromkeys(next_state.revealed_keys + scenario.phases[next_state.phase_index].reveal_keys))
            action, reason = RolePlayActionType.ADVANCE_PHASE, "Configured phase progression condition reached"
        next_state.unresolved_objections = persona.concerns[:10] if next_state.escalation >= 2 else []
        return next_state, RolePlayAction(action=action, rationale=reason, phase_id=scenario.phases[next_state.phase_index].id)
