"""Deterministic job-description extraction for the recruiter preview flow.

The preview intentionally does not introduce another model dependency.  It extracts
useful fields from plain text and leaves the recruiter in control of the final job
configuration.
"""

from __future__ import annotations

import io
import re
from typing import Any

from app.schemas.jobs import JdParseResponse


_SKILL_TERMS = (
    "python", "java", "javascript", "typescript", "react", "next.js", "node.js",
    "sql", "postgresql", "redis", "docker", "kubernetes", "aws", "gcp", "azure",
    "graphql", "rest", "fastapi", "django", "machine learning", "ai", "llm",
    "langgraph", "neo4j", "supabase", "agora", "terraform", "git", "system design",
    "software architecture", "coding", "scalability", "distributed systems", "debugging",
    "technical depth", "database optimization", "product sense", "customer impact",
    "prioritization", "stakeholder management", "user empathy", "trade-off analysis",
)

_SKILL_LABELS = {
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "react": "React",
    "next.js": "Next.js",
    "node.js": "Node.js",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "redis": "Redis",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "graphql": "GraphQL",
    "rest": "REST APIs",
    "fastapi": "FastAPI",
    "django": "Django",
    "machine learning": "Machine Learning",
    "ai": "AI",
    "llm": "LLM",
    "langgraph": "LangGraph",
    "neo4j": "Neo4j",
    "supabase": "Supabase",
    "agora": "Agora",
    "terraform": "Terraform",
    "git": "Git",
    "system design": "System Design",
    "software architecture": "Software Architecture",
    "coding": "Coding",
    "scalability": "Scalability",
    "distributed systems": "Distributed Systems",
    "debugging": "Debugging",
    "technical depth": "Technical Depth",
    "database optimization": "Database Optimization",
    "product sense": "Product Sense",
    "customer impact": "Customer Impact",
    "prioritization": "Prioritization",
    "stakeholder management": "Stakeholder Management",
    "user empathy": "User Empathy",
    "trade-off analysis": "Trade-off Analysis",
}

_COMPETENCY_IDS = {
    "system design": "system_design",
    "software architecture": "software_architecture",
    "coding": "coding_problem_solving",
    "scalability": "scalability",
    "distributed systems": "distributed_systems",
    "debugging": "debugging",
    "technical depth": "technical_depth",
    "database optimization": "database_optimization",
    "product sense": "product_sense",
    "customer impact": "customer_impact",
    "prioritization": "prioritization",
    "stakeholder management": "stakeholder_management",
    "user empathy": "user_empathy",
    "trade-off analysis": "trade_off_analysis",
}


def _extract_document_text(content: bytes, filename: str | None, content_type: str | None) -> str:
    name = (filename or "").lower()
    if "pdf" in (content_type or "").lower() or name.endswith(".pdf"):
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(content)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if text.strip():
                return text
        except Exception:
            pass
    if "word" in (content_type or "").lower() or name.endswith((".docx", ".doc")):
        try:
            from docx import Document  # type: ignore[import-not-found]

            document = Document(io.BytesIO(content))
            text = "\n".join(p.text for p in document.paragraphs)
            if text.strip():
                return text
        except Exception:
            pass
    return content.decode("utf-8", errors="replace")


def parse_job_description(text: str) -> JdParseResponse:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    lines = cleaned.splitlines()
    title = ""
    for line in lines[:8]:
        match = re.search(r"(?:job\s*title|role\s*title|position|opportunity\s*title)\s*[:\-]\s*(.+)", line, re.I)
        if match:
            title = match.group(1).strip()[:255]
            break
    if not title:
        # Branded PDFs often put the company name on the first line and the
        # actual role on the next line. Prefer a role-looking line and skip
        # common document labels such as INTRA AI, SUMMARY, or OVERVIEW.
        role_pattern = re.compile(
            r"\b(engineer|developer|designer|scientist|architect|manager|analyst|specialist|lead|director|consultant)\b",
            re.I,
        )
        ignored = {"intra ai", "job description", "role overview", "overview", "how you will succeed"}
        for line in lines[:12]:
            candidate = line.strip(" -*:")
            if candidate.lower() in ignored:
                continue
            if role_pattern.search(candidate):
                title = candidate[:255]
                break
    if not title and lines:
        title = lines[0][:255]

    lower = cleaned.lower()
    title_lower = title.lower()
    # Use the role title and explicit department labels for classification.
    # Descriptions commonly mention "product" or "sales" while describing
    # collaboration, which should not override an Engineering role.
    department = ""
    if any(k in title_lower for k in ("machine learning", "ml engineer", "ai engineer")):
        department = "AI / Machine Learning"
    elif any(k in title_lower for k in ("engineer", "developer", "architect", "technical")):
        department = "Engineering"
    elif "product" in title_lower:
        department = "Product Management"
    elif any(k in title_lower for k in ("designer", "design", "ux")):
        department = "Design / UX"
    elif any(k in title_lower for k in ("data", "analytics")):
        department = "Data & Analytics"
    elif "sales" in title_lower:
        department = "Sales"
    elif "marketing" in title_lower:
        department = "Developer Relations"
    elif any(k in lower for k in ("software", "engineer", "developer", "technical")):
        department = "Engineering"
    else:
        department = "Engineering"

    job_type = "remote" if "remote" in lower else "onsite" if "on-site" in lower or "onsite" in lower else "hybrid"
    detected_terms = [
        term for term in _SKILL_TERMS
        if re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", lower)
    ]
    required_skills = [_SKILL_LABELS.get(term, term.title()) for term in detected_terms]
    experience_min = experience_max = None
    exp = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?)", lower)
    if exp:
        experience_min, experience_max = int(exp.group(1)), int(exp.group(2))
    else:
        exp = re.search(r"(\d+)\+?\s*(?:years?|yrs?)", lower)
        if exp:
            experience_min = int(exp.group(1))
            experience_max = None

    salary_min = salary_max = None
    salaries = [float(v.replace(",", "")) for v in re.findall(r"(?:\$|usd\s*)([\d,]+(?:\.\d+)?)", lower, re.I)]
    if len(salaries) >= 2:
        salary_min, salary_max = salaries[0], salaries[1]

    education = None
    education_match = re.search(r"(bachelor(?:'s)?|master(?:'s)?|phd|degree)[^\n.;]*", cleaned, re.I)
    if education_match:
        education = education_match.group(0).strip()[:255]

    return JdParseResponse(
        title=title,
        department=department,
        location="Remote" if job_type == "remote" else "",
        job_type=job_type,
        description=cleaned,
        required_skills=required_skills,
        experience_min=experience_min,
        experience_max=experience_max,
        education=education,
        salary_min=salary_min,
        salary_max=salary_max,
        suggested_competencies=[_COMPETENCY_IDS[term] for term in detected_terms if term in _COMPETENCY_IDS],
    )


def parse_job_document(content: bytes, filename: str | None, content_type: str | None) -> JdParseResponse:
    return parse_job_description(_extract_document_text(content, filename, content_type))
