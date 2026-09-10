# Intra AI — Long-Run Feature Implementation Task

You are working on the existing Intra AI repository.

Your task is to extend the CURRENT Intra AI system with the new capabilities defined in `objective.md`.

The most important requirement is:

> Build the new capabilities as clean, isolated feature domains without breaking or unnecessarily modifying the existing working Standard Interview system.

This is a long-running implementation task.

Do not rush into implementation.
First inspect and understand the complete repository, reconcile the existing implementation against `objective.md`, then implement the missing capabilities end-to-end.

---

# 1. NON-NEGOTIABLE ARCHITECTURAL PRINCIPLE

The existing Standard Interview system is already working.

Treat it as a STABLE PRODUCTION COMPONENT.

The existing Standard Interview stack includes:

- Interview Intelligence / M1
- InterviewAIContext
- AgentTurnContext
- Standard Interview Meta-Orchestrator
- LangGraph interview routing
- `NextAction`
- existing interviewer personas/agents
- existing interview session lifecycle
- existing Agora voice architecture
- AICredits integration
- Supabase/PostgreSQL
- Neo4j candidate memory
- existing evidence pipeline
- existing reporting pipeline

DO NOT redesign these systems to accommodate the new features.

DO NOT turn them into universal systems.

DO NOT modify them simply because the new features need similar functionality.

If an existing component genuinely needs a backward-compatible integration change, make the smallest possible change and verify the existing Standard Interview regression suite afterward.

---

# 2. EXISTING STANDARD INTERVIEW MUST REMAIN ISOLATED

The existing interview flow remains:

Candidate
    ↓
Existing Interview Intelligence / M1
    ↓
InterviewAIContext
    ↓
Existing Meta-Orchestrator
    ↓
`NextAction`
    ↓
Existing Interview Agent / Voice flow

This architecture is already working.

Do not change the semantics of this flow.

In particular:

DO NOT:

- expand `NextAction` for GD
- expand `NextAction` for Role Play
- add GD actions to the interview orchestrator
- add Role-Play actions to the interview orchestrator
- make the existing LangGraph orchestrator understand every feature
- rewrite M1 into a universal evaluator
- move existing interview logic into a new generic framework
- replace the existing M1
- replace the existing interview orchestrator

The new features must live beside this system.

---

# 3. NEW FEATURE ARCHITECTURE

Create a separate feature architecture for:

1. Candidate Resume/CV Onboarding
2. Company Knowledge / Policy Grounding
3. Role Play / Behavioral Simulation
4. AI-Moderated Group Discussion
5. Production Hardening

These are separate capabilities.

They must NOT become one giant feature.

Use feature-oriented architecture.

Conceptually:

                    INTRA AI
                       |
          +------------+-------------+
          |                          |
          v                          v
 EXISTING INTERVIEW STACK       NEW FEATURE STACK
          |                          |
          |                   Intelligence Layer
          |                          |
          |              +-----------+-----------+
          |              |           |           |
          |              v           v           v
          |          Role Play       GD      Company Grounding
          |          Intelligence Intelligence Intelligence
          |              |           |
          |              v           v
          |       RolePlay       GD Moderator
          |       Orchestrator
          |
          v
      NextAction

Shared platform infrastructure may be reused underneath:

- AICredits
- Supabase/PostgreSQL
- Neo4j
- storage abstraction
- authentication
- authorization
- evidence infrastructure
- reporting infrastructure
- context primitives
- structured-output validation
- logging/observability

But feature-specific domain logic must remain isolated.

---

# 4. NEW INTELLIGENCE LAYER

Create a NEW Intelligence Layer for the new capabilities.

This is NOT a replacement for existing Interview Intelligence / M1.

Existing M1 remains responsible for the existing Standard Interview evaluation path.

The new Intelligence Layer should support feature-specific intelligence.

Conceptually:

backend/app/intelligence/

    core/
        contracts.py
        findings.py
        evidence.py
        context.py
        structured_output.py

    role_play/
        analyzer.py
        evaluator.py
        signals.py

    group_discussion/
        analyzer.py
        evaluator.py
        signals.py

    company/
        grounding.py
        evaluator.py

Only genuinely reusable intelligence primitives belong in `core`.

Feature-specific reasoning belongs in its feature module.

Do not create a universal intelligence class containing:

    if feature == "interview"
    elif feature == "role_play"
    elif feature == "gd"

etc.

---

# 5. INTELLIGENCE VS ORCHESTRATION

Keep these responsibilities separate.

INTELLIGENCE:

> What do we understand about what just happened?

ORCHESTRATION:

> Given the current state and intelligence, what should happen next?

NLG/RESPONSE GENERATION:

> How should that decision be expressed naturally?

The architecture should be:

Candidate turn/event
    ↓
Feature Intelligence
    ↓
Structured findings/signals
    ↓
Feature Orchestrator
    ↓
Typed domain action
    ↓
Response generation
    ↓
Voice/output adapter

The LLM must NOT be the authoritative source of application state.

Authoritative state transitions must be validated and controlled by backend domain logic.

---

# 6. M1 IS NOT THE NEW UNIVERSAL INTELLIGENCE LAYER

Existing M1 is working.

Do not modify it into a universal:

- GD evaluator
- Role-Play evaluator
- behavioral intelligence engine
- moderation engine
- universal orchestrator

For new features, implement feature-specific intelligence inside the NEW Intelligence Layer.

Existing evidence/reporting/KG infrastructure can be reused.

If genuinely reusable low-level contracts are required, expose clean interfaces rather than importing M1 internals.

For example:

- `IntelligenceFinding`
- `EvidenceSignal`
- `CompetencySignal`

may be shared if appropriate.

But do not make the new feature stack dependent on M1's internal implementation.

---

# 7. AICREDITS — SINGLE LLM PROVIDER ARCHITECTURE

AICredits is the LLM provider architecture.

Preserve it.

All new LLM reasoning must use the existing AICredits integration.

DO NOT:

- introduce Groq
- introduce a separate Gemini provider
- replace AICredits
- create direct provider clients inside features
- create parallel LLM infrastructure

New features may have separate model/configuration slots while still using AICredits.

Model selection must remain configuration-driven through the existing AICredits architecture.

The feature decides what reasoning is required.

The AICredits infrastructure handles the provider call.

---

# 8. AGORA — PLACEHOLDER ONLY FOR NEW FEATURES

IMPORTANT:

For the NEW Group Discussion and Role-Play features, Agora realtime integration is NOT to be fully implemented yet.

Treat Agora as a PLACEHOLDER / ADAPTER BOUNDARY for now.

Do NOT:

- redesign the existing Agora architecture
- modify existing Standard Interview Agora behavior
- implement new GD Agora rooms
- implement new Role-Play Agora rooms
- modify ASR/TTS/VAD/RTC/RTM behavior
- modify the existing Agora Agent Studio configuration unnecessarily
- build feature-specific Agora SDK logic throughout the domain layer

Instead, create clean domain-level interfaces/adapters where future realtime integration will plug in.

For example:

    VoiceSessionAdapter
    VoiceEventAdapter
    RealtimeSessionAdapter

The feature domain should depend on these interfaces, not Agora SDK types.

For now, provide a safe placeholder/mock/local implementation where necessary so the feature can be developed and tested without requiring new Agora functionality.

Future architecture:

Role Play
    ↓
VoiceSessionAdapter
    ↓
Agora implementation later

GD
    ↓
VoiceSessionAdapter
    ↓
Agora implementation later

The existing Standard Interview Agora implementation must remain untouched unless a backward-compatible shared abstraction is absolutely necessary.

---

# 9. DATABASE ARCHITECTURE

Supabase/PostgreSQL remains the system of record.

Neo4j remains the candidate-memory/evidence graph projection.

Do NOT introduce another primary database.

Do NOT introduce another candidate memory store.

Do NOT use an in-process dictionary as authoritative state for critical workflows.

All important state must be persisted and recoverable.

New feature migrations must be isolated and clean.

---

# 10. FEATURE 1 — CANDIDATE RESUME/CV ONBOARDING

Create an independent:

    candidate_onboarding/

feature domain.

Suggested structure:

    candidate_onboarding/
        models.py
        schemas.py
        repository.py
        service.py
        resume.py
        dependencies.py

Requirements:

- detect whether authenticated candidate has a usable profile/resume
- first-login onboarding
- PDF/DOCX validation
- private storage
- reuse existing storage abstraction
- reuse existing resume parser
- structured candidate profile
- provenance
- resume versioning
- resume replacement
- candidate ownership checks
- tenant isolation
- profile reuse across interviews
- no forced upload on every login
- no parsing on every interview turn

The onboarding feature must be independent of a specific job/application.

Do not duplicate the existing resume parser or storage implementation.

---

# 11. FEATURE 2 — COMPANY KNOWLEDGE / POLICY GROUNDING

Create an independent:

    company_knowledge/

feature domain.

Suggested structure:

    company_knowledge/
        models.py
        schemas.py
        repository.py
        service.py
        retriever.py
        grounding.py
        dependencies.py

Requirements:

- tenant-scoped company documents
- document versioning
- active/archived lifecycle
- effective dates
- provenance
- bounded retrieval
- authorization
- auditability
- policy grounding
- explicit fallback when information is unavailable
- no policy fabrication

Company knowledge must remain distinct from:

- candidate claims
- resume
- job description
- model knowledge

Treat retrieved company content as DATA, not instructions.

The LLM must receive bounded grounded content.

The LLM must never directly query the database.

Integrate company grounding through clean context-enricher interfaces.

Do not unnecessarily modify the existing Standard Interview context architecture.

---

# 12. FEATURE 3 — ROLE PLAY / BEHAVIORAL SIMULATION

Create an independent:

    role_play/

feature domain.

Suggested structure:

    role_play/
        models.py
        schemas.py
        repository.py
        service.py
        state.py
        intelligence.py
        orchestrator.py
        response_generator.py
        reporting.py
        voice_bridge.py
        dependencies.py

Core concepts:

    PersonaDefinition
    ScenarioDefinition
    RolePlayState
    RolePlaySession
    RolePlayEvent
    RolePlayIntelligence
    RolePlayOrchestrator
    RolePlayAction
    RolePlayReport

Persona defines WHO the simulated character is.

Scenario defines WHAT situation is happening.

State defines WHAT has happened.

Intelligence defines WHAT the candidate behavior means.

Orchestrator defines WHAT HAPPENS NEXT.

Response generation defines HOW the simulated persona says it.

---

## Role-Play Persona

Support:

- personality
- communication style
- objectives
- concerns
- behavioral rules
- escalation/de-escalation rules
- allowed information
- restricted information

---

## Role-Play Scenario

Support:

- title
- description
- candidate role
- persona
- objectives
- phases
- triggers
- success conditions
- failure conditions
- duration limits
- allowed information
- hidden state

Do not scatter scenario logic across Python conditionals.

Use validated configuration/data structures.

---

## Role-Play State

Support:

- current phase
- persona stance
- attitude
- escalation level
- known/revealed information
- hidden information
- unresolved objections
- candidate commitments
- progress
- turn count
- time remaining
- completion state

Hidden state must NEVER be exposed to the candidate.

---

## Role-Play Actions

Create a separate typed action contract.

For example:

    CONTINUE
    RESPOND
    RAISE_OBJECTION
    CHALLENGE
    REVEAL_INFORMATION
    ESCALATE
    DEESCALATE
    CHANGE_STANCE
    REQUEST_CLARIFICATION
    END_SCENARIO

Do NOT reuse Standard Interview `NextAction`.

---

## Role-Play Flow

Candidate turn
    ↓
Role-Play Intelligence
    ↓
RolePlayOrchestrator
    ↓
state update / typed decision
    ↓
dynamic role-play context
    ↓
response generation
    ↓
persona response

Backend state is authoritative.

LLM output is not authoritative state.

Use deterministic rules wherever possible.

Use AICredits only where LLM reasoning is actually necessary.

---

# 13. FEATURE 4 — AI-MODERATED GROUP DISCUSSION

Create an independent:

    group_discussion/

feature domain.

Suggested structure:

    group_discussion/
        models.py
        schemas.py
        repository.py
        service.py
        lifecycle.py
        signals.py
        intelligence.py
        moderator.py
        reporting.py
        voice_bridge.py
        dependencies.py

GD is a shared multi-human session.

Conceptually:

Candidate A \
Candidate B  \
Candidate C   ---> Shared GD Session ---> AI Moderator
Candidate D  /

Create:

    GDSession
    GDParticipant
    GDParticipantState
    DiscussionEvent
    GDIntelligence
    GDModerator
    GDModeratorAction
    GDReport

---

## GD Deterministic Intelligence

Calculate objective signals without unnecessary LLM usage.

Examples:

- speaking duration
- speaking frequency
- participation balance
- silence
- interruptions
- turn imbalance
- response-to-other-participants
- topic deviation
- time remaining
- discussion progress

Do not use an LLM to calculate basic timing/counting signals when deterministic data is available.

---

## GD Semantic Intelligence

Use AICredits when semantic reasoning is required.

Examples:

- argument quality
- counterargument quality
- topic relevance
- collaboration
- communication
- listening/responding
- leadership
- semantic interruption context

---

## GD Moderator Actions

Create a dedicated typed action contract.

For example:

    START_DISCUSSION
    INTRODUCE_TOPIC
    INVITE_PARTICIPANT
    ENCOURAGE_PARTICIPATION
    REDIRECT_DISCUSSION
    MANAGE_INTERRUPTION
    ASK_CLARIFICATION
    CHALLENGE_ARGUMENT
    INTRODUCE_NEW_ANGLE
    REQUEST_RESPONSE
    WARN_TIME
    REQUEST_CONCLUSION
    END_DISCUSSION
    CONTINUE

Do NOT modify or reuse Standard Interview `NextAction`.

---

## GD Flow

Discussion event
    ↓
GD deterministic signals
    ↓
GD semantic intelligence where needed
    ↓
GD Moderator
    ↓
typed moderator action
    ↓
moderator response generation
    ↓
discussion continues

The moderator's decision and the moderator's wording must be separate responsibilities.

---

# 14. GD INDIVIDUAL REPORTING

Do NOT reduce the GD to one group score.

Generate an individual report for each participant.

Possible dimensions:

- participation
- communication
- collaboration
- listening/responding
- leadership
- argument quality
- counterargument quality
- topic relevance
- interruption behavior
- strengths
- weaknesses
- competency findings

Important findings must have provenance to:

- candidate
- GD session
- participant
- event/turn
- timestamp
- transcript/evidence
- competency

Reuse the existing Evidence/KG/reporting infrastructure.

Do not create a second evidence system.

---

# 15. EVIDENCE AND KNOWLEDGE GRAPH

Reuse the existing evidence architecture.

Do NOT create a parallel evidence store.

New evidence must maintain provenance.

Role Play evidence should be associated with:

- candidate
- session
- scenario
- phase
- event/turn
- action
- competency

GD evidence should be associated with:

- candidate
- session
- participant
- event/turn
- timestamp
- competency

Extend Neo4j mappings carefully.

Do not break existing candidate graph queries.

Supabase/PostgreSQL remains authoritative.

Neo4j remains the projection/memory/evidence graph.

---

# 16. REPORTING

Reuse the existing reporting infrastructure where possible.

New report types should remain clearly separated:

- Role Play report
- GD individual participant report
- relevant company-policy/grounding findings
- candidate onboarding/profile information where required

Reports must distinguish between:

- observation
- evidence
- inference
- rating/score

Never fabricate evidence.

---

# 17. SECURITY

Security must be implemented at feature boundaries.

Every new feature must enforce:

- authentication
- authorization
- tenant isolation
- candidate ownership
- resource-level authorization
- session ownership
- safe token handling
- auditability

GD invitation tokens must:

- use high entropy
- be securely stored/hashed where appropriate
- expire
- be bound to the correct session
- be bound to intended participant where applicable
- not contain candidate IDs
- never be logged
- enforce reuse/consumption rules

Role-play hidden state must never leak.

Company documents must not cross tenants.

Resume files must remain private.

Do not expose credentials or tokens in logs.

---

# 18. API ORGANIZATION

Give each feature its own route namespace.

Examples:

    /api/v1/candidate/onboarding/...
    /api/v1/company-knowledge/...
    /api/v1/roleplay/...
    /api/v1/group-discussions/...

Keep feature-specific endpoints in feature-specific route modules.

Use typed request/response schemas.

Validate all state transitions server-side.

Do not put unrelated feature logic into existing interview route files.

---

# 19. FRONTEND ORGANIZATION

Use feature-oriented frontend structure.

For example:

frontend/src/features/

    candidate-onboarding/
        components/
        hooks/
        api/
        types/
        state/

    company-knowledge/
        components/
        hooks/
        api/
        types/

    role-play/
        components/
        hooks/
        api/
        types/
        state/

    group-discussion/
        components/
        hooks/
        api/
        types/
        state/

Only genuinely reusable UI should live in global shared components.

Do not spread feature-specific state or logic across unrelated pages.

---

# 20. DATABASE MIGRATIONS

Inspect all existing migrations before creating new ones.

Do not duplicate existing tables.

Create isolated migrations for each feature using the repository's established migration convention.

Every migration should include appropriate:

- foreign keys
- constraints
- indexes
- tenant scoping
- RLS/grants
- timestamps
- lifecycle fields
- uniqueness constraints
- audit fields where required

---

# 21. PERSISTENCE AND STATE

Critical state must survive process restarts.

Do not rely on:

    global dictionaries
    in-memory session maps
    process-local authoritative state

for:

- GD sessions
- GD participants
- GD state
- Role-Play state
- invitation consumption
- scenario progression

Use PostgreSQL persistence.

Neo4j is a projection, not the transactional source of truth.

State transitions should be transactionally safe and idempotent where external events may retry.

---

# 22. TESTING

Every new feature requires unit + integration + security tests.

Candidate onboarding:

- first-login detection
- upload validation
- PDF/DOCX handling
- parsing
- persistence
- replacement
- candidate isolation
- profile reuse

Company knowledge:

- tenant isolation
- versioning
- active/archived filtering
- effective date resolution
- provenance
- missing policy
- ambiguous policy
- conflicting versions

Role Play:

- persona validation
- scenario validation
- state transitions
- hidden-state isolation
- escalation/de-escalation
- action validation
- reconnect/recovery
- structured AICredits output
- evidence traceability
- reporting

Group Discussion:

- session lifecycle
- participant lifecycle
- invite security
- token expiry/reuse
- event ingestion
- deterministic signals
- interruption handling
- participation balance
- moderator decisions
- participant isolation
- concurrent events
- reconnect/recovery
- individual reports
- evidence traceability

Regression:

The existing Standard Interview test suite MUST continue to pass.

---

# 23. AGORA TESTING FOR NEW FEATURES

Because Agora integration is a placeholder for now:

New GD and Role-Play tests should be able to run without a live Agora environment.

Use:

- domain-level voice interfaces
- mocks/fakes
- deterministic local adapters

Do not require live Agora rooms to verify the core domain logic.

The future Agora implementation should be replaceable behind the adapter boundary.

---

# 24. PRODUCTION HARDENING

After the features are implemented, harden the system without redesigning existing architecture.

Review:

- authentication
- authorization
- tenant isolation
- callback verification
- token security
- custom LLM authentication
- route-level permissions
- migration discipline
- health/readiness
- structured logging
- error handling
- retry policies
- idempotency
- persistent state
- graceful shutdown
- dependency failure handling
- storage security

Do not perform AWS deployment unless explicitly requested.

The architecture should remain AWS-ready, but deployment itself is not the current objective.

---

# 25. IMPLEMENTATION ORDER

Follow this order.

## Phase 0 — Repository Reconciliation

Before modifying code:

1. Inspect the complete repository.
2. Read `objective.md` completely.
3. Inspect existing migrations.
4. Inspect existing Standard Interview architecture.
5. Inspect M1.
6. Inspect Meta-Orchestrator.
7. Inspect InterviewAIContext.
8. Inspect AgentTurnContext.
9. Inspect AICredits.
10. Inspect Agora.
11. Inspect Supabase/PostgreSQL.
12. Inspect Neo4j.
13. Inspect evidence.
14. Inspect reporting.
15. Inspect resume/storage.
16. Inspect frontend.
17. Inspect tests.

Produce an internal reconciliation containing:

    ALREADY IMPLEMENTED
    PARTIALLY IMPLEMENTED
    MISSING
    REUSABLE
    REQUIRES MODIFICATION
    DO NOT TOUCH
    OPTIONAL/FUTURE

Do not duplicate existing functionality.

---

## Phase 1 — Candidate Onboarding

Implement completely.

Verify.

Run tests.

---

## Phase 2 — Company Knowledge

Implement completely.

Verify.

Run tests.

---

## Phase 3 — New Intelligence Layer + Role Play

First establish the clean Intelligence Layer.

Then implement Role Play using:

    RolePlayIntelligence
    RolePlayOrchestrator
    RolePlayAction

Do not touch Standard Interview M1/orchestration unless absolutely necessary.

Verify.

Run tests.

---

## Phase 4 — Group Discussion

Implement:

    GDIntelligence
    deterministic signal engine
    GDModerator
    GDModeratorAction
    GD session lifecycle
    participant lifecycle
    individual reporting

Keep Agora integration as a placeholder/adapter.

Verify.

Run tests.

---

## Phase 5 — Production Hardening

Harden security, persistence, migrations, health, errors, logging, etc.

Do not destabilize the existing interview system.

---

## Phase 6 — Full Regression

Run the full relevant test suite.

Verify:

- Standard Interview
- Candidate Onboarding
- Company Knowledge
- Role Play
- Group Discussion
- Evidence
- KG
- Reporting
- APIs
- authorization
- persistence

Fix regressions before completion.

---

# 26. FEATURE ISOLATION TEST

The architecture must satisfy:

If Group Discussion is removed:
    Standard Interview still works.

If Role Play is removed:
    Standard Interview still works.

If Company Knowledge is disabled:
    Standard Interview still works using its existing behavior.

If the NEW Intelligence Layer is disabled:
    Existing Standard Interview M1 + orchestrator still work.

If Candidate Onboarding is disabled:
    Existing application/interview behavior must not be unnecessarily destroyed.

Each feature should be independently understandable and removable.

---

# 27. CODE QUALITY RULES

Prefer:

- small focused modules
- explicit interfaces
- typed contracts
- dependency injection
- feature-local business logic
- deterministic state machines where appropriate
- clear repositories
- clear service boundaries
- explicit authorization
- explicit provenance

Avoid:

- giant service classes
- universal orchestrators
- universal intelligence engines
- universal feature services
- circular dependencies
- hidden global state
- feature-specific conditionals inside shared infrastructure
- copying existing implementations
- direct Agora SDK usage in domain logic
- direct LLM provider calls from feature modules

The code should be understandable by another engineer without needing to trace the entire application.

---

# 28. DEFINITION OF DONE

Do not declare a feature complete because:

- database tables exist
- models exist
- endpoints exist
- frontend exists
- tests compile

A feature is complete only when the relevant end-to-end flow works.

For example:

    input
      ↓
    API/session
      ↓
    domain state
      ↓
    intelligence
      ↓
    orchestrator
      ↓
    AICredits where required
      ↓
    response generation
      ↓
    persistence
      ↓
    evidence
      ↓
    KG
      ↓
    reporting
      ↓
    frontend

with failure cases and authorization verified.

For GD/Role Play, realtime voice must stop at the adapter/placeholder boundary for this implementation phase.

---

# 29. FINAL ARCHITECTURE AUDIT

At the end provide a final audit containing:

1. Existing components that were intentionally left untouched.
2. New feature domains created.
3. New Intelligence Layer structure.
4. How existing M1 remains isolated.
5. How existing Standard Interview orchestration remains isolated.
6. How Role Play has its own intelligence + orchestrator + actions.
7. How GD has its own intelligence + moderator + actions.
8. How Company Knowledge remains independent.
9. How Candidate Onboarding remains independent.
10. How AICredits is reused.
11. How Agora is currently only an adapter/placeholder for new features.
12. How Supabase/PostgreSQL is used.
13. How Neo4j is used.
14. How evidence and reporting are reused.
15. Security changes.
16. Migration changes.
17. Frontend changes.
18. Tests executed and results.
19. Existing regressions, if any.
20. Remaining limitations.

---

# FINAL DIRECTIVE

Build NEW capabilities around the existing system.

Do not rebuild the existing system around the new capabilities.

The existing Standard Interview M1 + Meta-Orchestrator is working and must remain stable.

The NEW Intelligence Layer is separate.

Role Play has its own intelligence and orchestrator.

Group Discussion has its own intelligence and moderator.

Company Knowledge has its own grounding domain.

Candidate Onboarding has its own onboarding domain.

AICredits remains the LLM provider.

Supabase/PostgreSQL remains the system of record.

Neo4j remains the graph/memory projection.

Agora remains the existing realtime architecture, while NEW GD/Role-Play Agora integration is only a clean placeholder/adapter boundary for now.

Use composition and explicit interfaces.

Keep feature code clean, modular, testable, and removable.

Do not create a monolith.

Do not break working functionality.

Implement each capability end-to-end, verify it, and only then move to the next phase.