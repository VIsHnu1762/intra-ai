// ─── Users ────────────────────────────────────────────────────────────────────

export type UserRole = "admin" | "recruiter" | "candidate";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  avatar_url: string | null;
  created_at: string;
}

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export type JobType = "remote" | "hybrid" | "onsite";
export type JobStatus = "draft" | "published" | "closed" | "archived";
export type InterviewRoundType =
  | "introduction"
  | "technical"
  | "behavioral"
  | "hr_culture";

export interface InterviewRoundConfig {
  id?: string;
  type: InterviewRoundType;
  duration_minutes: number;
  focus_areas: string[];
  enabled: boolean;
  order_index?: number;
  agent_ids?: string[];
  agent_id?: "alex" | "jordan" | string;
}


export interface Job {
  id: string;
  title: string;
  department: string;
  location: string;
  type?: JobType;
  job_type?: JobType | string;
  description: string;
  required_skills: string[];
  experience_min: number;
  experience_max: number;
  salary_min: number | null;
  salary_max: number | null;
  status: JobStatus;
  created_at: string;
  updated_at?: string;
  applications_count: number;
  interview_rounds: InterviewRoundConfig[];
}

// ─── Candidates & Resumes ─────────────────────────────────────────────────────

export interface WorkExperience {
  company: string;
  role: string;
  start_date: string;
  end_date: string | null;
  description: string | null;
  technologies?: string[];
  location?: string | null;
}

export interface Education {
  institution: string;
  degree: string;
  field: string;
  year: number | string | null;
  details?: string | null;
}

export interface Project {
  name: string;
  description: string | null;
  technologies: string[];
  url?: string | null;
}

export interface ParsedResume {
  summary?: string | null;
  skills: string[];
  experience: WorkExperience[];
  education: Education[];
  certifications: string[];
  projects: Project[];
  achievements?: string[];
  location?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  raw_text?: string | null;
}

export interface Candidate {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  location?: string | null;
  resume_url: string | null;
  parsed_resume: ParsedResume | null;
  applications?: Application[];
  created_at: string;
}

// ─── Applications ─────────────────────────────────────────────────────────────

export type ApplicationStatus =
  | "applied"
  | "parsing"
  | "shortlisted"
  | "rejected"
  | "invited"
  | "scheduled"
  | "in_progress"
  | "completed"
  | "no_show";

export interface Application {
  id: string;
  job_id: string;
  candidate_id: string;
  status: ApplicationStatus;
  eligibility_score: number | null;
  created_at: string;
  candidate?: Candidate;
  job?: Job;
}

// ─── Interviews ───────────────────────────────────────────────────────────────

export type InterviewStatus =
  | "scheduled"
  | "in_progress"
  | "completed"
  | "cancelled";

export interface ScheduledInterview {
  id: string;
  application_id: string;
  scheduled_at: string;
  duration_minutes: number;
  room_token: string;
  status: InterviewStatus;
  candidate?: Candidate;
  job?: Job;
}

export type QuestionDifficulty = "easy" | "medium" | "hard" | "expert";

export interface InterviewQuestion {
  id: string;
  interview_id: string;
  round_type: InterviewRoundType;
  text: string;
  topic: string;
  difficulty: QuestionDifficulty;
  order: number;
}

export interface CandidateAnswer {
  id: string;
  question_id: string;
  transcript: string;
  duration_seconds: number;
}

// ─── Evaluation & Reports ─────────────────────────────────────────────────────

export interface Evaluation {
  id: string;
  answer_id: string;
  relevance: number;
  depth: number;
  accuracy: number;
  communication: number;
  confidence: number;
  overall: number;
  feedback: string;
}

export interface RoundAssessment {
  round_type: InterviewRoundType;
  score: number;
  observations: string[];
  strengths: string[];
  weaknesses: string[];
}

export type Recommendation = "strong_hire" | "hire" | "maybe" | "no_hire";

export interface SalaryRecommendation {
  min: number;
  max: number;
  justification: string;
}

export interface Report {
  id: string;
  interview_id: string;
  round_assessments: RoundAssessment[];
  overall_score: number;
  recommendation: Recommendation;
  strengths: string[];
  improvements: string[];
  salary_recommendation: SalaryRecommendation;
  pdf_url: string | null;
  created_at: string;
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

export interface DashboardStats {
  total_jobs: number;
  active_jobs: number;
  total_candidates: number;
  total_interviews: number;
  interviews_this_week: number;
  avg_score: number;
  pass_rate: number;
}

// ─── Scheduling ───────────────────────────────────────────────────────────────

export interface InterviewSlot {
  id: string;
  job_id: string;
  date: string;
  start_time: string;
  end_time: string;
  is_booked: boolean;
}

// ─── Proctoring ───────────────────────────────────────────────────────────────

export type ProctoringEventType =
  | "face_detected"
  | "face_lost"
  | "multiple_faces"
  | "tab_switch"
  | "audio_anomaly";

export interface ProctoringEvent {
  type: ProctoringEventType;
  timestamp: string;
  details?: string | null;
}

export interface ProctoringReport {
  face_presence_pct: number;
  tab_switches: number;
  integrity_score: number;
  events: ProctoringEvent[];
}

// ─── Notifications ────────────────────────────────────────────────────────────

export type NotificationType =
  | "application_received"
  | "shortlisted"
  | "rejected"
  | "interview_scheduled"
  | "reminder_24h"
  | "reminder_1h"
  | "report_ready";

export type NotificationStatus = "pending" | "sent" | "failed";

export interface Notification {
  id: string;
  type: NotificationType;
  recipient: string;
  subject: string;
  status: NotificationStatus;
  sent_at: string | null;
}

// ─── Re-export Intra AI M2 Domain Contracts ──────────────────────────────────
export * from "./intra-ai";
export * from "./api";
