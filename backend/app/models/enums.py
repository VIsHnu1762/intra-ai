"""Domain enums mirroring the database schema."""

from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    RECRUITER = "recruiter"
    CANDIDATE = "candidate"


class JobStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"
    ARCHIVED = "archived"


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    PARSING = "parsing"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    INVITED = "invited"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class InterviewRoundType(StrEnum):
    INTRODUCTION = "introduction"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    HR_CULTURE = "hr_culture"


class QuestionType(StrEnum):
    INTRODUCTION = "introduction"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    SITUATIONAL = "situational"
    HR = "hr"
    SALARY_NEGOTIATION = "salary_negotiation"


class DifficultyLevel(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class Recommendation(StrEnum):
    STRONG_HIRE = "strong_hire"
    HIRE = "hire"
    MAYBE = "maybe"
    NO_HIRE = "no_hire"


class ProctoringEventType(StrEnum):
    FACE_DETECTED = "face_detected"
    FACE_LOST = "face_lost"
    MULTIPLE_FACES = "multiple_faces"
    TAB_SWITCH = "tab_switch"
    AUDIO_ANOMALY = "audio_anomaly"


class ActionType(StrEnum):
    ASK_QUESTION = "ASK_QUESTION"
    SWITCH_AGENT = "SWITCH_AGENT"
    COMPLETE = "COMPLETE"
