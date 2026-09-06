# Product Requirements Document — Intra AI

## Product Name

Intra AI — AI Interviewer & Skill Assessment Platform

## Problem

Companies spend 20-40 hours per hire on interviews. Recruiters manually screen resumes, schedule calls, conduct 3-5 rounds, and write evaluations. 70% of initial interviews are wasted on unqualified candidates. Human bias affects 60% of hiring decisions. Small companies can't afford dedicated hiring teams. The process is slow, expensive, inconsistent, and unscalable.

Intra AI automates the entire pipeline: resume parsing → eligibility matching → interview scheduling → multi-round AI interviews (video + voice) → per-round assessment → final report with salary recommendation.

## Core Users

| User | Role |
|------|------|
| Candidate | Applies for job, uploads resume, schedules interview, takes AI interview |
| Recruiter / HR | Creates job postings, reviews AI assessment reports, makes final decisions |
| Hiring Manager | Configures interview rounds, sets skill requirements, reviews top candidates |
| Admin | Manages platform settings, AI configuration, templates, billing |

---

## End-to-End Flow (The Complete Pipeline)

### Phase 1: Job Posting & Candidate Onboarding

```
Hiring Manager creates job posting
    → Job title, description, required skills, experience level, salary range
    → Configures interview rounds (intro, technical, behavioral, HR)
    → Sets eligibility criteria (min experience, required skills, education)
    → Publishes job → generates public application URL

Candidate applies
    → Fills onboarding form:
        - Full name
        - Email address
        - Phone number
        - LinkedIn URL (optional)
        - Current role & company
        - Years of experience
        - Expected salary range
    → Uploads resume (PDF/DOCX)
    → Submits application
```

### Phase 2: Resume Parsing & Eligibility Check

```
System receives application
    → AI parses resume:
        - Personal info (name, contact, location)
        - Education (degrees, institutions, years)
        - Work experience (companies, roles, duration, responsibilities)
        - Technical skills (languages, frameworks, tools, databases)
        - Certifications & achievements
        - Projects (descriptions, tech used)
    → Matches against job description:
        - Required skills overlap (%)
        - Experience level match
        - Education match
        - Overall eligibility score (0-100)

IF eligible (score >= threshold):
    → Send email invite: "You're shortlisted! Schedule your interview."
    → Email contains scheduling link with available slots

IF not eligible:
    → Send polite rejection email with feedback
    → Store application for future openings
```

### Phase 3: Interview Scheduling

```
Candidate opens scheduling link
    → Sees available time slots (next 7-14 days)
    → Selects preferred date & time
    → Receives confirmation email with:
        - Interview date/time
        - Interview link (unique token)
        - Instructions (camera, mic, quiet room, ID)
        - Expected duration (30-60 min based on rounds)
    → Calendar invite sent (ICS attachment)

System schedules the AI interview session
    → Pre-generates questions based on:
        - Resume skills & experience
        - Job description requirements
        - Round-specific focus areas
    → Creates interview room (WebRTC)
```

### Phase 4: Live AI Interview (Video + Voice)

```
At scheduled time, candidate joins via link

Step 1: System Check
    → Camera permission check
    → Microphone permission check
    → Internet speed check
    → Browser compatibility check
    → "All systems ready. Click Start when you're ready."

Step 2: Identity Verification
    → Face detection (MediaPipe) — confirm candidate is present
    → Match face with any uploaded photo (optional, post-MVP)

Step 3: Interview Begins — Round by Round

ROUND 1: Introduction (5-7 min)
    → AI: "Tell me about yourself"
    → AI: "Walk me through your career journey"
    → AI: "Why are you interested in this role?"
    → AI: "What are your key strengths?"
    → Assess: Communication clarity, confidence, self-awareness

ROUND 2: Technical Assessment (15-20 min)
    → Questions generated from resume skills + JD requirements
    → Example (for a Python developer):
        - "Explain how you've used FastAPI in production"
        - "What's your approach to database optimization?"
        - "Walk me through a system you've designed"
        - "How would you handle rate limiting in an API?"
    → Adaptive: If candidate scores well → harder follow-ups
    → Adaptive: If candidate struggles → simpler clarification questions
    → Assess: Technical depth, problem-solving, architecture thinking

ROUND 3: Behavioral Assessment (10-15 min)
    → STAR-method questions:
        - "Tell me about a time you dealt with a difficult team member"
        - "Describe a project that failed. What did you learn?"
        - "How do you handle tight deadlines?"
        - "Give an example of when you took initiative"
    → Assess: Leadership, teamwork, conflict resolution, growth mindset

ROUND 4: HR & Culture Fit (5-10 min)
    → "What's your expected salary range?"
    → "When can you start?"
    → "Are you open to [remote/hybrid/onsite]?"
    → "Do you have any questions about the company?"
    → Salary negotiation simulation (if configured)
    → Assess: Expectations alignment, culture fit, enthusiasm

Each Round:
    → AI asks question via voice (Speech-to-Speech or TTS)
    → Candidate answers via voice
    → Real-time transcription (speech-to-text)
    → AI evaluates answer in background
    → AI decides next question (adaptive)
    → Timer visible to candidate
    → "Next Question" button available (skip option)
```

### Phase 5: Assessment & Report Generation

```
Interview ends
    → System generates comprehensive assessment:

Per-Round Scores:
    ┌─────────────────┬───────┬─────────────────────────────┐
    │ Round           │ Score │ Key Observations            │
    ├─────────────────┼───────┼─────────────────────────────┤
    │ Introduction    │ 8/10  │ Clear communicator, confident│
    │ Technical       │ 7/10  │ Strong Python, weak on DBs  │
    │ Behavioral      │ 9/10  │ Excellent STAR responses    │
    │ HR & Culture    │ 8/10  │ Salary aligned, flexible    │
    └─────────────────┴───────┴─────────────────────────────┘

Skill-Wise Assessment:
    - Communication: 8.5/10
    - Technical Depth: 7.0/10
    - Problem Solving: 7.5/10
    - Leadership: 8.0/10
    - Culture Fit: 8.5/10
    - Confidence: 9.0/10

Overall:
    - Overall Score: 78/100
    - Recommendation: STRONG HIRE / HIRE / MAYBE / NO HIRE
    - Salary Recommendation: Based on market + candidate expectation + performance
    - Strengths: [list]
    - Areas for Improvement: [list]
    - Suggested Next Steps: [e.g., "Proceed to final round with hiring manager"]

Report available as:
    → Web view (admin dashboard)
    → PDF download
    → Email to recruiter/hiring manager
```

---

## Core Modules (12 Feature Areas)

### 1. Job Management

- Create, edit, publish, archive job postings
- Job description with structured fields (title, department, location, type, salary range)
- Required skills and experience configuration
- Interview round configuration (which rounds, duration, question focus)
- Eligibility criteria and threshold settings
- Public application URL generation
- Job analytics (views, applications, conversion rate)

### 2. Candidate Onboarding

- Public application form (responsive, mobile-friendly)
- Required fields: name, email, phone, experience, expected salary
- Resume upload (PDF, DOCX — max 10MB)
- LinkedIn URL import (optional)
- Application confirmation email
- Candidate portal (track application status)
- Duplicate detection (same email/phone)

### 3. Resume Parsing & Intelligence

- AI-powered resume parser (extract structured data from PDF/DOCX)
- Extract: personal info, education, experience, skills, projects, certifications
- Skill taxonomy mapping (e.g., "React.js" → "React" → "Frontend Framework")
- Experience level detection (junior/mid/senior/lead)
- Resume-to-JD matching score (0-100)
- Skill gap identification (what the resume is missing vs. JD)
- Batch processing for bulk applications

### 4. Eligibility Engine

- Configurable matching rules per job
- Weighted scoring: skills (40%), experience (30%), education (20%), other (10%)
- Auto-shortlist candidates above threshold
- Auto-reject with feedback below threshold
- Manual override for recruiters
- Eligibility audit log (why accepted/rejected)

### 5. Interview Scheduling

- Available slot management (recruiter sets availability windows)
- Self-service scheduling (candidate picks slot from available times)
- Timezone-aware scheduling
- Calendar integration (Google Calendar ICS)
- Confirmation + reminder emails (24h before, 1h before)
- Reschedule and cancellation flow
- No-show detection and re-invite

### 6. Live AI Interview Engine (Core)

- WebRTC video + audio room
- OpenAI Speech-to-Speech API for real-time AI conversation
- Multi-round interview flow (introduction → technical → behavioral → HR)
- Adaptive question generation based on resume + JD + previous answers
- Real-time speech-to-text transcription
- Per-question timer + overall interview timer
- "Next Question" skip button for candidates
- Interview pause/resume capability
- Graceful error handling (connection drop → rejoin)

### 7. Proctoring & Integrity

- Face presence detection (MediaPipe, client-side)
- Multiple face detection (flag if >1 person)
- Tab switch detection (Page Visibility API)
- Audio anomaly detection (background voices, text-to-speech)
- Proctoring event log with timestamps
- Integrity score (% of time face present, # of tab switches)
- Fraud flag system (auto + manual)

### 8. Answer Evaluation Engine

- Per-answer LLM evaluation with structured rubric
- Evaluation dimensions:
  - **Relevance** — Does the answer address the question? (0-10)
  - **Depth** — How thorough and detailed? (0-10)
  - **Accuracy** — Is the technical content correct? (0-10)
  - **Communication** — Clarity, structure, articulation (0-10)
  - **Confidence** — Tone, pace, conviction (0-10)
- Adaptive difficulty: harder follow-ups for strong answers, easier for weak
- Real-time scoring (candidate doesn't see scores during interview)
- Evaluation audit trail (which model, what rubric, confidence level)

### 9. Assessment Report Generator

- Per-round score breakdown
- Per-skill aggregate scoring
- Overall recommendation (Strong Hire / Hire / Maybe / No Hire)
- Strengths and weaknesses summary (AI-generated)
- Salary recommendation (based on performance + market + expectations)
- Interview transcript (full, searchable)
- Proctoring summary (integrity score, flagged events)
- Comparative ranking (candidate vs. other applicants for same job)
- PDF report generation (branded, professional)
- Email delivery to recruiter/hiring manager

### 10. Admin Dashboard

- Job posting management (CRUD)
- Candidate pipeline view (applied → shortlisted → scheduled → interviewed → assessed)
- Interview calendar view
- Report viewing and downloading
- AI configuration (models, rubric weights, round settings)
- Interview template management (reusable configurations)
- Team management (invite recruiters, hiring managers)
- Platform analytics (interviews conducted, avg scores, time-to-hire)

### 11. Candidate Portal

- Application status tracking
- Interview scheduling self-service
- Pre-interview system check (camera, mic, speed)
- Interview room entry
- Post-interview: view report (if recruiter allows)
- Notification preferences

### 12. Notifications & Email System

- Application received confirmation
- Shortlisted / rejection notification
- Interview invite with scheduling link
- Interview reminders (24h, 1h)
- Interview completed — report ready notification
- Reschedule / cancellation notifications
- All emails: branded, professional, mobile-responsive

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 14+, TypeScript, Tailwind CSS | SSR, type safety, rapid UI |
| Backend | Python 3.11+, FastAPI, Pydantic v2 | Async, typed, fast API development |
| Database | Supabase (PostgreSQL + pgvector) | Auth, RLS, realtime, vector search |
| Cache | Redis | Session state, rate limiting, job queue |
| CDN | AWS CloudFront | Static assets, resume downloads, report PDFs |
| Video/Audio | WebRTC (Daily.co or LiveKit) | Reliable video rooms, no raw WebRTC |
| AI Conversation | OpenAI Speech-to-Speech API (Realtime API) | Natural voice interview, low latency |
| AI Evaluation | OpenAI GPT-4o / Claude Sonnet | Answer scoring, report generation |
| Resume Parsing | OpenAI GPT-4o (structured output) | Extract structured data from PDF |
| Speech-to-Text | Deepgram (streaming) or OpenAI Whisper | Real-time transcription fallback |
| Face Detection | MediaPipe (client-side) | Privacy-first, no video to server |
| File Storage | AWS S3 | Resumes, reports, recordings |
| Email | Resend or AWS SES | Transactional emails |
| Auth | Supabase Auth + JWT | RBAC, social login |
| Deployment | Docker, AWS (ECS Fargate, ALB) | Production-grade, scalable |
| Monitoring | Sentry + structured logging | Error tracking, observability |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PUBLIC INTERNET                               │
│                                                                       │
│   Candidate                          Recruiter / Admin                │
│   (applies, schedules,               (creates jobs, views             │
│    takes interview)                   reports, manages)               │
└────────────┬──────────────────────────────┬──────────────────────────┘
             │                              │
             ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AWS CloudFront (CDN)                               │
│              Static assets, resume downloads                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    AWS ALB / API Gateway                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Next.js App    │ │  FastAPI Backend │ │  WebRTC Provider │
│  (SSR + SPA)    │ │  (REST + WS)    │ │  (Daily.co /     │
│                 │ │                 │ │   LiveKit)       │
│  Pages:         │ │  Services:      │ │                 │
│  - Job listings │ │  - Job          │ │  + OpenAI       │
│  - Apply form   │ │  - Resume       │ │    Realtime API │
│  - Schedule     │ │  - Eligibility  │ │    (Speech-to-  │
│  - Interview    │ │  - Scheduling   │ │     Speech)     │
│    room         │ │  - Interview    │ │                 │
│  - Admin panel  │ │  - Evaluation   │ └─────────────────┘
│  - Reports      │ │  - Report       │
└────────┬────────┘ │  - Proctoring   │
         │          │  - Notification  │
         │          └────────┬────────┘
         │                   │
         │          ┌────────┴────────┐
         │          │  Repositories   │
         │          └────────┬────────┘
         │                   │
         ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Supabase (PostgreSQL + pgvector + Auth + RLS + Realtime)           │
└─────────────────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Redis           │ │  AWS S3          │ │  Resend / SES   │
│  (cache, queue,  │ │  (resumes, PDFs, │ │  (emails)       │
│   rate limit)    │ │   recordings)    │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## Interview Round Configuration

| Round | Duration | Focus | Question Source | Assessment |
|-------|----------|-------|----------------|------------|
| Introduction | 5-7 min | Self-introduction, career, motivation | Standard + JD | Communication, confidence, self-awareness |
| Technical | 15-20 min | Skills from resume + JD requirements | Resume skills + JD + adaptive | Technical depth, accuracy, problem-solving |
| Behavioral | 10-15 min | STAR method, leadership, teamwork | Standard behavioral bank + role-specific | Leadership, teamwork, conflict resolution |
| HR & Culture | 5-10 min | Salary, availability, culture fit | Standard HR + company-specific | Expectations alignment, enthusiasm |

**Configurable:** Hiring managers can enable/disable rounds, adjust duration, add custom questions.

---

## Evaluation Rubric

### Per-Answer Scoring (5 dimensions, each 0-10)

| Dimension | What It Measures | Weight |
|-----------|-----------------|--------|
| Relevance | Does the answer address the question directly? | 25% |
| Depth | How thorough, detailed, and comprehensive? | 25% |
| Accuracy | Is the technical/factual content correct? | 20% |
| Communication | Clarity, structure, articulation, grammar | 15% |
| Confidence | Tone, pace, conviction, no excessive fillers | 15% |

### Per-Round Scoring

Each round aggregates answer scores with round-specific weights:
- Introduction: Communication (40%) + Confidence (30%) + Relevance (30%)
- Technical: Accuracy (35%) + Depth (30%) + Relevance (20%) + Communication (15%)
- Behavioral: Depth (30%) + Relevance (25%) + Communication (25%) + Confidence (20%)
- HR: Relevance (40%) + Communication (30%) + Confidence (30%)

### Overall Score → Recommendation

| Score Range | Recommendation | Action |
|-------------|---------------|--------|
| 85-100 | **Strong Hire** | Fast-track to final round |
| 70-84 | **Hire** | Proceed with process |
| 55-69 | **Maybe** | Discuss with team, possible re-interview |
| 0-54 | **No Hire** | Polite rejection with feedback |

---

## Salary Recommendation Logic

```
Input:
    - Candidate's expected salary range
    - Job posting's salary range
    - Candidate's performance score
    - Market data (role + location + experience level)

Output:
    - Recommended offer range
    - Justification (e.g., "Score 82/100, 5yr exp, market median $120K")
    - Negotiation notes (e.g., "Candidate flexible on remote, can offer lower")
```

---

## MVP vs. Post-MVP Scope

### MVP (Phase 1) — Ship This First

| Feature | Priority |
|---------|----------|
| Job posting CRUD | P0 |
| Candidate application form + resume upload | P0 |
| Resume parsing (AI) | P0 |
| Eligibility scoring + auto-shortlist | P0 |
| Email notifications (invite, confirmation, rejection) | P0 |
| Interview scheduling (self-service) | P0 |
| Live AI interview — video + voice (OpenAI Realtime API) | P0 |
| Multi-round flow (intro, technical, behavioral, HR) | P0 |
| Real-time transcription | P0 |
| Per-answer evaluation (LLM) | P0 |
| Assessment report (web + PDF) | P0 |
| Face presence detection | P0 |
| Admin dashboard (jobs, candidates, reports) | P0 |
| Candidate portal (status, schedule, interview) | P0 |
| Auth + RBAC (admin, recruiter, candidate) | P0 |

### Post-MVP (Phase 2+)

| Feature | Phase |
|---------|-------|
| Coding interview environment (live editor + execution) | 2 |
| Speech emotion / confidence scoring (prosody analysis) | 2 |
| Advanced fraud detection (tab switch, audio anomaly, multiple faces) | 2 |
| Video recording & playback for reviewers | 2 |
| Bulk resume upload + batch processing | 2 |
| ATS integrations (Greenhouse, Lever, Workday) | 3 |
| White-label API / embeddable widget | 3 |
| Panel interview mode (multiple AI personas) | 3 |
| Benchmark comparisons (candidate vs. cohort) | 3 |
| Multi-language support | 3 |
| Calendar integration (Google, Outlook) | 2 |
| SMS notifications (Twilio) | 2 |
| LangGraph multi-agent orchestration | 3 |
| Analytics warehouse (BigQuery) | 3 |
| Continuous learning from recruiter feedback | 3 |

---

## Pricing Model

| Package | Price | What They Get |
|---------|-------|--------------|
| Starter | $500/mo | 50 interviews/mo, 2 rounds, text report |
| Pro | $2K/mo | 200 interviews/mo, 4 rounds, video proctoring, PDF reports, analytics |
| Enterprise | $5K+ setup + $3K/mo | Unlimited, custom rubrics, ATS integration, white-label, dedicated support |

**Per-interview cost breakdown:**
- OpenAI Realtime API: ~$0.10-0.30/interview (30-60 min)
- GPT-4o evaluation: ~$0.05-0.10/interview (scoring all answers)
- Resume parsing: ~$0.02/resume
- Deepgram STT (fallback): ~$0.006/min
- Infrastructure: ~$0.05/interview
- **Total: ~$0.25-0.50/interview → 90%+ margin at scale**

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Resume parse accuracy | >90% field extraction |
| Eligibility matching precision | >85% (validated by recruiter) |
| Interview completion rate | >80% (candidates who start finish) |
| Assessment accuracy | >75% correlation with human interviewer scores |
| Time-to-first-interview | <48 hours from application |
| Report generation time | <2 minutes after interview ends |
| System uptime | 99.9% |
| Candidate satisfaction (post-interview survey) | >4.0/5.0 |

---

## Security & Compliance

- All data encrypted at rest (Supabase) and in transit (TLS)
- Resume data: stored in S3 with server-side encryption
- Interview recordings: stored encrypted, access-controlled
- GDPR-ready: candidate data deletion on request
- SOC 2 Type II alignment (post-MVP)
- No biometric data stored (face detection is client-side only)
- AI decision audit logs for every evaluation
- Rate limiting on all public endpoints
- CAPTCHA on application form

---

## Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| OpenAI Realtime API latency | Poor interview experience | Fallback to TTS + STT pipeline |
| Resume parser inaccuracy | Wrong eligibility decisions | Human review queue for edge cases |
| Candidate drops during interview | Incomplete assessment | Auto-save progress, rejoin capability |
| AI bias in evaluation | Legal/ethical issues | Regular rubric calibration, diverse training prompts |
| WebRTC connection issues | Interview failure | Pre-interview system check, graceful degradation |
| High API costs at scale | Low margins | Cache common questions, batch evaluations |
