from app.services.round_agents import decode_round_agents, encode_agent_ids


def test_round_agent_assignment_round_trips_without_polluting_focus_areas():
    encoded = encode_agent_ids(["system_design"], ["Alex", "jordan", "alex"])
    assert encoded == ["system_design", "__intra_agent_ids__:alex,jordan"]
    assert decode_round_agents({"type": "technical", "focus_areas": encoded}) == (
        ["alex", "jordan"],
        ["system_design"],
    )


def test_legacy_rounds_get_safe_type_defaults():
    assert decode_round_agents({"type": "behavioral", "focus_areas": ["user_empathy"]}) == (
        ["jordan"],
        ["user_empathy"],
    )
