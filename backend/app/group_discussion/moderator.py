from app.group_discussion.models import GDModeratorAction,GDModeratorActionType as Action


class GDModerator:
    def decide(self,session,signals,analysis,participants,sequence):
        state=dict(session.get("moderator_state") or {})
        def result(action,reason,target=None):
            if action!=Action.CONTINUE: state["last_prompt_sequence"]=sequence
            return GDModeratorAction(action=action,rationale=reason,target_participant_id=target),state
        if session["status"]!="active": return result(Action.CONTINUE,"Discussion has ended; evaluate evidence without further prompts")
        if signals["time_remaining_seconds"]<=0: return result(Action.END_DISCUSSION,"Configured duration elapsed")
        if signals["time_remaining_seconds"]<=60 and not state.get("warned_time"):
            state["warned_time"]=True
            return result(Action.WARN_TIME,"One minute or less remains")
        semantic={s.signal for s in analysis.signals} if analysis else set()
        if semantic & {"off_topic","hostile"}: return result(Action.REDIRECT_DISCUSSION,"Return to the topic and respectful exchange")
        if "unclear" in semantic: return result(Action.ASK_CLARIFICATION,"The contribution needs clarification")
        if sequence-state.get("last_prompt_sequence",0)<3: return result(Action.CONTINUE,"Allow uninterrupted human discussion")
        active=[p for p in participants if p["status"]=="joined"]
        if signals["total_turns"]>=3 and active:
            target=min(active,key=lambda p:(signals["participants"][p["id"]]["turn_count"],p["id"]))
            highest=max(signals["participants"][p["id"]]["turn_count"] for p in active)
            lowest=signals["participants"][target["id"]]["turn_count"]
            if highest-lowest>=2:
                return result(Action.ENCOURAGE_PARTICIPATION,"Observed contribution counts are imbalanced",target["id"])
            if signals["total_turns"]>=len(active)*2:
                return result(Action.INTRODUCE_NEW_ANGLE,"All active participants have had opportunities to contribute")
        return result(Action.CONTINUE,"No intervention needed")
