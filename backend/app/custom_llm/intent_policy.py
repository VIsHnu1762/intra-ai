"""Conversational assistance outside competency scoring; no extra model calls."""
import re


def clarification_response(
    utterance: str,
    question: str | None,
    *,
    competency: str | None = None,
    subject: str | None = None,
    agent_role: str | None = None,
) -> str:
    """Explain a term and ask one concrete version of the active question.

    The caller supplies only a supported CV/answer subject. An absent subject
    invites a real example rather than inventing an application or experience.
    No model request, competency selection, or context mutation takes place.
    """
    definitions = {
        "scalability": "Scalability means how a system handles more users or work while maintaining acceptable performance.",
        "trade-off": "A trade-off is a benefit you gain by accepting a cost or limitation in another area.",
        "latency": "Latency is the time between a request and its response.",
        "throughput": "Throughput is how much work a system completes in a given amount of time.",
        "prioritization": "Prioritization means deciding which needs to address first and why.",
        "customer impact": "Customer impact means the observable change a feature makes for the people using it.",
    }
    # ASR can spell the same term as trade-off, trade-offs, tradeoff, or
    # trade offs. Canonicalize those forms before looking up an explanation.
    def normalize_terms(text: str) -> str:
        return re.sub(r"\btrade[\s\-–—]*offs?\b", "trade-off", text.lower())

    normalized = normalize_terms(utterance)
    active = normalize_terms(question or "")
    term = next((term for source in (normalized, active) for term in definitions
                 if re.search(r"\b" + re.escape(term) + r"\b", source)), None)
    topic = (competency or "").casefold().replace("-", "_").replace(" ", "_")
    if not topic:
        # The active question is only used for bounded objective recognition;
        # never repeat its vague or overly complex wording back to the user.
        topic = next((name for name, pattern in (
            ("coding_problem_solving", r"\b(?:coding|code|algorithm|programming)\b"),
            ("debugging", r"\b(?:bug|debug|debugging)\b"),
            ("software_architecture", r"\b(?:architecture|architectural)\b"),
            ("product_sense", r"\b(?:user problem|customer problem|product sense)\b"),
        ) if re.search(pattern, active)), "")

    # Definitions use the term actually queried; the simpler question preserves
    # the active competency when one is available. A generic clarification can
    # otherwise use the named term to explain its concrete objective.
    if not topic or topic in {"general", "experience", "technical_depth"}:
        topic = {
            "trade-off": "technical_decision_making",
            "customer impact": "customer_impact",
        }.get(term, term or topic)
    safe_subject = re.sub(r"\s+", " ", subject).strip() if isinstance(subject, str) else ""
    if not safe_subject or len(safe_subject) > 150 or re.search(r"[?!;\n]", safe_subject):
        safe_subject = "a project you worked on"

    if topic == "scalability":
        simplified = f"In {safe_subject}, what would you change first if ten times as many people used it?"
    elif topic == "latency":
        simplified = f"In {safe_subject}, what would you check first if a request took too long to respond?"
    elif topic == "throughput":
        simplified = f"In {safe_subject}, what would you change to complete more requests each second?"
    elif topic in {"coding_problem_solving", "coding", "problem_solving"}:
        simplified = f"In {safe_subject}, what was one coding problem you solved yourself?"
    elif topic in {"debugging", "reliability"}:
        simplified = f"In {safe_subject}, how did you find the cause of one bug?"
    elif topic in {"technical_decision_making", "trade_off_decisions", "trade_off_analysis"}:
        simplified = f"In {safe_subject}, why did you choose one approach over another?"
    elif topic == "prioritization":
        simplified = f"In {safe_subject}, which user need did you choose to address first?"
    elif topic in {"metrics_and_roi", "metrics", "success_metrics"}:
        simplified = f"For {safe_subject}, what result did you use to judge whether it helped users?"
    elif (topic in {"product_sense", "customer_understanding", "customer_impact", "problem_identification", "product_strategy", "requirements_thinking"}
          or (not topic and "product" in (agent_role or "").casefold())):
        simplified = f"What problem did {safe_subject} solve for the people using it?"
    else:
        simplified = f"In {safe_subject}, what part did you personally build?"

    explanation = definitions.get(term, "")
    if not explanation and re.search(r"\btechnical details?\b", normalized):
        explanation = "By technical details, I mean what you personally built and how it worked."
    return f"{explanation} {simplified}".strip()
