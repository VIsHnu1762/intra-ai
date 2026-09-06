"""Small, deterministic personalization from the candidate's supplied profile."""

from __future__ import annotations

import re
from typing import Any


def candidate_profile(metadata: dict[str, Any]) -> dict[str, Any]:
    raw = metadata.get("candidate_profile") or metadata.get("parsed_resume") or {}
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        return {}
    return raw.get("parsed_resume") if isinstance(raw.get("parsed_resume"), dict) else raw


def candidate_first_name(metadata: dict[str, Any]) -> str | None:
    """Prefer an explicit given name; never derive a name from email or IDs."""
    profile = candidate_profile(metadata)
    value = (metadata.get("candidate_first_name") or profile.get("first_name")
             or metadata.get("candidate_name") or profile.get("name") or profile.get("full_name"))
    if not isinstance(value, str):
        return None
    words = value.strip().split()
    while words and words[0].rstrip(".").casefold() in {"mr", "mrs", "ms", "miss", "dr", "prof"}:
        words.pop(0)
    if not words:
        return None
    name = words[0]
    if len(name) > 50 or name.casefold() in {"candidate", "unknown", "anonymous", "n/a", "null", "none"}:
        return None
    if not any(char.isalpha() for char in name) or not all(char.isalpha() or char in "-'’" for char in name):
        return None
    return name


def relevant_cv_project(metadata: dict[str, Any]) -> str | None:
    """Prefer CV projects whose stated technologies overlap the job's skills."""
    projects = [item for item in candidate_profile(metadata).get("projects", [])
                if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()]
    if not projects:
        return None
    required = {str(skill).strip().casefold() for skill in metadata.get("required_skills", [])}

    def overlap(project: dict[str, Any]) -> int:
        technologies = project.get("technologies") or []
        if not isinstance(technologies, list):
            return 0
        return len(required.intersection(str(item).strip().casefold() for item in technologies))

    # max is stable for ties, keeping the CV's order when no overlap is known.
    name = max(projects, key=overlap)["name"]
    return re.sub(r"\s+", " ", name).strip()[:120]


def relevant_cv_skill(metadata: dict[str, Any]) -> str | None:
    """Use a claimed CV skill only when the JD also requests that skill."""
    required = {str(skill).strip().casefold() for skill in metadata.get("required_skills", [])}
    return next((skill.strip() for skill in candidate_profile(metadata).get("skills", [])
                 if isinstance(skill, str) and skill.strip().casefold() in required), None)
