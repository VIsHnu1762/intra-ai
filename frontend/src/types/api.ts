/**
 * Intra AI — Backend API Contract Type Definitions
 *
 * Forensically reconciled with FastAPI backend schemas:
 * - backend/app/schemas/auth.py
 * - backend/app/schemas/jobs.py
 * - backend/app/schemas/candidates.py
 * - backend/app/schemas/applications.py
 * - backend/app/schemas/interviews.py
 * - backend/app/schemas/reports.py
 */

import type {
  UserRole,
  JobStatus,
  JobType,
  InterviewRoundConfig,
  ApplicationStatus,
  Recommendation,
  ParsedResume,
  ProctoringReport,
  RoundAssessment,
} from "./index";

// ─── Generic & Pagination Envelopes ──────────────────────────────────────────

export interface PaginatedList<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface ApiErrorDetail {
  loc?: (string | number)[];
  msg: string;
  type?: string;
}

export interface ApiErrorResponse {
  detail?: string | ApiErrorDetail[];
  message?: string;
  error?: string;
}

// ─── Authentication Contracts ────────────────────────────────────────────────

/**
 * EXISTING CONTRACT: POST /api/v1/auth/login
 * Verified from backend/app/schemas/auth.py:LoginRequest
 */
export interface LoginCredentials {
  email: string;
  password: string; // min_length=8
}

/**
 * EXISTING CONTRACT: POST /api/v1/auth/signup
 * Verified from backend/app/schemas/auth.py:SignupRequest
 */
export interface SignupPayload {
  email: string;
  password: string; // min_length=8
  name: string;
  role?: UserRole; // defaults to "candidate"
}

/**
 * EXISTING CONTRACT: Return type of POST /api/v1/auth/login, /signup, /refresh
 * Verified from backend/app/schemas/auth.py:UserResponse
 */
export interface AuthUserResponse {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  avatar_url: string | null;
  created_at: string;
}

/**
 * EXISTING CONTRACT: Return type of POST /api/v1/auth/login, /signup, /refresh
 * Verified from backend/app/schemas/auth.py:TokenResponse
 */
export interface AuthTokenResponse {
  access_token: string;
  token_type: string; // "bearer"
  user: AuthUserResponse;
}

/**
 * MISSING CONTRACT: GET /api/v1/auth/me
 * NOTE: The FastAPI backend currently DOES NOT expose GET /api/v1/auth/me.
 * It provides POST /api/v1/auth/refresh which returns a fresh TokenResponse
 * for the Bearer-authenticated user. The frontend session manages user profile
 * state via TokenResponse.user and proactive refresh.
 */

// ─── Jobs Contracts ──────────────────────────────────────────────────────────

/**
 * EXISTING CONTRACT: GET /api/v1/jobs/public/{id} & admin responses
 * Verified from backend/app/schemas/jobs.py:JobResponse
 */
export interface BackendJobResponse {
  id: string;
  title: string;
  department: string;
  location: string;
  job_type: JobType | string;
  description: string;
  required_skills: string[];
  experience_min: number;
  experience_max: number;
  salary_min: number | null;
  salary_max: number | null;
  education?: string | null;
  eligibility_threshold?: number;
  status: JobStatus;
  applications_count: number;
  interview_rounds: InterviewRoundConfig[];
  created_at: string;
  updated_at: string;
}

/**
 * EXISTING CONTRACT: GET /api/v1/jobs/public and GET /api/v1/jobs
 * Verified from backend/app/schemas/jobs.py:JobListResponse
 */
export interface BackendJobListResponse {
  jobs: BackendJobResponse[];
  total: number;
  page: number;
  per_page: number;
}

/**
 * EXISTING CONTRACT: POST /api/v1/jobs
 * Verified from backend/app/schemas/jobs.py:JobCreate
 */
export interface BackendJobCreatePayload {
  title: string;
  department: string;
  location: string;
  job_type: JobType;
  description: string;
  required_skills: string[];
  experience_min: number;
  experience_max: number;
  salary_min?: number | null;
  salary_max?: number | null;
  education?: string | null;
  eligibility_threshold?: number;
  interview_rounds: InterviewRoundConfig[];
}

export type BackendJobUpdatePayload = Partial<BackendJobCreatePayload>;

/**
 * CONTRACT: POST /api/v1/jobs/parse-jd
 * Verified from backend/app/schemas/jobs.py:JdParseResponse
 */
export interface JdParseResponse {
  title: string;
  department: string;
  location: string;
  job_type: JobType | string;
  description: string;
  required_skills: string[];
  experience_min: number | null;
  experience_max: number | null;
  education?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  suggested_competencies: string[];
}

export interface JdTextParsePayload {
  text: string;
}


// ─── Candidate Contracts ─────────────────────────────────────────────────────

/**
 * EXISTING CONTRACT: GET /api/v1/candidates/{id}
 * Verified from backend/app/schemas/candidates.py:CandidateResponse
 */
export interface BackendCandidateResponse {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  location?: string | null;
  resume_url: string | null;
  parsed_resume: ParsedResume | null;
  applications?: any[];
  created_at: string;
}

/**
 * EXISTING CONTRACT: GET /api/v1/candidates
 * Returns {"candidates": CandidateResponse[], "total": number}
 */
export interface BackendCandidateListResponse {
  candidates: BackendCandidateResponse[];
  total: number;
}

// ─── Application Contracts ───────────────────────────────────────────────────

/**
 * EXISTING CONTRACT: GET /api/v1/applications/{id}
 * Verified from backend/app/schemas/applications.py:ApplicationResponse
 */
export interface BackendApplicationResponse {
  id: string;
  job_id: string;
  candidate_id: string;
  status: ApplicationStatus;
  eligibility_score: number | null;
  created_at: string;
  candidate: BackendCandidateResponse | null;
  job: BackendJobResponse | null;
  jobs?: BackendJobResponse | null;
  current_role?: string | null;
  current_company?: string | null;
  years_experience?: number | null;
  expected_salary_min?: number | null;
  expected_salary_max?: number | null;
  linkedin_url?: string | null;
  resume_url?: string | null;
  interview_id?: string | null;
  scheduled_at?: string | null;
  meeting_mode?: "scheduled" | "instant" | string | null;
  instant_deadline?: string | null;
  instant_status?: string | null;
  room_token?: string | null;
}

/**
 * EXISTING CONTRACT: GET /api/v1/jobs/{job_id}/applications
 * Verified from backend/app/schemas/applications.py:ApplicationListResponse
 */
export interface BackendApplicationListResponse {
  applications: BackendApplicationResponse[];
  total: number;
}

// ─── Scheduling Contracts ───────────────────────────────────────────────────

/**
 * CONTRACT: GET /api/v1/jobs/{job_id}/slots
 * Verified from backend/app/schemas/interviews.py:InterviewSlotResponse
 */
export interface BackendInterviewSlotResponse {
  id: string;
  job_id: string;
  date: string;
  start_time: string;
  end_time: string;
  is_booked: boolean;
}

/**
 * CONTRACT: POST /api/v1/applications/{app_id}/schedule
 * Verified from backend/app/schemas/interviews.py:ScheduleInterviewRequest
 */
export interface BackendScheduleInterviewRequest {
  slot_id: string;
  template_id?: string;
}

/**
 * CONTRACT: GET /api/v1/interviews/{interview_id} and POST /api/v1/applications/{app_id}/schedule
 * Verified from backend/app/schemas/interviews.py:ScheduledInterviewResponse
 */
export interface BackendScheduledInterviewResponse {
  id: string;
  application_id: string;
  scheduled_at: string;
  duration_minutes: number;
  room_token: string | null;
  status: string;
  meeting_mode?: "scheduled" | "instant" | string;
  response_deadline?: string | null;
  candidate?: BackendCandidateResponse | null;
  job?: BackendJobResponse | null;
}

export interface BackendInterviewListResponse {
  interviews: BackendScheduledInterviewResponse[];
  total: number;
}

// ─── Interview & Real-Time Voice Contracts ────────────────────────────────────

/**
 * EXISTING CONTRACT: GET /api/v1/interviews/{interview_id}/agora-token
 * Verified from backend/app/routes/interviews.py:get_agora_rtc_token
 * PRESERVED EXACTLY: Never exposes AGORA_APP_CERTIFICATE.
 */
export interface BackendAgoraTokenResponse {
  app_id: string;
  channel_name: string;
  token: string;
  uid: number;
  role: number;
  expires_in: number;
}

/**
 * EXISTING CONTRACT: GET /api/v1/interviews/{interview_id}/agora-agent-config
 * Verified from backend/app/routes/interviews.py:get_agora_agent_config
 */
export interface BackendAgoraAgentConfigResponse {
  app_id: string;
  channel_name: string;
  agent_rtc_uid: number;
  agent_token: string;
  expires_in: number;
  agora_payload: Record<string, unknown>;
}

export interface BackendCreateSlotRequest {
  date: string;
  start_time: string;
  end_time: string;
}

// ─── Assessment Report Contracts ─────────────────────────────────────────────

/**
 * EXISTING CONTRACT: GET /api/v1/interviews/{interview_id}/report
 * Verified from backend/app/schemas/reports.py:ReportResponse
 */
export interface BackendReportRoundAssessment extends Omit<RoundAssessment, "round_type"> {
  round_type: string;
  round_id?: string | null;
  round_name?: string | null;
  agent_ids?: string[];
  configured_agent_ids?: string[];
  identity_resolution?: string | null;
  evidence_ids?: string[];
}

export interface BackendReportAnalysis {
  overall_summary?: string;
  round_assessments?: BackendReportRoundAssessment[];
  competency_findings?: { competency_id: string; score: number | null; evidence_ids: string[]; observations: string[]; agent_ids: string[]; round_ids: string[] }[];
  evidence?: { id: string; signal: string; score: number | null; competency: string; answer_id?: string | null; round_id: string; source_agent_id?: string | null; timestamp?: string | null }[];
  answers?: { answer_id: string; question_text?: string; transcript?: string; answer_text?: string; agent_id?: string | null; round_id?: string | null }[];
  handoffs?: { from_agent_id?: string; to_agent_id?: string; source_agent_id?: string; target_agent_id?: string; round_id?: string; status?: string; timestamp?: string }[];
  transcripts?: { id: string; speaker: string; agent_id?: string | null; text: string; timestamp?: string | null; sequence?: number }[];
  coverage?: {
    configured_rounds?: { round_id: string; round_type?: string; round_name?: string; configured_agent_ids?: string[] }[];
    unobserved_rounds?: { round_id: string; round_type?: string; round_name?: string; configured_agent_ids?: string[] }[];
    observed_agent_ids?: string[];
    warnings?: string[];
  };
  counts?: { evidence?: number; scored_evidence?: number; answers?: number; evaluated_answers?: number; questions?: number; rounds?: number; handoffs?: number };
  narrative_evidence?: { strengths?: { text: string; evidence_ids: string[] }[]; improvements?: { text: string; evidence_ids: string[] }[] };
}

export interface BackendReportResponse {
  id: string;
  interview_id: string;
  round_assessments: BackendReportRoundAssessment[];
  overall_score: number;
  recommendation: Recommendation;
  strengths: string[];
  improvements: string[];
  salary_recommendation?: {
    min: number;
    max: number;
    justification: string;
  } | null;
  candidate_rating?: number | null;
  candidate_feedback?: string[] | null;
  analysis?: BackendReportAnalysis | null;
  pdf_url: string | null;
  proctoring_summary: ProctoringReport | null;
  candidate?: {
    id?: string;
    name?: string;
    email?: string;
    [key: string]: unknown;
  } | null;
  job?: {
    id?: string;
    title?: string;
    [key: string]: unknown;
  } | null;
  created_at: string;
}

export type ReportGenerationState = "not_completed" | "not_started" | "generating" | "ready" | "failed";

export interface BackendReportStatusResponse {
  interview_id: string;
  status: ReportGenerationState;
  report_id?: string | null;
  error_code?: string | null;
  message?: string | null;
  retryable: boolean;
}

/** Candidate-only projection; detailed evaluation fields are intentionally absent. */
export interface BackendCandidatePerformanceResponse {
  interview_id: string;
  status: ReportGenerationState;
  rating?: number | null;
  feedback?: string[] | null;
  created_at?: string | null;
  message?: string | null;
}

export interface BackendReportListResponse {
  reports: BackendReportResponse[];
  total: number;
}
