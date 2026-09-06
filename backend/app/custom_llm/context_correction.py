"""Conservative handling of corrections to an application's spoken name.

These utterances identify the subject, not technical capability. Only complete
name corrections are handled here; answers about changed implementations still
go to M1, including statements such as 'not SQL, we used NoSQL'.
"""
from __future__ import annotations

import re

_NAME = r"(?:[A-Za-z][A-Za-z0-9+-]*\s+){0,4}(?:application|software|app|project|platform|system|chatbot)"
_EXPLICIT = re.compile(
    rf"^(?:(?:so|sorry|no|actually)[,\s]+)*(?:it(?:'s| is)|this is|the project is)\s+not\s+"
    rf"(?:a |an |the )?(?P<old>{_NAME})[,;.\s]+(?:it(?:'s| is)|this is|but|it should be)\s+"
    rf"(?:a |an |the )?(?P<new>{_NAME})[.!\s]*$", re.I,
)


def project_name_correction(answer: str) -> tuple[str, str] | None:
    match = _EXPLICIT.fullmatch(answer.strip())
    if not match:
        return None
    old, new = match['old'].strip(), match['new'].strip()
    # Architectural properties are claims to assess, even when phrased using
    # the noun 'system'; they are not spoken application-name corrections.
    if re.search(r'\b(?:synchronous|asynchronous|distributed|monolithic|stateful|stateless|event[- ]driven|microservices?)\b',
                 old + ' ' + new, re.I):
        return None
    return (old, new) if old.casefold() != new.casefold() else None


def corrected_question(question: str, old: str, new: str) -> str:
    # Preserve the original information target; replace only the corrected name.
    result = re.sub(r'\b' + re.escape(old) + r'\b', lambda _: new, question, flags=re.I)
    # The earlier question may have shortened 'webmaster application' to
    # 'webmaster'. Don't guess at unrelated nouns in that case.
    old_label = re.sub(r'\s+(?:application|software|app|project|platform|system|chatbot)$', '', old, flags=re.I)
    new_label = re.sub(r'\s+(?:application|software|app|project|platform|system|chatbot)$', '', new, flags=re.I)
    if result == question and old_label:
        result = re.sub(r'\b' + re.escape(old_label) + r'\b', lambda _: new_label, question, flags=re.I)
    # A previous mistaken insistence must not be repeated with a new noun.
    result = re.sub(r"^I(?:'d| would) like to stay focused on [^.]+\.\s*", '', result, flags=re.I)
    result = re.sub(r'^Regardless of (?:the )?classification,\s*', '', result, flags=re.I)
    return result[:1].upper() + result[1:]
