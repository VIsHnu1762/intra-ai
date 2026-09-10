from datetime import datetime, timezone
import re


def timestamp(value):
    return value if isinstance(value,datetime) else datetime.fromisoformat(value.replace("Z","+00:00"))


def participation_signals(events,participants,*,started_at=None,now=None,duration_seconds=1200):
    """Only observed text signals. Media duration/interruptions are intentionally unknown."""
    now=now or datetime.now(timezone.utc)
    messages=[e for e in events if e["kind"]=="message"]
    result={}
    for participant in participants:
        own=[e for e in messages if e["participant_id"]==participant["id"]]
        last=timestamp(own[-1]["created_at"]) if own else timestamp(participant.get("joined_at") or started_at) if participant.get("joined_at") or started_at else now
        result[participant["id"]]={"turn_count":len(own),"word_count":sum(len(re.findall(r"\w+",e["source_text"])) for e in own),
            "reply_count":sum(bool(e.get("reply_to")) for e in own),
            "text_participation_share":round(len(own)/len(messages),4) if messages else 0,
            "silence_seconds":max(0,round((now-last).total_seconds())),
            "speaking_seconds":None,"audio_interruptions":None,"timing_source":"server_text_events"}
    elapsed=max(0,(now-timestamp(started_at)).total_seconds()) if started_at else 0
    return {"participants":result,"total_turns":len(messages),"time_remaining_seconds":max(0,round(duration_seconds-elapsed)),
            "media_signals_available":False}
