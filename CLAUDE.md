# CLAUDE.md — Intra AI

> Last updated: 2026-03-14

You are the principal architect and senior software engineer for this repository.

## Project Identity

**Product Name:** Intra AI
**GitHub:** `VIsHnu1762/intra-ai`
**Type:** AI-powered interview automation + skill assessment SaaS
**MVP Goal:** Ship a complete hiring pipeline: candidate applies → resume parsed → eligibility checked → interview scheduled → AI conducts multi-round video+voice interview (Introduction → Technical → Behavioral → HR) → per-round assessment → final report with recommendation + salary guidance.
**Full Vision:** Enterprise-grade hiring intelligence platform with coding interviews, speech emotion scoring, advanced fraud detection, ATS integrations, white-label API, panel interviews, benchmark comparisons, and continuous learning. See `docs/PRD.md`.
**Target Customers:** Hiring platforms, universities, bootcamps, enterprises, staffing agencies.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14+, TypeScript, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| Database | Supabase (PostgreSQL + pgvector) |
| Cache/Queue | Redis |
| Video/Audio | WebRTC (Daily.co or LiveKit SDK) |
| AI Conversation | OpenAI Realtime API (Speech-to-Speech) — primary interview voice |
| Speech-to-Text | Deepgram (streaming fallback) or OpenAI Whisper |
| AI Evaluation | OpenAI GPT-4o / Claude Sonnet — answer scoring, report generation |
| Resume Parsing | OpenAI GPT-4o (structured output from PDF) |
| AI Orchestration | LangGraph (multi-agent, typed state, supervisor) — post-MVP |
| Computer Vision | MediaPipe (face detection, presence — client-side) |
| Email | Resend or AWS SES — transactional emails |
| CDN | AWS CloudFront — static assets, resume downloads, report PDFs |
| File Storage | AWS S3 — resumes, reports, recordings |
| Auth | Supabase Auth + JWT, RBAC |
| Deployment | Docker, AWS (ECS Fargate, ALB, S3, CloudFront) |

**Cost Targets:** AI interview (30-60 min) < $0.50 | Resume parsing $0.02/resume | OpenAI Realtime ~$0.10-0.30/interview

---

## MVP Scope — What to Build NOW

### INCLUDE in MVP (Phase 1)

1. **Auth & RBAC** — Login/signup, role-based access (admin/recruiter/candidate), JWT via Supabase Auth
2. **Job Posting Management** — Create/edit/publish jobs with title, description, required skills, experience, salary range, interview round config
3. **Candidate Onboarding** — Public application form (name, email, phone, experience, expected salary) + resume upload (PDF/DOCX)
4. **Resume Parsing (AI)** — Extract structured data from resume: skills, experience, education, projects, certifications via GPT-4o
5. **Eligibility Engine** — Match resume against JD (skills overlap, experience, education) → auto-shortlist or reject with feedback
6. **Email Notifications** — Application received, shortlisted invite, rejection, interview confirmation, reminders (Resend/SES)
7. **Interview Scheduling** — Self-service: candidate picks from available slots, confirmation + calendar invite (ICS)
8. **Live AI Interview (Video + Voice)** — WebRTC room + OpenAI Realtime API (Speech-to-Speech) for natural voice conversation
9. **Multi-Round Interview Flow** — Introduction (5-7 min) → Technical (15-20 min) → Behavioral (10-15 min) → HR & Culture (5-10 min)
10. **Adaptive Question Generation** — Questions generated from resume + JD + previous answer scores; harder follow-ups for strong answers
11. **Real-Time Transcription** — Live STT of candidate answers (Deepgram streaming or OpenAI Whisper)
12. **Per-Answer Evaluation** — LLM scores each answer on rubric: relevance, depth, accuracy, communication, confidence (each 0-10)
13. **Face Presence Detection** — MediaPipe client-side: verify candidate present and alone throughout
14. **Assessment Report** — Per-round scores, per-skill aggregates, strengths/weaknesses, overall recommendation (Strong Hire → No Hire), salary recommendation, PDF export
15. **Admin Dashboard** — Job management, candidate pipeline view, interview calendar, report viewing, AI config
16. **Candidate Portal** — Application status tracking, interview scheduling, pre-interview system check, interview room, post-interview report

### EXCLUDE from MVP (Post-launch)

- Speech emotion / confidence scoring (prosody, tone analysis)
- Advanced fraud detection (tab switch, copy-paste, multiple faces, audio anomaly)
- Video recording & playback for reviewers
- Coding interview environment (live code editor + execution)
- Panel interview mode (multiple AI personas)
- Benchmark comparisons (candidate vs. cohort)
- ATS integrations (Greenhouse, Lever, Workday)
- White-label API / embeddable widget
- Multi-language support
- LangGraph multi-agent orchestration
- BigQuery / analytics data warehouse
- Continuous learning from recruiter feedback
- Bulk resume upload + batch processing
- Calendar integration (Google, Outlook sync)
- SMS notifications (Twilio)

---

## Key Docs (Read Before Coding)

- `docs/PRD.md` — Product requirements, user flows, milestones, pricing
- `docs/ARCHITECTURE.md` — Layers, data flow, key decisions
- `docs/API_SPEC.md` — Endpoints, schemas, error responses
- `docs/DB_SCHEMA.md` — Tables, indexes, RLS policies
- `docs/DEPLOYMENT.md` — Docker, AWS, CI/CD setup
- `ENGINEERING-CONTEXT.md` — Engineering patterns, target customers, pricing

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│   Candidate (applies,            Recruiter / Admin (creates     │
│   schedules, takes interview)    jobs, views reports, manages)  │
└──────────┬───────────────────────────────┬──────────────────────┘
           │                               │
           ▼                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              AWS CloudFront (CDN) — static assets, PDFs         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              AWS ALB / API Gateway                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Next.js App    │ │  FastAPI Backend │ │  WebRTC +        │
│  (SSR + SPA)    │ │  (REST + WS)    │ │  OpenAI Realtime │
│                 │ │                 │ │  (Speech-to-     │
│  Pages:         │ │  Services:      │ │   Speech)        │
│  - Job listings │ │  - Job          │ └─────────────────┘
│  - Apply form   │ │  - Resume Parse │
│  - Schedule     │ │  - Eligibility  │
│  - Interview    │ │  - Scheduling   │
│    room         │ │  - Interview    │
│  - Admin panel  │ │  - Evaluation   │
│  - Reports      │ │  - Report       │
└────────┬────────┘ │  - Proctoring   │
         │          │  - Notification  │
         │          └────────┬────────┘
         │                   │
         ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Supabase (PostgreSQL + pgvector + Auth + RLS + Realtime)       │
└─────────────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Redis           │ │  AWS S3          │ │  Resend / SES   │
│  (cache, queue,  │ │  (resumes, PDFs, │ │  (emails)       │
│   rate limit)    │ │   recordings)    │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

**Three interfaces, one app:**
- **Public routes** (`/jobs/*`): Job listings, application form
- **Admin routes** (`/admin/*`): Job management, candidate pipeline, reports, AI config
- **Candidate routes** (`/interview/*`): Schedule, system check, interview room, report
- Role-based access via middleware; shared component library

### Complete Pipeline Flow

```
APPLY                    PARSE                   ELIGIBLE?
Candidate fills  ──►  AI extracts skills  ──►  Match vs JD
form + resume         from resume (GPT-4o)     score >= threshold?
                                                    │
                                          ┌─────────┴─────────┐
                                         YES                  NO
                                          │                    │
                                    Send invite           Send rejection
                                    (schedule link)       (with feedback)
                                          │
                                     SCHEDULE
                                    Candidate picks
                                    time slot
                                          │
                                     INTERVIEW
                               ┌──────────┴──────────┐
                               │   WebRTC Room        │
                               │   + OpenAI Realtime  │
                               │   (Speech-to-Speech) │
                               └──────────┬──────────┘
                                          │
                    Round 1: Introduction (5-7 min)
                    Round 2: Technical (15-20 min)
                    Round 3: Behavioral (10-15 min)
                    Round 4: HR & Culture (5-10 min)
                                          │
                                      EVALUATE
                                 Per-answer scoring
                                 Per-round aggregation
                                 Per-skill assessment
                                          │
                                      REPORT
                                 Scores + recommendation
                                 + salary guidance + PDF
```

---

## Project Structure

### Backend (`/backend`)

```
backend/
  app/
    main.py                     # FastAPI app entry
    core/
      config.py                 # Settings via env vars (pydantic-settings)
      security.py               # Auth, JWT validation, RBAC
      middleware.py              # CORS, logging, tenant context
      exceptions.py             # Centralized error handling
    routes/
      auth.py                   # Login, signup, token refresh
      jobs.py                   # Job posting CRUD, publish/archive
      applications.py           # Apply, upload resume, list applications
      interviews.py             # CRUD, configure, start/end
      scheduling.py             # Available slots, book slot, reschedule
      questions.py              # Generate, list, adaptive follow-up
      evaluation.py             # Score answers, get rubric results
      transcription.py          # WebSocket for real-time STT
      reports.py                # Generate, view, download reports
      candidates.py             # Candidate management, pipeline view
      proctoring.py             # Face detection events, fraud flags
      admin.py                  # AI config, interview templates
      health.py                 # Health check endpoint
    services/
      job_service.py            # Job posting management
      resume_service.py         # AI resume parsing (GPT-4o structured output)
      eligibility_service.py    # Resume ↔ JD matching, scoring, auto-shortlist
      scheduling_service.py     # Slot management, booking, calendar ICS
      notification_service.py   # Email notifications (Resend/SES)
      interview_service.py      # Interview lifecycle management
      question_service.py       # LLM question generation + adaptive logic
      evaluation_service.py     # LLM answer scoring + rubric
      transcription_service.py  # Deepgram/Whisper streaming integration
      report_service.py         # Report generation + PDF export
      proctoring_service.py     # Face detection event processing
      video_service.py          # WebRTC room management (Daily.co / LiveKit)
      realtime_service.py       # OpenAI Realtime API (Speech-to-Speech) integration
    repositories/
      user_repo.py
      job_repo.py
      application_repo.py
      interview_repo.py
      scheduling_repo.py
      question_repo.py
      answer_repo.py
      evaluation_repo.py
      report_repo.py
      candidate_repo.py
      proctoring_repo.py
    models/                     # SQLAlchemy / Supabase models
    schemas/                    # Pydantic request/response schemas
    integrations/
      openai_client.py          # OpenAI API wrapper (chat + realtime)
      deepgram_client.py        # Deepgram streaming STT
      video_provider.py         # Daily.co / LiveKit API
      supabase_client.py        # Supabase client init
      redis_client.py           # Redis connection
      s3_client.py              # AWS S3 (resumes, PDFs)
      email_client.py           # Resend / AWS SES
    workers/
      resume_worker.py          # Async resume parsing
      report_worker.py          # Async report generation
      evaluation_worker.py      # Async batch evaluation
      notification_worker.py    # Async email delivery
    tests/
  requirements.txt
  Dockerfile
```

### Frontend (`/frontend`)

```
frontend/
  app/
    layout.tsx                  # Root layout
    page.tsx                    # Landing / redirect
    (auth)/
      login/page.tsx
      signup/page.tsx
    (public)/
      jobs/page.tsx                   # Public job listings
      jobs/[id]/page.tsx              # Job detail + apply button
      jobs/[id]/apply/page.tsx        # Application form + resume upload
      jobs/[id]/apply/success/page.tsx # Application submitted confirmation
    (admin)/
      dashboard/page.tsx              # Pipeline overview + stats
      jobs/page.tsx                   # Job posting management
      jobs/new/page.tsx               # Create new job posting
      jobs/[id]/page.tsx              # Job detail + applicants
      candidates/page.tsx             # Candidate pipeline view
      candidates/[id]/page.tsx        # Candidate detail + all interviews
      interviews/page.tsx             # Interview calendar view
      interviews/[id]/page.tsx        # Interview detail + report
      reports/page.tsx                # All reports
      settings/page.tsx               # AI config, templates, slots
    (candidate)/
      portal/page.tsx                 # Application status tracking
      schedule/[token]/page.tsx       # Self-service scheduling
      interview/[token]/prep/page.tsx  # Pre-interview system check
      interview/[token]/page.tsx       # Interview room (WebRTC + AI voice)
      interview/[token]/done/page.tsx  # Post-interview + report view
  components/
    ui/                         # Design system primitives (Button, Card, Input, etc.)
    layout/                     # Sidebar, Header, Footer
    interview/                  # VideoRoom, QuestionDisplay, Timer, TranscriptPanel
    evaluation/                 # ScoreCard, SkillRadar, StrengthWeakness
    proctoring/                 # FaceDetector, PresenceIndicator, FraudAlert
    reports/                    # ReportView, ReportPDF, SkillBreakdown
    admin/                      # InterviewForm, CandidateTable, ConfigPanel
  hooks/
    useWebRTC.ts                # Video room connection hook
    useTranscription.ts         # Real-time STT hook
    useFaceDetection.ts         # MediaPipe face detection hook
    useInterviewState.ts        # Interview flow state machine
    useAuth.ts                  # Auth state
    useTimer.ts                 # Interview timer
  lib/
    api.ts                      # API client (fetch wrapper)
    constants.ts
    utils.ts
    mediapipe.ts                # MediaPipe initialization
  services/
    auth.ts
    interview.ts
    evaluation.ts
    report.ts
  types/
    index.ts                    # Shared TypeScript types
  public/
  tailwind.config.ts
  next.config.ts
  tsconfig.json
  package.json
  Dockerfile
```

---

## Design System — "Euron" (Strict)

All UI must follow this system. No deviations.

### Color Palette

| Token | Value | Usage |
|-------|-------|-------|
| `primary` | `#0A66C2` | Buttons, links, active states, brand accent |
| `primary-hover` | `#004182` | Hover/active on primary elements |
| `bg` | `#F3F6F8` | Page background |
| `surface` | `#FFFFFF` | Cards, panels, modals |
| `border` | `#E5E7EB` | Card borders, dividers, input borders |
| `text-primary` | `#111827` | Headings, body text |
| `text-muted` | `#6B7280` | Secondary text, captions, placeholders |
| `success` | `#057642` | Success states, high scores |
| `warning` | `#B45309` | Warning states, medium scores |
| `error` | `#B91C1C` | Error states, low scores, fraud alerts |
| `input-border` | `#D1D5DB` | Default input borders |

Blue is the dominant color. All other colors used sparingly and functionally.

### Typography

- **Font:** Inter (import from Google Fonts)
- **Headings:** weight 600-700
- **Body:** weight 400-500

| Element | Size | Weight |
|---------|------|--------|
| Page title | 28-32px | 700 |
| Section header | 20-24px | 600 |
| Card title | 16-18px | 600 |
| Body text | 14-16px | 400 |
| Caption / meta | 12px | 400 |

Line height: 1.4-1.6 for all text.

### Cards

```css
background: #FFFFFF;
border: 1px solid #E5E7EB;
border-radius: 8px;
box-shadow: none; /* flat, stable, professional */
```

### Buttons

**Primary:** `bg: #0A66C2, color: #FFF, border-radius: 999px (pill), font-weight: 600`
**Secondary:** `bg: transparent, border: 1px solid #0A66C2, color: #0A66C2, pill`
**Tertiary:** Text only, muted gray.
**Danger:** `bg: #B91C1C, color: #FFF, pill` (for ending interviews, fraud actions)

### Forms & Inputs

- Height: 40-44px | Border: 1px solid #D1D5DB | Focus: border #0A66C2 + `ring-1 ring-blue-500/20`
- Labels above inputs | Placeholder in muted gray

### Icons & Motion

- Outline/stroke-based only (Lucide React or Heroicons outline)
- Hover transitions: 100-150ms ease | No bounce, no flashy animations
- Interview room: minimal UI, focus on video and questions

### Tailwind Config

```js
colors: {
  brand: { DEFAULT: '#0A66C2', hover: '#004182' },
  surface: '#FFFFFF',
  bg: '#F3F6F8',
  border: '#E5E7EB',
  'input-border': '#D1D5DB',
  'text-primary': '#111827',
  'text-muted': '#6B7280',
  success: '#057642',
  warning: '#B45309',
  error: '#B91C1C',
}
```

---

## Database Schema (MVP subset)

| Table | Purpose |
|-------|---------|
| `tenants` | Multi-tenant org isolation |
| `users` | Admin, recruiter, candidate identity |
| `jobs` | Job postings (title, description, skills, experience, salary range, status) |
| `job_rounds` | Interview rounds per job (type, duration, focus areas, order) |
| `candidates` | Candidate profiles (name, email, phone, resume URL, parsed data) |
| `applications` | Candidate ↔ Job link (status: applied/shortlisted/rejected/scheduled/interviewed) |
| `parsed_resumes` | Structured resume data (skills, experience, education, projects — JSON) |
| `eligibility_scores` | Resume ↔ JD match scores (skills_overlap, experience_match, overall) |
| `interview_slots` | Available scheduling slots per job |
| `scheduled_interviews` | Booked interviews (candidate, job, slot, status, room token) |
| `interview_rounds` | Per-round state during interview (round type, status, start/end time) |
| `interview_questions` | Questions per round (text, topic, difficulty, order, source) |
| `candidate_answers` | Candidate responses (transcript text, timestamps, round, question) |
| `evaluations` | Per-answer scores (relevance, depth, accuracy, communication, confidence) |
| `round_assessments` | Per-round aggregate scores + observations |
| `skill_assessments` | Per-skill aggregate scores + recommendation |
| `reports` | Final assessment reports (JSON payload, PDF URL, recommendation) |
| `proctoring_events` | Face detection, tab switch, fraud flags with timestamps |
| `notifications` | Email log (type, recipient, status, sent_at) |
| `ai_decision_logs` | Every LLM call: model, tokens, cost, latency, decision |

Full schema with all tables: see `docs/DB_SCHEMA.md`.

**Conventions:** UUID PKs, timestamptz, tenant_id + RLS, enums for status/difficulty/question_type/score_level.

### Key Enums

```sql
CREATE TYPE job_status AS ENUM ('draft', 'published', 'closed', 'archived');
CREATE TYPE application_status AS ENUM ('applied', 'parsing', 'shortlisted', 'rejected', 'invited', 'scheduled', 'in_progress', 'completed', 'no_show');
CREATE TYPE interview_round_type AS ENUM ('introduction', 'technical', 'behavioral', 'hr_culture');
CREATE TYPE question_type AS ENUM ('introduction', 'technical', 'behavioral', 'situational', 'hr', 'salary_negotiation');
CREATE TYPE difficulty_level AS ENUM ('easy', 'medium', 'hard', 'expert');
CREATE TYPE recommendation AS ENUM ('strong_hire', 'hire', 'maybe', 'no_hire');
CREATE TYPE proctoring_event_type AS ENUM ('face_detected', 'face_lost', 'multiple_faces', 'tab_switch', 'audio_anomaly');
```

---

## API Endpoints (MVP subset)

**Base:** `/api/v1`

| Area | Key Endpoints |
|------|--------------|
| Auth | `POST /auth/login`, `/auth/signup`, `/auth/refresh` |
| Jobs | `GET/POST /jobs`, `PATCH /jobs/{id}`, `POST /jobs/{id}/publish`, `GET /jobs/public` (no auth) |
| Applications | `POST /jobs/{id}/apply` (public, multipart — form + resume), `GET /jobs/{id}/applications` |
| Resume | `GET /applications/{id}/parsed-resume`, `POST /applications/{id}/parse` (trigger re-parse) |
| Eligibility | `GET /applications/{id}/eligibility`, `POST /applications/{id}/shortlist`, `POST /applications/{id}/reject` |
| Scheduling | `GET /jobs/{id}/slots`, `POST /jobs/{id}/slots` (admin sets), `POST /applications/{id}/schedule` (candidate books) |
| Interviews | `GET/POST /interviews`, `POST /interviews/{id}/start`, `POST /interviews/{id}/end` |
| Questions | `POST /interviews/{id}/questions/generate`, `GET /interviews/{id}/questions`, `POST /interviews/{id}/questions/{qid}/follow-up` |
| Answers | `POST /interviews/{id}/answers`, `GET /interviews/{id}/answers` |
| Evaluation | `POST /interviews/{id}/evaluate`, `GET /interviews/{id}/evaluation` |
| Transcription | `WebSocket /ws/transcription/{interview_id}` (real-time STT stream) |
| Interview Voice | `WebSocket /ws/interview/{interview_id}` (OpenAI Realtime relay) |
| Reports | `GET /interviews/{id}/report`, `POST /interviews/{id}/report/generate`, `GET /interviews/{id}/report/pdf` |
| Candidates | `GET /candidates`, `GET /candidates/{id}`, `GET /candidates/{id}/applications` |
| Proctoring | `POST /interviews/{id}/proctoring/events`, `GET /interviews/{id}/proctoring/summary` |
| Video Room | `POST /interviews/{id}/room/create`, `GET /interviews/{id}/room/token` |
| Notifications | `GET /notifications` (admin view sent emails) |
| Admin | `GET/PATCH /admin/config/ai`, `GET/POST /admin/templates` |
| Health | `GET /health` |

Full API: see `docs/API_SPEC.md`.

---

## Key Flows (MVP)

### 1. Recruiter creates a job posting

```
Recruiter opens admin dashboard -> clicks "New Job"
-> Fills: job title, department, description, required skills, experience, salary range
-> Configures interview rounds: Introduction (5 min), Technical (20 min), Behavioral (15 min), HR (10 min)
-> Sets eligibility threshold (e.g., 60% match minimum)
-> Publishes job -> generates public application URL
-> Shares URL on LinkedIn, careers page, job boards
```

### 2. Candidate applies

```
Candidate opens job listing -> clicks "Apply"
-> Fills onboarding form: name, email, phone, years of experience, expected salary
-> Uploads resume (PDF/DOCX) -> stored in S3
-> Application confirmed ("We'll review your application within 24 hours")
-> Async worker: resume_worker parses resume via GPT-4o structured output
-> Extracts: skills, experience, education, projects, certifications
-> Eligibility engine: matches parsed skills vs JD requirements
-> Score calculated: skills_overlap (40%) + experience_match (30%) + education (20%) + other (10%)
```

### 3. Auto-shortlist or reject

```
IF eligibility_score >= threshold:
    -> Application status: "shortlisted"
    -> Send email: "Congratulations! You've been shortlisted. Schedule your interview."
    -> Email contains scheduling link with unique token

IF eligibility_score < threshold:
    -> Application status: "rejected"
    -> Send email: "Thank you for applying. Unfortunately..." (with skill gap feedback)
    -> Application stored for future matching
```

### 4. Candidate schedules interview

```
Candidate clicks scheduling link -> sees available time slots
-> Selects preferred date/time
-> Confirmation page + email with:
    - Interview date/time (timezone-aware)
    - Interview room link (unique token)
    - Instructions (camera, mic, quiet room, stable internet)
    - Expected duration
    - Calendar invite (ICS attachment)
-> Reminder emails: 24h before + 1h before
```

### 5. Live AI interview (Video + Voice)

```
At scheduled time, candidate opens interview link

Step 1: System Check
    -> Camera permission -> Microphone permission -> Speed check
    -> "All systems ready. Click Start when you're ready."

Step 2: Face Detection
    -> MediaPipe loads in browser
    -> Verifies: candidate face detected, alone in frame
    -> Continuous monitoring throughout interview

Step 3: Interview — Round by Round
    -> OpenAI Realtime API connects (Speech-to-Speech)
    -> AI speaks questions naturally via voice
    -> Candidate answers via voice
    -> Real-time transcription runs in parallel

    ROUND 1 — Introduction (5-7 min):
        "Tell me about yourself"
        "Walk me through your career journey"
        "Why are you interested in this role?"

    ROUND 2 — Technical (15-20 min):
        Questions from resume skills + JD requirements
        Adaptive: strong answer → harder follow-up
        Adaptive: weak answer → simpler clarification

    ROUND 3 — Behavioral (10-15 min):
        STAR-method questions
        Leadership, teamwork, conflict resolution

    ROUND 4 — HR & Culture (5-10 min):
        Salary expectations discussion
        Availability, work mode preferences
        Questions about the company

-> Interview ends -> redirect to "done" page
```

### 6. Evaluation & report generation

```
Interview ends -> backend triggers evaluation
-> For each answer: LLM scores on rubric:
    - Relevance (0-10), Depth (0-10), Accuracy (0-10)
    - Communication (0-10), Confidence (0-10)
-> Aggregate per round (weighted by round type)
-> Aggregate per skill area
-> Calculate overall score (0-100)
-> Generate recommendation: Strong Hire / Hire / Maybe / No Hire
-> Generate salary recommendation
-> Generate strengths + areas for improvement
-> Build final report (JSON + PDF)
-> Email recruiter: "Assessment report ready for [Candidate Name]"
-> Report available in admin dashboard
```

### 7. Proctoring (continuous)

```
Interview starts -> MediaPipe client-side
-> Every 2s: detect face(s) in video frame
-> Face lost > 5s: POST proctoring event (face_lost)
-> Multiple faces: POST proctoring event (multiple_faces)
-> Tab switch: Page Visibility API detects, POST event
-> Integrity score: % face present, # tab switches
-> Summary included in final report
```

---

## LangGraph Agents (5) — Post-MVP

| Agent | Role | Model | Triggers |
|-------|------|-------|----------|
| Resume Parser Agent | Extract skills, experience, education from resume | Haiku | Interview creation (if resume uploaded) |
| Question Generator Agent | Generate role-specific, adaptive questions | Sonnet/GPT-4o | Interview start + after each answer |
| Evaluation Agent | Score answers on multi-dimensional rubric | GPT-4o | After each answer (real-time) |
| Proctoring Agent | Aggregate fraud signals, decide severity | Haiku | Continuous during interview |
| Report Agent | Generate comprehensive skill assessment report | Sonnet | Interview end |

**State:** `InterviewState(TypedDict)` — interview_id, candidate_id, job_role, skill_areas, questions, answers, evaluations, proctoring_events, face_presence_ratio, overall_score, recommendation, ai_cost_usd, errors.

**Key Patterns:**
1. **Dual-LLM Cost Optimization** — Haiku for parsing/classification, GPT-4o for evaluation/generation
2. **Adaptive Questioning** — Next question difficulty/topic adjusts based on previous answer score
3. **Real-Time + Batch Hybrid** — STT is real-time, evaluation can be near-real-time or batched at end
4. **Audit Every AI Decision** — Log model, tokens, cost, latency, decision, confidence

---

## Build Order

### Phase 1 — Foundation (Week 1)

1. Project scaffolding (backend + frontend + Docker Compose)
2. Supabase setup + migrations (users, tenants, jobs, candidates, applications)
3. Auth (login/signup/JWT/RBAC — admin, recruiter, candidate roles)
4. Health check + config validation at startup
5. Basic layout shell (admin sidebar, public job pages, candidate portal routing)

### Phase 2 — Job Posting & Application Pipeline (Week 2)

6. Job posting CRUD (create, edit, publish, archive) + admin UI
7. Public job listings page + job detail page
8. Candidate application form (onboarding fields + resume upload to S3)
9. AI resume parsing service (GPT-4o structured output → parsed_resumes table)
10. Eligibility engine (resume ↔ JD matching, scoring, auto-shortlist/reject)

### Phase 3 — Scheduling & Notifications (Week 3)

11. Email integration (Resend/SES) — application received, shortlisted, rejected
12. Interview scheduling: admin sets available slots
13. Self-service scheduling: candidate picks slot, confirmation email + ICS
14. Reminder emails (24h, 1h before interview)
15. Candidate portal: application status tracking + scheduling UI

### Phase 4 — Live AI Interview (Week 4-5)

16. WebRTC video room integration (Daily.co or LiveKit)
17. OpenAI Realtime API integration (Speech-to-Speech for AI interviewer voice)
18. Multi-round interview flow (Introduction → Technical → Behavioral → HR)
19. Adaptive question generation (LLM generates from resume + JD + previous scores)
20. Real-time transcription (Deepgram streaming or Whisper)
21. Answer storage (transcript + timestamps per round per question)

### Phase 5 — Evaluation & Proctoring (Week 5-6)

22. Per-answer LLM evaluation (5-dimension rubric: relevance, depth, accuracy, communication, confidence)
23. Per-round score aggregation (weighted by round type)
24. Per-skill assessment aggregation
25. Face detection (MediaPipe client-side) + proctoring events API
26. Overall score + recommendation (Strong Hire / Hire / Maybe / No Hire)

### Phase 6 — Reports & Polish (Week 6-7)

27. Report generation (JSON + PDF) with salary recommendation
28. Admin dashboard: candidate pipeline, interview calendar, report viewing
29. Candidate portal: post-interview report view (if allowed)
30. Error handling, loading states, empty states across all pages
31. Docker setup + AWS deployment config (ECS + ALB + CloudFront + S3)

---

## Coding Conventions

### Backend (Python/FastAPI)

- **Architecture:** Routes > Services > Repositories (clean layered)
- Routes are thin — validation + dependency injection only
- Business logic in services, DB access through repositories
- Pydantic v2 for all request/response schemas
- Async I/O for all external calls (OpenAI, Deepgram, Supabase, Redis)
- Error response: `{"code": "...", "message": "...", "details": ...}`
- Structured JSON logging with `request_id`, `interview_id`, `candidate_id`
- Never hardcode secrets

### Frontend (Next.js/TypeScript)

- App Router (Next.js 14+), TypeScript strict mode
- Small, reusable components; separate presentation from logic
- Handle loading, error, and empty states on every page
- WebSocket for real-time transcription via `useTranscription` hook
- WebRTC via `useWebRTC` hook (encapsulate provider SDK)
- MediaPipe face detection via `useFaceDetection` hook
- Role-based routing middleware
- API calls through centralized `lib/api.ts`

### Video & Audio

- WebRTC provider SDK handles all media transport (don't build raw WebRTC)
- **OpenAI Realtime API** is the primary voice interface — AI speaks and listens naturally
- Backend relays audio between WebRTC room and OpenAI Realtime via WebSocket
- Deepgram as fallback/parallel STT for transcript persistence
- Face detection runs client-side only (no video frames sent to backend)
- Audio capture: provider's audio track routed to OpenAI Realtime + Deepgram
- Handle connection drops gracefully — auto-reconnect with state preservation

### Security

- No secrets in code, Docker layers, or client bundles
- Validate all user input server-side
- RBAC enforced at API layer
- RLS enabled on tenant-scoped tables
- Candidate interview tokens: single-use, time-limited, tied to interview_id
- Treat uploaded resumes, prompts, and audio as untrusted
- Face detection data stays client-side (privacy)

### Testing

- Tests for all service methods: question generation, evaluation, report generation
- Mock external services (OpenAI, Deepgram, video provider) in tests
- Cover validation, failure, and edge cases
- Integration tests for interview lifecycle (create → start → answer → evaluate → report)

---

## Environment Variables

```env
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=

# OpenAI (Chat + Realtime API)
OPENAI_API_KEY=

# Deepgram (STT fallback)
DEEPGRAM_API_KEY=

# Video Provider (Daily.co or LiveKit)
DAILY_API_KEY=
# or
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=
LIVEKIT_URL=

# Redis
REDIS_URL=

# AWS
AWS_S3_BUCKET=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=
AWS_CLOUDFRONT_DOMAIN=        # CDN for static assets + PDFs

# Email (Resend or AWS SES)
RESEND_API_KEY=
# or
AWS_SES_FROM_EMAIL=

# App
APP_ENV=development
API_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
JWT_SECRET=
```

---

## Development Workflow

1. **Start backend:** `cd backend && uvicorn app.main:app --reload --port 8000`
2. **Start frontend:** `cd frontend && npm run dev`
3. **Start Redis:** `docker run -p 6379:6379 redis:alpine`
4. **Run migrations:** `supabase db push`
5. **Run tests:** `cd backend && pytest` / `cd frontend && npm test`

---

## Prompt Persistence Rule

Every prompt must be saved to `prompts/prompt-history.md`:
- Format: ISO 8601 timestamp + exact prompt text
- Append only, never delete existing entries
- Never save secrets/tokens
- Prompts include: question generation, answer evaluation, report generation

---

## References

- PRD: `docs/PRD.md`
- Architecture: `docs/ARCHITECTURE.md`
- API Spec: `docs/API_SPEC.md`
- DB Schema: `docs/DB_SCHEMA.md`
- Deployment: `docs/DEPLOYMENT.md`
- Engineering Context: `ENGINEERING-CONTEXT.md`
