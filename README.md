<h1 align="center">Intra AI</h1>

<p align="center">
  <strong>AI-Powered Interview & Skill Assessment Platform</strong>
</p>

<p align="center">
  Automate your entire hiring pipeline — from resume screening to multi-round AI voice interviews — and make data-driven hiring decisions in minutes, not weeks.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-15-black?logo=next.js" />
  <img src="https://img.shields.io/badge/FastAPI-Python_3.11-009688?logo=fastapi" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?logo=tailwindcss" />
  <img src="https://img.shields.io/badge/OpenAI-Realtime_API-412991?logo=openai" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3FCF8E?logo=supabase" />
  <img src="https://img.shields.io/badge/License-MIT-yellow" />
</p>

---

## What is Intra AI?

Current assistant workflows: [Morgan HR actions and interview templates](docs/MORGAN_HR_WORKFLOWS.md) · [Taylor native practice](docs/TAYLOR_NATIVE_PRACTICE.md). These delivery notes include the tested behavior and current integration limits.

Intra AI replaces the manual interview process with an AI-powered pipeline:

```
Candidate Applies → Resume Parsed (GPT-4o) → Eligibility Scored
  → Interview Scheduled → AI Voice Interview (4 Rounds)
    → Per-Answer Evaluation (5 Dimensions) → Assessment Report
      → Hire/No-Hire Recommendation + Salary Guidance
```

**Who is this for?**
- Hiring platforms automating first-round interviews
- Startups screening 100s of candidates without a dedicated HR team
- Universities and bootcamps running placement assessments
- Staffing agencies scaling candidate evaluation
- Enterprises standardizing interview quality across teams

---

## Features

| Feature | Description |
|---------|-------------|
| **Resume Intelligence** | GPT-4o parses resumes and scores candidates against job requirements across skills, experience, and education |
| **Multi-Round AI Interviews** | Introduction, Technical, Behavioral, and HR rounds — fully automated and customizable per role |
| **Voice AI Interviewer** | Natural speech-to-speech conversation powered by OpenAI Realtime API |
| **5-Dimension Evaluation** | Each answer scored on relevance (25%), depth (25%), accuracy (20%), communication (20%), confidence (10%) |
| **Smart Proctoring** | Client-side face detection (MediaPipe) monitors presence and integrity throughout interviews |
| **Assessment Reports** | PDF reports with per-skill breakdowns, round scores, strengths, weaknesses, and hiring recommendations |
| **Salary Guidance** | AI-recommended salary range based on performance, experience, and market benchmarks |
| **Candidate Portal** | Self-service portal with application tracking, interview scheduling, and report access |
| **Admin Dashboard** | Real-time hiring pipeline, interview calendar, candidate Kanban, and analytics |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 15, TypeScript, Tailwind CSS v4, Radix UI |
| **Backend** | Python 3.11+, FastAPI, Pydantic v2 |
| **Database** | Supabase (PostgreSQL + pgvector) |
| **Cache** | Redis |
| **AI Voice** | OpenAI Realtime API (Speech-to-Speech) |
| **AI Evaluation** | GPT-4o (resume parsing, answer scoring, report generation) |
| **Proctoring** | MediaPipe (face detection — client-side) |
| **Auth** | Supabase Auth + JWT, RBAC |
| **Storage** | AWS S3 (resumes, reports) |
| **Deployment** | Docker + AWS ECS Fargate |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (Next.js 15)                 │
│  Landing │ Auth │ Jobs │ Admin Dashboard │ Interview Room│
│  Candidate Portal │ Reports │ Settings │ Scheduling      │
└────────────────────────┬────────────────────────────────┘
                         │ REST API
┌────────────────────────┴────────────────────────────────┐
│                    BACKEND (FastAPI)                      │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Auth   │  │   Jobs   │  │Candidates│  │Interviews│ │
│  │ Service │  │  Service │  │ Service  │  │ Service  │ │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘ │
│       │            │             │              │        │
│  ┌────┴────┐  ┌────┴─────┐  ┌───┴──────┐  ┌───┴──────┐│
│  │ Resume  │  │Eligibility│  │Evaluation│  │  Report  ││
│  │ Parser  │  │  Scorer   │  │  Engine  │  │Generator ││
│  └─────────┘  └──────────┘  └──────────┘  └──────────┘ │
└────────┬───────────┬──────────────┬─────────────┬───────┘
         │           │              │             │
    ┌────┴───┐  ┌────┴────┐   ┌────┴────┐  ┌────┴────┐
    │Supabase│  │  Redis  │   │ OpenAI  │  │  AWS S3 │
    │  (DB)  │  │ (Cache) │   │Realtime │  │(Storage)│
    └────────┘  └─────────┘   └─────────┘  └─────────┘
```

---

## Interview Flow

Intra AI conducts **4-round interviews**, each with adaptive questioning:

| Round | Duration | What's Assessed |
|-------|----------|----------------|
| **1. Introduction** | 5-7 min | Background, motivation, career goals |
| **2. Technical** | 15-20 min | Skills from resume matched against JD — adaptive difficulty |
| **3. Behavioral** | 10-15 min | STAR-method: leadership, teamwork, conflict resolution |
| **4. HR & Culture** | 5-10 min | Salary expectations, availability, culture fit |

### Evaluation Rubric (5 Dimensions)

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Relevance | 25% | How well the answer addresses the question |
| Depth | 25% | Level of detail and thoroughness |
| Accuracy | 20% | Technical correctness |
| Communication | 20% | Clarity, structure, articulation |
| Confidence | 10% | Delivery, poise, conviction |

---

## Project Structure

```
intra-ai/
├── frontend/                 # Next.js 15 + Tailwind v4
│   ├── src/
│   │   ├── app/
│   │   │   ├── (auth)/       # Login, Signup
│   │   │   ├── (public)/     # Jobs listing, Job detail, Apply
│   │   │   ├── (candidate)/  # Portal, Scheduling, Interview room
│   │   │   └── admin/        # Dashboard, Jobs, Candidates, Reports, Settings
│   │   ├── components/
│   │   │   └── ui/           # 16 reusable components
│   │   └── lib/              # Utils, API client
│   └── package.json
│
├── backend/                  # FastAPI + Python 3.11
│   ├── app/
│   │   ├── routes/           # 9 route modules
│   │   ├── services/         # 11 business logic services
│   │   ├── repositories/     # 5 data access repositories
│   │   ├── schemas/          # 8 Pydantic schema modules
│   │   ├── integrations/     # Supabase, Redis, OpenAI, S3, Email
│   │   └── core/             # Config, security, middleware, exceptions
│   ├── requirements.txt
│   └── Dockerfile
│
├── docs/
│   └── PRD.md                # Product Requirements Document
│
├── docker-compose.yml
├── .env.example
└── CLAUDE.md                 # AI coding context
```

### Frontend Routes (24 pages)

| Section | Routes |
|---------|--------|
| **Landing** | `/` — Hero, stats, how-it-works, features, pricing, CTA |
| **Auth** | `/login`, `/signup` — With role toggle (candidate/recruiter) |
| **Public Jobs** | `/jobs`, `/jobs/[id]`, `/jobs/[id]/apply` — Search, filter, 3-step apply |
| **Admin** | `/admin/dashboard`, `/admin/jobs`, `/admin/jobs/new`, `/admin/candidates`, `/admin/interviews`, `/admin/reports`, `/admin/reports/[id]`, `/admin/settings` |
| **Candidate** | `/portal` — Application tracker with pipeline stepper |
| **Scheduling** | `/schedule/[token]` — 14-day calendar + time slots |
| **Interview** | `/interview/[token]`, `/interview/[token]/prep`, `/interview/[token]/done`, `/interview/[token]/report` |

### Backend Modules (52 files)

| Layer | Modules |
|-------|---------|
| **Routes** | auth, jobs, candidates, applications, interviews, scheduling, evaluation, reports, health |
| **Services** | auth, job, application, eligibility, evaluation, interview, notification, question, report, resume, scheduling |
| **Repositories** | user, job, candidate, application, interview |
| **Schemas** | auth, jobs, candidates, applications, interviews, evaluation, reports, common |
| **Integrations** | supabase, redis, openai, s3, email |

---

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- Redis
- Supabase account (or local PostgreSQL)

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local
npm run dev
# → http://localhost:3000
```

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
uvicorn app.core.main:app --reload --port 8000
# → http://localhost:8000/docs
```

### Environment Variables

```bash
cp .env.example .env
```

See `.env.example` for all required variables (OpenAI, Supabase, Redis, S3, etc.)

---

## Roadmap

- [x] Landing page with dashboard mockup
- [x] Auth (login/signup with role toggle)
- [x] Job management (listing, detail, create, apply)
- [x] Admin dashboard with pipeline analytics
- [x] Candidates Kanban (5-stage pipeline)
- [x] Interview calendar view
- [x] Assessment reports with score circles
- [x] AI interview room (dark theme, transcript, rounds)
- [x] Candidate self-service portal
- [x] Settings with AI config (threshold sliders, rubric weights)
- [x] Backend API skeleton (FastAPI, 52 files)
- [ ] Supabase migrations (21 tables)
- [ ] API wiring (frontend ↔ backend)
- [ ] OpenAI Realtime API integration (voice interviews)
- [ ] Resume parsing with GPT-4o structured output
- [ ] Eligibility scoring engine
- [ ] Real-time evaluation pipeline
- [ ] PDF report generation
- [ ] Email notifications (interview invites, results)
- [ ] MediaPipe proctoring integration
- [ ] Docker deployment

---

## Contributing

Contributions are welcome! Please read the codebase structure above and check `CLAUDE.md` for architecture context.

```bash
# Fork → Clone → Branch → PR
git checkout -b feature/your-feature
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with Next.js, FastAPI, OpenAI, and Supabase.<br/>
  <strong>Star this repo</strong> if you find it useful!
</p>
