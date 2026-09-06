-- Intra AI Database Schema & Initial Seed Data

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Roles & Permissions for PostgREST / Supabase Client ──────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
        CREATE ROLE service_role NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD 'postgres';
    END IF;
END
$$;

GRANT anon, authenticated, service_role TO authenticator;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role, authenticator, postgres;

-- ── Enums (Idempotent) ──────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('admin', 'recruiter', 'candidate');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
        CREATE TYPE job_status AS ENUM ('draft', 'published', 'closed', 'archived');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'application_status') THEN
        CREATE TYPE application_status AS ENUM ('applied', 'parsing', 'shortlisted', 'rejected', 'invited', 'scheduled', 'in_progress', 'completed', 'no_show');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'interview_round_type') THEN
        CREATE TYPE interview_round_type AS ENUM ('introduction', 'technical', 'behavioral', 'hr_culture');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'question_type') THEN
        CREATE TYPE question_type AS ENUM ('introduction', 'technical', 'behavioral', 'situational', 'hr', 'salary_negotiation');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'difficulty_level') THEN
        CREATE TYPE difficulty_level AS ENUM ('easy', 'medium', 'hard', 'expert');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'recommendation') THEN
        CREATE TYPE recommendation AS ENUM ('strong_hire', 'hire', 'maybe', 'no_hire');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'proctoring_event_type') THEN
        CREATE TYPE proctoring_event_type AS ENUM ('face_detected', 'face_lost', 'multiple_faces', 'tab_switch', 'audio_anomaly');
    END IF;
END
$$;

-- ── Tables ──────────────────────────────────────────────────────

-- Tenants
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'candidate',
    avatar_url TEXT,
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Jobs
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    location TEXT NOT NULL,
    job_type TEXT NOT NULL DEFAULT 'remote',
    description TEXT NOT NULL,
    required_skills TEXT[] DEFAULT '{}',
    experience_min INTEGER NOT NULL DEFAULT 0,
    experience_max INTEGER NOT NULL DEFAULT 0,
    salary_min NUMERIC,
    salary_max NUMERIC,
    education TEXT,
    eligibility_threshold NUMERIC NOT NULL DEFAULT 60.0,
    status TEXT NOT NULL DEFAULT 'draft',
    applications_count INTEGER NOT NULL DEFAULT 0,
    created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Job Rounds
CREATE TABLE IF NOT EXISTS job_rounds (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL DEFAULT 15,
    focus_areas TEXT[] DEFAULT '{}',
    agent_ids TEXT[] DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    order_index INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Backward-compatible migration for databases initialized before multi-agent
-- round assignments were added.
ALTER TABLE job_rounds ADD COLUMN IF NOT EXISTS agent_ids TEXT[] DEFAULT '{}';

-- Candidates
CREATE TABLE IF NOT EXISTS candidates (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    resume_url TEXT,
    tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Applications
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'applied',
    eligibility_score NUMERIC,
    years_experience INTEGER NOT NULL DEFAULT 0,
    "current_role" TEXT,
    current_company TEXT,
    expected_salary_min NUMERIC,
    expected_salary_max NUMERIC,
    linkedin_url TEXT,
    resume_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Parsed Resumes
CREATE TABLE IF NOT EXISTS parsed_resumes (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    skills JSONB DEFAULT '[]'::jsonb,
    experience JSONB DEFAULT '[]'::jsonb,
    education JSONB DEFAULT '[]'::jsonb,
    certifications JSONB DEFAULT '[]'::jsonb,
    projects JSONB DEFAULT '[]'::jsonb,
    raw_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Eligibility Scores
CREATE TABLE IF NOT EXISTS eligibility_scores (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    application_id TEXT UNIQUE NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    skills_overlap NUMERIC NOT NULL DEFAULT 0,
    experience_match NUMERIC NOT NULL DEFAULT 0,
    education_score NUMERIC NOT NULL DEFAULT 0,
    other_score NUMERIC NOT NULL DEFAULT 0,
    overall_score NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Interview Slots
CREATE TABLE IF NOT EXISTS interview_slots (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    is_booked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Scheduled Interviews
CREATE TABLE IF NOT EXISTS scheduled_interviews (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    application_id TEXT NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    slot_id TEXT REFERENCES interview_slots(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    room_token TEXT,
    duration_minutes INTEGER NOT NULL DEFAULT 60,
    scheduled_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Interview Questions
CREATE TABLE IF NOT EXISTS interview_questions (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    interview_id TEXT NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    round_type TEXT NOT NULL,
    text TEXT NOT NULL,
    topic TEXT NOT NULL,
    difficulty TEXT NOT NULL DEFAULT 'medium',
    "order" INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Candidate Answers
CREATE TABLE IF NOT EXISTS candidate_answers (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    interview_id TEXT NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES interview_questions(id) ON DELETE CASCADE,
    transcript TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Evaluations
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    interview_id TEXT NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    answer_id TEXT NOT NULL REFERENCES candidate_answers(id) ON DELETE CASCADE,
    relevance NUMERIC NOT NULL DEFAULT 0,
    depth NUMERIC NOT NULL DEFAULT 0,
    accuracy NUMERIC NOT NULL DEFAULT 0,
    communication NUMERIC NOT NULL DEFAULT 0,
    confidence NUMERIC NOT NULL DEFAULT 0,
    overall NUMERIC NOT NULL DEFAULT 0,
    feedback TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Round Assessments
CREATE TABLE IF NOT EXISTS round_assessments (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    interview_id TEXT NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    round_type TEXT NOT NULL,
    score NUMERIC NOT NULL DEFAULT 0,
    observations TEXT[] DEFAULT '{}',
    strengths TEXT[] DEFAULT '{}',
    weaknesses TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Skill Assessments
CREATE TABLE IF NOT EXISTS skill_assessments (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    interview_id TEXT NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    score NUMERIC NOT NULL DEFAULT 0,
    level TEXT NOT NULL DEFAULT 'intermediate',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Reports
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    interview_id TEXT UNIQUE NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    round_assessments JSONB DEFAULT '[]'::jsonb,
    overall_score NUMERIC NOT NULL DEFAULT 0,
    recommendation TEXT NOT NULL DEFAULT 'no_hire',
    strengths JSONB DEFAULT '[]'::jsonb,
    improvements JSONB DEFAULT '[]'::jsonb,
    salary_recommendation JSONB,
    proctoring_summary JSONB,
    pdf_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Proctoring Events
CREATE TABLE IF NOT EXISTS proctoring_events (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    interview_id TEXT NOT NULL REFERENCES scheduled_interviews(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    type TEXT NOT NULL,
    recipient TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    payload JSONB,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- AI Decision Logs
CREATE TABLE IF NOT EXISTS ai_decision_logs (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    model TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost NUMERIC DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    decision JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ─────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_by ON jobs(created_by);
CREATE INDEX IF NOT EXISTS idx_job_rounds_job_id ON job_rounds(job_id);
CREATE INDEX IF NOT EXISTS idx_candidates_email ON candidates(email);
CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_candidate_id ON applications(candidate_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_job_candidate
    ON applications(job_id, candidate_id);
CREATE INDEX IF NOT EXISTS idx_interview_slots_job_id ON interview_slots(job_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_app_id ON scheduled_interviews(application_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_job_id ON scheduled_interviews(job_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_interviews_status ON scheduled_interviews(status);
CREATE INDEX IF NOT EXISTS idx_questions_interview_id ON interview_questions(interview_id);
CREATE INDEX IF NOT EXISTS idx_answers_interview_id ON candidate_answers(interview_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_interview_id ON evaluations(interview_id);
CREATE INDEX IF NOT EXISTS idx_proctoring_interview_id ON proctoring_events(interview_id);

-- ── Grants ──────────────────────────────────────────────────────
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated, service_role, authenticator, postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role, authenticator, postgres;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO anon, authenticated, service_role, authenticator, postgres;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role, authenticator, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role, authenticator, postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON ROUTINES TO anon, authenticated, service_role, authenticator, postgres;

-- ── Initial Seed Data ───────────────────────────────────────────

-- 1. Default Tenant
INSERT INTO tenants (id, name, slug)
VALUES ('00000000-0000-0000-0000-000000000001', 'Intra AI HQ', 'intra-ai')
ON CONFLICT (slug) DO NOTHING;

-- 2. Seed Users (password: Password123!)
INSERT INTO users (id, email, name, password_hash, role, tenant_id)
VALUES
  ('u-admin-01', 'admin@intra-ai.example', 'Super Admin', '$2b$12$fYd49h8LlXGCxcdcrIouz.Lq5oLFOtWXIi7lyxQjUgqnTRVJCl7mW', 'admin', '00000000-0000-0000-0000-000000000001'),
  ('u-recruiter-01', 'recruiter@intra-ai.example', 'Lead Recruiter', '$2b$12$fYd49h8LlXGCxcdcrIouz.Lq5oLFOtWXIi7lyxQjUgqnTRVJCl7mW', 'recruiter', '00000000-0000-0000-0000-000000000001'),
  ('u-candidate-01', 'candidate@intra-ai.example', 'Alex Rivera', '$2b$12$fYd49h8LlXGCxcdcrIouz.Lq5oLFOtWXIi7lyxQjUgqnTRVJCl7mW', 'candidate', '00000000-0000-0000-0000-000000000001')
ON CONFLICT (email) DO NOTHING;

-- 3. Seed Jobs
INSERT INTO jobs (id, title, department, location, job_type, description, required_skills, experience_min, experience_max, salary_min, salary_max, status, created_by, tenant_id)
VALUES
  (
    'job-001',
    'Senior Full-Stack Engineer',
    'Engineering',
    'San Francisco, CA / Remote',
    'remote',
    'We are seeking an experienced Senior Full-Stack Engineer to lead the development of high-performance web applications. You will architect scalable frontend and backend systems, mentor engineers, and drive technical excellence across the stack.',
    ARRAY['React', 'TypeScript', 'Node.js', 'Python', 'FastAPI', 'PostgreSQL', 'Docker'],
    5,
    10,
    140000,
    185000,
    'published',
    'u-recruiter-01',
    '00000000-0000-0000-0000-000000000001'
  ),
  (
    'job-002',
    'AI / Machine Learning Engineer',
    'AI & Data',
    'New York, NY / Remote',
    'remote',
    'Join our AI research and deployment team to build state-of-the-art voice and LLM agent pipelines. You will work on real-time speech processing, agentic reasoning loops, and multimodal models.',
    ARRAY['Python', 'PyTorch', 'OpenAI API', 'LangChain', 'FastAPI', 'Vector Databases', 'WebSockets'],
    3,
    8,
    160000,
    210000,
    'published',
    'u-recruiter-01',
    '00000000-0000-0000-0000-000000000001'
  ),
  (
    'job-003',
    'Product Designer (UI/UX)',
    'Design',
    'Remote',
    'remote',
    'Looking for a passionate Product Designer to design intuitive, world-class user experiences for our AI interview platform. You will craft interactive prototypes, design systems, and delightful interfaces.',
    ARRAY['Figma', 'UI/UX Design', 'Design Systems', 'User Research', 'Prototyping'],
    3,
    7,
    110000,
    150000,
    'published',
    'u-recruiter-01',
    '00000000-0000-0000-0000-000000000001'
  )
ON CONFLICT (id) DO NOTHING;

-- 4. Job Rounds
INSERT INTO job_rounds (id, job_id, type, duration_minutes, focus_areas, enabled, order_index)
VALUES
  ('jr-001-1', 'job-001', 'introduction', 7, ARRAY['Background', 'Career Goals', 'System Architecture Overview'], TRUE, 1),
  ('jr-001-2', 'job-001', 'technical', 20, ARRAY['React/TypeScript', 'FastAPI Architecture', 'Database Optimization'], TRUE, 2),
  ('jr-001-3', 'job-001', 'behavioral', 15, ARRAY['STAR Method', 'Conflict Resolution', 'Mentorship Experience'], TRUE, 3),
  ('jr-001-4', 'job-001', 'hr_culture', 10, ARRAY['Work Style', 'Compensation', 'Availability'], TRUE, 4),
  ('jr-002-1', 'job-002', 'introduction', 5, ARRAY['Background', 'AI Research Interests'], TRUE, 1),
  ('jr-002-2', 'job-002', 'technical', 25, ARRAY['LLM Architectures', 'Realtime Voice Pipeline', 'Vector Search'], TRUE, 2),
  ('jr-002-3', 'job-002', 'behavioral', 15, ARRAY['Handling Ambiguity', 'Team Collaboration'], TRUE, 3),
  ('jr-002-4', 'job-002', 'hr_culture', 10, ARRAY['Culture Fit', 'Compensation'], TRUE, 4)
ON CONFLICT (id) DO NOTHING;

-- 5. Seed Interview Slots (for scheduling)
INSERT INTO interview_slots (id, job_id, date, start_time, end_time, is_booked)
VALUES
  ('slot-001', 'job-001', '2026-09-10', '10:00', '11:00', FALSE),
  ('slot-002', 'job-001', '2026-09-10', '14:00', '15:00', FALSE),
  ('slot-003', 'job-001', '2026-09-11', '11:00', '12:00', FALSE),
  ('slot-004', 'job-001', '2026-09-11', '16:00', '17:00', FALSE),
  ('slot-005', 'job-002', '2026-09-12', '10:00', '11:00', FALSE),
  ('slot-006', 'job-002', '2026-09-12', '15:00', '16:00', FALSE)
ON CONFLICT (id) DO NOTHING;

-- 6. Seed Candidate & Application
INSERT INTO candidates (id, name, email, phone, resume_url, tenant_id)
VALUES
  ('cand-001', 'Alex Rivera', 'candidate@intra-ai.example', '+1 (555) 234-5678', 'https://example.com/resumes/alex-rivera.pdf', '00000000-0000-0000-0000-000000000001')
ON CONFLICT (id) DO NOTHING;

INSERT INTO applications (id, job_id, candidate_id, status, eligibility_score, years_experience, "current_role", current_company, expected_salary_min, expected_salary_max)
VALUES
  ('app-001', 'job-001', 'cand-001', 'shortlisted', 88.5, 6, 'Senior Software Engineer', 'TechCorp Labs', 150000, 175000)
ON CONFLICT (id) DO NOTHING;

INSERT INTO parsed_resumes (id, application_id, candidate_id, skills, experience, education, certifications, projects)
VALUES
  (
    'pr-001',
    'app-001',
    'cand-001',
    '["React", "TypeScript", "Node.js", "Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "GraphQL"]'::jsonb,
    '[{"company": "TechCorp Labs", "role": "Senior Software Engineer", "start_date": "2021-03", "end_date": null, "description": "Led fullstack engineering of cloud SaaS platform serving 500k+ users."}]'::jsonb,
    '[{"institution": "UC Berkeley", "degree": "B.S. Computer Science", "field": "Computer Science", "year": 2020}]'::jsonb,
    '["AWS Certified Solutions Architect", "Certified Kubernetes Administrator"]'::jsonb,
    '[{"name": "Realtime AI Voice Agent", "description": "Built low-latency voice streaming interface with OpenAI Realtime API.", "technologies": ["React", "FastAPI", "WebSockets"]}]'::jsonb
  )
ON CONFLICT (id) DO NOTHING;

INSERT INTO eligibility_scores (id, application_id, skills_overlap, experience_match, education_score, other_score, overall_score)
VALUES
  ('es-001', 'app-001', 92.0, 100.0, 100.0, 85.0, 88.5)
ON CONFLICT (id) DO NOTHING;
