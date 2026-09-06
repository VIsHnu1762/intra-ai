"""Compatibility helpers for assigning one or more agents to an interview round.

The hosted Supabase project may not have the newer ``agent_ids`` column yet.
Round assignments are therefore also encoded in a private focus-area marker so
that jobs created before the migration continue to carry their configuration.
"""

from __future__ import annotations

from typing import Any, Iterable

AGENT_IDS_MARKER = "__intra_agent_ids__:"

DEFAULT_AGENT_BY_ROUND = {
    "introduction": "alex",
    "technical": "alex",
    "behavioral": "jordan",
    "hr_culture": "jordan",
}


def normalize_agent_ids(value: Any) -> list[str]:
    """Return stable, lower-case, de-duplicated agent IDs."""
    if value is None:
        return []
    values: Iterable[Any]
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = [value]
    result: list[str] = []
    for item in values:
        clean = str(item).strip().lower()
        if clean and clean not in result:
            result.append(clean)
    return result


def decode_round_agents(row: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Decode explicit or legacy round assignments and return clean focus areas."""
    raw_focus = row.get("focus_areas") or []
    focus = [str(item).strip() for item in raw_focus if str(item).strip()]
    marker_ids: list[str] = []
    clean_focus: list[str] = []
    for item in focus:
        if item.startswith(AGENT_IDS_MARKER):
            marker_ids.extend(normalize_agent_ids(item[len(AGENT_IDS_MARKER) :]))
        else:
            clean_focus.append(item)

    agent_ids = normalize_agent_ids(row.get("agent_ids"))
    if not agent_ids:
        agent_ids = normalize_agent_ids(row.get("agent_id"))
    if not agent_ids:
        agent_ids = marker_ids
    if not agent_ids:
        fallback = DEFAULT_AGENT_BY_ROUND.get(str(row.get("type") or "").strip().lower())
        if fallback:
            agent_ids = [fallback]
    return agent_ids, clean_focus


def encode_agent_ids(focus_areas: Iterable[Any] | None, agent_ids: Any) -> list[str]:
    """Encode assignments in a round row while keeping focus areas user-visible."""
    clean_focus = [
        str(item).strip()
        for item in (focus_areas or [])
        if str(item).strip() and not str(item).strip().startswith(AGENT_IDS_MARKER)
    ]
    ids = normalize_agent_ids(agent_ids)
    if ids:
        clean_focus.append(AGENT_IDS_MARKER + ",".join(ids))
    return clean_focus
