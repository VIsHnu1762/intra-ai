"""Async OpenAI client wrapper for resume parsing, question generation, evaluation, and reports."""

from __future__ import annotations

import json
from typing import Any

import structlog
from openai import AsyncOpenAI

from app.core.config import settings

logger = structlog.stdlib.get_logger("intra_ai.openai")

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


# ── Resume Parsing ───────────────────────────────────────────

_RESUME_PARSE_PROMPT = """You are an expert resume parser. Extract structured information from the following resume text.

Return a valid JSON object with these exact keys:
- skills: list of technical and soft skills (strings)
- experience: list of objects with keys: company, role, start_date, end_date, description
- education: list of objects with keys: institution, degree, field, year
- certifications: list of certification names (strings)
- projects: list of objects with keys: name, description, technologies (list of strings)

Be thorough. Extract ALL skills mentioned explicitly and implied by experience/projects.
If a field is not found, use an empty list or null for optional fields."""


async def parse_resume(text: str) -> dict[str, Any]:
    """Parse resume text into structured data using GPT-4o."""
    client = _get_client()

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _RESUME_PARSE_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)

    logger.info(
        "resume_parsed",
        model="gpt-4o",
        tokens=response.usage.total_tokens if response.usage else 0,
        skills_count=len(parsed.get("skills", [])),
    )
    return parsed


# ── Question Generation ─────────────────────────────────────

_QUESTION_GEN_PROMPT = """You are an expert interviewer. Generate interview questions based on the provided context.

Context includes:
- Job description and required skills
- Candidate's resume (parsed skills, experience)
- Interview round type: {round_type}
- Difficulty adjustment: {difficulty_note}

Generate exactly {count} questions. Each question should be a JSON object with:
- text: the question text
- topic: the skill or topic being assessed
- difficulty: one of "easy", "medium", "hard", "expert"
- question_type: one of "introduction", "technical", "behavioral", "situational", "hr", "salary_negotiation"

Return a JSON object with key "questions" containing the list.
Make questions specific to the candidate's background and the job requirements.
For technical rounds, focus on the required skills from the JD.
For behavioral rounds, use STAR-method prompts."""


async def generate_questions(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate interview questions from resume + JD + round context."""
    client = _get_client()

    round_type = context.get("round_type", "technical")
    difficulty_note = context.get("difficulty_note", "Standard difficulty")
    count = context.get("count", 5)

    prompt = _QUESTION_GEN_PROMPT.format(
        round_type=round_type,
        difficulty_note=difficulty_note,
        count=count,
    )

    user_content = json.dumps(
        {
            "job_title": context.get("job_title", ""),
            "job_description": context.get("job_description", ""),
            "required_skills": context.get("required_skills", []),
            "candidate_skills": context.get("candidate_skills", []),
            "candidate_experience": context.get("candidate_experience", []),
            "previous_scores": context.get("previous_scores", []),
        },
        default=str,
    )

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )

    content = response.choices[0].message.content or '{"questions": []}'
    result = json.loads(content)

    logger.info(
        "questions_generated",
        model="gpt-4o",
        round_type=round_type,
        count=len(result.get("questions", [])),
        tokens=response.usage.total_tokens if response.usage else 0,
    )
    return result.get("questions", [])


# ── Answer Evaluation ────────────────────────────────────────

_EVALUATION_PROMPT = """You are an expert interview evaluator. Score the candidate's answer on 5 dimensions, each from 0.0 to 10.0.

Question: {question}
Expected topic: {topic}
Job role context: {job_context}

Scoring dimensions:
1. relevance - How relevant is the answer to the question asked?
2. depth - How deep and thorough is the analysis/response?
3. accuracy - How technically accurate is the answer?
4. communication - How clearly and articulately is the answer delivered?
5. confidence - How confident and assured does the candidate sound?

Return a JSON object with:
- relevance: float (0-10)
- depth: float (0-10)
- accuracy: float (0-10)
- communication: float (0-10)
- confidence: float (0-10)
- overall: float (0-10, weighted average)
- feedback: string (2-3 sentences of constructive feedback)"""


async def evaluate_answer(
    question: str,
    answer: str,
    rubric: dict[str, Any],
) -> dict[str, Any]:
    """Score an answer on 5 dimensions using LLM."""
    client = _get_client()

    prompt = _EVALUATION_PROMPT.format(
        question=question,
        topic=rubric.get("topic", "general"),
        job_context=rubric.get("job_context", ""),
    )

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Candidate's answer:\n\n{answer}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    content = response.choices[0].message.content or "{}"
    evaluation = json.loads(content)

    logger.info(
        "answer_evaluated",
        model="gpt-4o",
        overall=evaluation.get("overall"),
        tokens=response.usage.total_tokens if response.usage else 0,
    )
    return evaluation


# ── Report Summary ───────────────────────────────────────────

_REPORT_PROMPT = """You are an expert hiring consultant. Generate a comprehensive assessment summary.

Given the interview data (per-round scores, per-skill assessments, candidate background, job requirements),
produce a JSON object with:
- overall_summary: string (3-5 sentence executive summary)
- strengths: list of 3-5 specific strengths demonstrated
- improvements: list of 3-5 areas for improvement
- recommendation_justification: string (why this recommendation)
- salary_recommendation: object with min (float), max (float), justification (string)
- hiring_risk_notes: string (any concerns or risks)"""


async def generate_report_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Generate a narrative report summary from interview evaluation data."""
    client = _get_client()

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _REPORT_PROMPT},
            {"role": "user", "content": json.dumps(data, default=str)},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    content = response.choices[0].message.content or "{}"
    summary = json.loads(content)

    logger.info(
        "report_generated",
        model="gpt-4o",
        tokens=response.usage.total_tokens if response.usage else 0,
    )
    return summary
