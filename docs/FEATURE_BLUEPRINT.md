# Feature extension blueprint and architecture lock

Reconciled against source on 2026-09-09. `objective.md` and the user's architecture lock govern this implementation. This file records design decisions; passing tests and the delivery audit determine implementation status.

## Protected architecture

Standard Interview retains its existing M1, InterviewAIContext, AgentTurnContext, LangGraph Meta-Orchestrator, NextAction, agent registry, sessions and Agora media behavior. New domains must never import M1, interview context, interview actions or orchestrator internals. Removal of all new feature routers must leave the existing interview flow operational.

Role-play owns RolePlayIntelligence, RolePlayOrchestrator and RolePlayAction. GD owns GDIntelligence, deterministic participation signals, GDModerator and GDModeratorAction. Intelligence observes, orchestration selects validated transitions, and response generation expresses the selected action. There is no universal intelligence engine or universal orchestrator.

AICredits remains the only new LLM transport. Extend its existing bounded JSON client with additive named feature slots; preserve old calls and model behavior. Do not add another provider or use M1's transport purpose as a new feature contract. New realtime adapters expose local text operation and explicitly report voice unavailable. They must neither import Agora SDKs nor issue RTC credentials or create agents/rooms.

## Repository reconciliation (pre-extension baseline)

The status column below records what existed at reconciliation, not the current delivery state. Current implemented/partial/missing/configuration/future classifications and verified results are in [FEATURE_IMPLEMENTATION_AUDIT.md](FEATURE_IMPLEMENTATION_AUDIT.md).

| Area | Current source status | Reuse / required change |
| --- | --- | --- |
| Standard interviews | Implemented | Preserve protected packages and regression behavior. Existing older provider compatibility classes stay isolated. |
| AICredits | Implemented | Reuse request/response bounds, error classification, JSON validation and HTTP lifecycle. Add named feature JSON calls only. |
| Resume upload/parsing | Partial for onboarding | ApplicationService and ResumeService already upload, parse, normalize and persist application CVs. Add strict PDF/DOCX extraction and a profile entry point; reuse private Supabase storage. |
| Candidate onboarding | Missing | Add durable versioned profile ownership, current-version selection, status detection, replacement and reuse APIs. Never require a job to onboard. |
| Identity/access | Partial | JWT dependency alone returns claims. Reuse workspace_access.current_actor and voice.authorization.identity to resolve active persisted users. Recruiter access remains owner-scoped, including within a tenant. |
| Company knowledge | Missing | Add owner/tenant-scoped documents, immutable versions, effective windows, archive, bounded retrieval and citation-preserving context enrichment. |
| Role-play | Missing | Add reusable persona/scenario configuration, separate intelligence/actions, durable optimistic state transitions, transcript, evidence and reports. |
| Group discussion | Missing | Add shared sessions, bound hashed invitations, participant lifecycle, ordered durable events, signals, moderation and individual reports. |
| Evidence/reporting | Implemented for interviews | Existing tables have mandatory interview/question/answer foreign keys. Do not create fake interview rows or change those contracts. Persist new findings with their authoritative domain events; adapt existing report rating and AICredits narrative primitives. |
| Neo4j | Implemented for interviews | Existing Evidence requires answer/round provenance and retrieval identifies it as INTERVIEW_EVIDENCE. Project new domain evidence into source-specific graph labels attached to the same Candidate root; avoid contaminating legacy reads. No second graph store. |
| Frontend | Implemented ATS and assistants | Reuse apiClient, AuthProvider, QueryProvider, UI tokens and layouts. Place new state/API/components in src/features. |
| Migrations | Partial | Two dated SQL migrations plus docker/init-db/01-init.sql. Base local schema broadly grants anonymous access. New migrations require FKs, checks, indexes, server-only grants/RLS, transactional RPCs and repeatable application. |
| Readiness/Docker | Partial | Existing readiness returns a constant. Backend Docker runs as root and Compose is development-only. Add actual dependency readiness and deployment guidance without AWS deployment. |
| Existing control routes | Needs hardening | Custom LLM checks credential presence but does not authenticate it; session creation and several legacy control routes are public. Protect external boundaries without changing interview reasoning/media. |

## Persistence decisions

Supabase/PostgreSQL remains authoritative. Feature repositories use the existing service-role Supabase client. Multi-row changes use narrowly scoped PostgreSQL functions, row locks and expected versions. Retries carry request IDs and must reject a reused ID with different content. Never hold a database lock during LLM/network calls; use optimistic compare-and-swap on commit. State, transitions, findings and pending graph delivery commit together. In-process structures are allowed only in tests and non-authoritative transport helpers.

Onboarding uses candidate-owned immutable resume versions and existing parsed-resume fields, with an explicit active profile pointer. Recruiters cannot browse candidate onboarding files without an authorized application relationship. Replacement never changes old applications or completed assessment evidence. Storage writes use unpredictable version-specific keys; failed persistence must not activate incomplete profiles.

Company knowledge uses immutable document versions and source chunks, inclusive start/exclusive end effective windows, explicit archive, and bounded lexical retrieval initially. The result retains document/version/chunk/date provenance. Missing or conflicting policy returns an explicit unavailable/conflict result. Retrieved text is data, and company-policy output must use validated citations/excerpts. An optional enricher is independently callable for authorized interview context; automatic changes to protected interview prompts require a separately justified integration.

Role-play pins persona/scenario/profile definitions at session creation. Its backend stores hidden configuration separately from candidate projections. Persona generation receives only currently allowed/revealed information. Configuration controls phases, signal triggers, escalation, disclosure, completion and duration; backend validates every action. Model outages preserve recorded turns and an explicit unevaluated state; reports cannot fabricate missing assessments.

GD invitations are random, hashed, expiring, candidate-bound, session-bound and atomically consumed. Candidates rejoin using authenticated membership, not a reusable invitation secret. Server-assigned event order, idempotency and optimistic version checks prevent lost concurrent turns. Local text participation can measure turns, replies and observed timestamps. Speaking duration/overlap are unknown without trusted media events; never infer them from character count or client claims. Each participant receives a separate report, with no private evaluation of peers.

New evidence stays in domain event records; a durable delivery queue projects those same records to Neo4j. Reports consume validated saved evidence and use the existing deterministic rating mapping. Candidate-safe output excludes hidden scenario configuration, recruiter-only analysis and other participants' private information. Graph failure delays projection, not transactional completion; retries are idempotent.

## Internal implementation checkpoints

1. Onboarding: migrations, strict extraction, shared-parser entry point, private versioned uploads, status/profile/reuse routes, first-login UI, unit/API/storage/concurrency tests.
2. Company knowledge: migrations, management UI/API, version/effective-date validation, bounded retrieval, grounding contracts and tenant/security tests.
3. New intelligence and role-play: core primitives only, AICredits feature slots, typed findings, reusable definitions, state machine, local text adapter, persistence, reports, candidate/recruiter UI and recovery tests.
4. GD: session and invitation transactions, participant lifecycle, text events, deterministic/semantic intelligence, moderator, per-candidate evidence/reports, UI and concurrent/replay/security tests.
5. Hardening: callback/control authorization, RLS/grants, private storage, dependency checks, bounded errors/logs, migration tooling, container readiness and operational documentation.
6. Full verification: existing backend/frontend suites, feature unit/API/security suites, real isolated PostgreSQL migrations/transactions, text end-to-end flows, frontend type/lint/build, protected-file hash comparison, and external checks where safe and available.

## Explicit future scope

New Agora voice rooms/agents, speech timing adapters, semantic embeddings, OCR, PDF report artifacts and AWS deployment are future work. Local text flows must be usable without these. Live provider/database/graph checks must be reported separately from fakes and offline tests; skipped checks are not evidence of a verified integration.

## Reconciled delivery checkpoint: 2026-09-10

The isolated onboarding, company knowledge, role-play and GD text flows are implemented and have passed the API/database/browser checks described in the audit. Six feature migrations were exercised repeatedly against text-ID and UUID-ID test schemas. Live AICredits, private Supabase Storage and AuraDB business-flow checks passed with synthetic records; hosted relational feature migrations have not been applied.

The final offline backend run passed 1,800 tests with 37 conditional skips. Frontend behavior passed 65 tests; types, targeted feature lint, production builds and container checks passed. Repository-wide legacy lint is not clean. One-off browser checks cover first-login/profile replacement, reusable scenario assignment, policy-grounded RP, document versioning/archive, two-candidate GD and individual feedback, including mobile layout checks.

Forty of 41 protected files still match the original hash baseline. The Standard-only graph.py vague-answer/follow-up correction is an explicit exception, not an expansion of the interview orchestrator. The audit explains the regression and test changes. A cold-start removal probe retained the Standard completion routes with all new feature packages unavailable, and a 45-module import check found no direct protected-interview/provider-SDK/Agora-SDK imports in the new domains.

Company knowledge exposes an authorized interview-context endpoint/enricher. It is not automatically injected into protected Standard Interview prompts. RP/GD pin candidate-visible policy sources and expose exact quotations in their UI/reports; new voice remains placeholder-only.

The remaining hosted activation gate is a valid direct/session-pooler PostgreSQL DATABASE_URL for the existing Supabase project, followed by guarded migration application and hosted verification. The current localhost URL and working API keys do not satisfy that gate. No AWS deployment is authorized or performed. See [FEATURE_OPERATIONS.md](FEATURE_OPERATIONS.md) for the operator sequence.
