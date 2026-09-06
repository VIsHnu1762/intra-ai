"""Regression coverage for recruiter JD extraction."""

from app.services.jd_service import parse_job_description


def test_parse_job_description_uses_role_heading_in_branded_document() -> None:
    result = parse_job_description(
        """INTRA AI
        Senior Full-Stack Engineer
        Build reliable web applications with Python, FastAPI, React, TypeScript,
        PostgreSQL, Docker, and system design.
        This is a remote role for 3-7 years of experience.
        Bachelor's degree preferred.
        """
    )

    assert result.title == "Senior Full-Stack Engineer"
    assert result.department == "Engineering"
    assert result.location == "Remote"
    assert result.job_type == "remote"
    assert {"Python", "FastAPI", "React", "TypeScript", "PostgreSQL", "Docker"}.issubset(
        set(result.required_skills)
    )
    assert "system_design" in result.suggested_competencies
    assert result.experience_min == 3
    assert result.experience_max == 7
    assert result.education and result.education.lower().startswith("bachelor")
