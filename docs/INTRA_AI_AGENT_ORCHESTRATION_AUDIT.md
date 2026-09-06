# Intra AI — Multi-Agent Voice Interview & Adaptive Orchestration Audit

*Audit Document: docs/INTRA_AI_AGENT_ORCHESTRATION_AUDIT.md*  
*Target System: Intra AI Adaptive Multi-Persona Voice Interview Platform*  
*Repository: Intra AI (`VIsHnu1762/intra-ai`)*
*Mode: Comprehensive Read-Only Technical Audit*

---

## 1. Executive Summary & Core Architectural Philosophy

### 1.1 Product Vision & Core Objective
**Intra AI** is designed as an AI-powered, adaptive voice interview platform that conducts a complete multi-round interview using multiple specialized AI interviewer personas (**Alex** for Technical Architecture, **Jordan** for Product & Customer Impact, extensible to $N$ agents).

The system replaces rigid, pre-generated question scripts with an intelligent, closed-loop conversational engine where:
1. **Candidate CV & Job Description** ground the interview competency model before the call begins.
2. **Agora Agent Studio** provides the real-time voice interface (STT, TTS, Turn Detection, VAD).
3. **Specialized AI Interviewer Personas** conduct natural, real-time voice conversations.
4. **M1 Interview Intelligence** deeply analyzes every answer for technical depth, evidence, missing information, vagueness, and contradictions.
5. **Meta-Orchestrator / LangGraph** dynamically decides the next conversational action (`ASK_QUESTION`, `FOLLOW_UP`, `INCREASE_DIFFICULTY`, `DECREASE_DIFFICULTY`, `SWITCH_AGENT`, `COMPLETE`).
6. **Persistent Knowledge Graph** preserves grounded candidate evidence across conversational turns, agent handoffs, and separate interview rounds.
7. **Final Assessment Engine** synthesizes an evidence-backed scorecard for recruiters.

```
Recruiter Uploads CV + JD
           ↓
Intra AI Builds Candidate Knowledge & Competency Plan
           ↓
Interview Starts (Agora Agent Studio Voice Runtime)
           ↓
Active Interviewer Persona (Alex / Technical)
           ↓
Candidate Speaks Naturally
           ↓
M1 Interview Intelligence Analyzes Answer
           ↓
Meta-Orchestrator (LangGraph) Decides NextAction
           ├── Ask adaptive follow-up
           ├── Increase/decrease difficulty
           ├── Continue with current interviewer
           ├── SWITCH_AGENT → Jordan (Product)
           └── Complete interview
           ↓
Knowledge Graph Stores Grounded Evidence
           ↓
Next Interviewer / Round Hydrates from Shared Knowledge Graph
           ↓
Evidence-Backed Final Assessment & Scorecard
```

---

## 2. Core Architectural Separation of Concerns

The architecture strictly enforces clean separation across **6 distinct subsystems**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           1. AGORA AGENT STUDIO                             │
│  • Real-time WebRTC Audio Transport                                         │
│  • Speech-to-Text (STT) & Text-to-Speech (TTS) Runtime                      │
│  • Voice Activity Detection (VAD) & Turn Detection                          │
│  • NOT the source of truth for long-term candidate memory                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP Webhook / SSE Stream
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                          6. CUSTOM LLM ADAPTER                              │
│  • Bidirectional bridge between Agora Agent Studio and Intra AI             │
│  • Translates candidate transcript into Intra AI turn event                 │
│  • Formats persona responses and metadata for Agora TTS synthesis          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
         ┌─────────────────────────────┴─────────────────────────────┐
         ▼                                                           ▼
┌──────────────────────────────────────┐    ┌─────────────────────────────────┐
│     5. INTERVIEW AI CONTEXT          │    │  4. KNOWLEDGE GRAPH /           │
│     (Short-term Working State)       │    │     PERSISTENT CANDIDATE CONTEXT│
│  • Current Agent (Alex vs Jordan)    │    │     (Long-term Memory)          │
│  • Current Round & Difficulty        │    │  • CV Facts, Skills, Projects   │
│  • Assessed Competencies (Session)   │    │  • Verified Spoken Evidence     │
│  • Open Questions & Turn Count       │    │  • Contradictions & Gaps        │
│  • Authoritative for active turn loop│    │  • Persists across rounds       │
└──────────────────┬───────────────────┘    └────────────────┬────────────────┘
                   │                                         │
         ┌─────────┴─────────┐                               │
         ▼                   ▼                               │
┌──────────────────┐  ┌────────────────────────────────┐     │
│ 2. M1 INTELLIGENCE│  │ 3. META-ORCHESTRATOR /         │     │
│ • AnswerAnalysis │  │    LANGGRAPH                   │     │
│ • Relevance/Depth│  │ • Evaluates NextAction         │     │
│ • Evidence/Gaps  │  │ • Decides Persona Handoff      │     │
│ • Contradictions │  │ • Explainable Rationale        │     │
│ • Does NOT decide│  │ • Supports N Specialized Agents│     │
│   routing        │  └───────────────┬────────────────┘     │
└────────┬─────────┘                  │                      │
         │                            │                      │
         └────────────────────────────┼──────────────────────┘
                                      │
                                      ▼
                      Persona Utterance to Agora TTS
```

### Detailed Subsystem Responsibilities:

| Subsystem | Primary Responsibility | Explicit Boundaries (What it does NOT do) |
|---|---|---|
| **1. Agora Agent Studio** | Real-time voice transport, ultra-low latency STT, turn detection, and audio TTS rendering. | **NOT** candidate memory; does not make evaluation or routing decisions. |
| **2. M1 Interview Intelligence** | Semantic understanding of candidate answers, scoring depth (0–10), extracting evidence snippets, detecting vagueness, off-topic shifts, and CV contradictions. | **NOT** a decision-maker; does not decide which agent speaks next or when to finish. |
| **3. Meta-Orchestrator / LangGraph** | Interview governance state machine. Evaluates competency backlog, decides follow-up vs new topic, adjusts difficulty, executes persona handoffs, and completes the interview. | **NOT** a raw audio processor; consumes structured `M1AnswerAnalysis` and `InterviewAIContext`. |
| **4. Knowledge Graph (Persistent Context)** | Grounded candidate memory linking claims, verified evidence nodes, and cross-round observations. Shared across all interviewer agents. | **NOT** session-specific working scratchpad; holds immutable verified facts. |
| **5. Interview AI Context** | Short-term working state for the active interview round (turn count, current agent, open questions). | **NOT** cross-round storage; discarded or archived upon interview completion. |
| **6. Custom LLM Adapter** | Translates Agora Conversational AI webhook calls into Intra AI turn execution, streaming the active persona's response back to Agora. | **NOT** domain logic; purely a protocol translation and streaming adapter. |

---

## 3. Two-Level Memory Architecture

Intra AI strictly separates **Short-Term Conversational Memory** from **Long-Term Grounded Candidate Memory**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             TWO-LEVEL MEMORY MODEL                          │
│                                                                             │
│  LEVEL 1: SHORT-TERM WORKING MEMORY                                         │
│  ├── Agora conversation buffer (bounded to last 2-4 turns for natural flow)  │
│  └── InterviewAIContext (active round state, current agent, turn counter)   │
│                                                                             │
│  LEVEL 2: LONG-TERM GROUNDED MEMORY (Knowledge Graph)                       │
│  ├── CV Claims (Technologies, Projects, Roles, Claimed Experience)          │
│  ├── Verified Evidence Nodes (Round, Agent, Utterance, Score, Signal)       │
│  ├── Contradiction Nodes (Claimed vs Demonstrated Gaps)                     │
│  └── Competency Progress (Coverage status across rounds)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Critical Memory Principles:
1. **Never Rely on Agora's Bounded History as Long-Term Memory**:
   - Agora Agent Studio maintains a limited conversational context window. As the interview progresses past 10–15 turns, early context is truncated.
   - Intra AI persists every meaningful technical claim, demonstrated competency, and verified evidence snippet directly into the **Knowledge Graph** at each turn.
2. **Grounded Context Injection**:
   - When an agent formulates a question, relevant evidence is retrieved from the Knowledge Graph using semantic competency queries, rather than dumping the entire raw dialogue transcript into the prompt.

---

## 4. Multi-Agent Context Sharing & Persona Handoff

### 4.1 Shared Candidate Context vs Isolated Silos
In Intra AI, interviewer personas (**Alex**, **Jordan**, etc.) do **NOT** operate in isolated memory silos. They all read from and write to the same **Shared Candidate Knowledge Graph**.

```
                           Candidate Profile
                                   │
                     Persistent Knowledge Graph
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
            Alex                 Jordan              Morgan
     (Technical Lead)        (Product Lead)       (Leadership/HR)
```

### 4.2 Forensic Walkthrough of Cross-Agent Persona Handoff

#### Step 1: Alex (Technical Interviewer) Explores Architecture
- **Alex's Prompt Focus**: Distributed systems, API design, scalability trade-offs, concurrency.
- **Alex asks**: *"Tell me how you architected the Payment API at your previous company to handle peak transaction spikes."*
- **Candidate answers**: *"We broke down the monolithic service into microservices, implemented Redis for caching idempotent transaction tokens, and horizontally scaled our FastAPI workers behind an Nginx load balancer."*
- **M1 Intelligence analyzes**:
  - `relevance_score`: 9.0
  - `depth_score`: 8.5
  - `demonstrated_competencies`: `["system_design", "redis_caching", "horizontal_scaling"]`
  - `extracted_evidence`: `[EvidenceNode(id="ev-101", topic="Payment API Scaling", snippet="Implemented Redis for idempotent tokens and scaled FastAPI workers")]`
- **Knowledge Graph update**: `ev-101` is attached to `Candidate.Projects["Payment API"]` and `Competencies["system_design"]`.

#### Step 2: Meta-Orchestrator Triggers `SWITCH_AGENT`
- Meta-Orchestrator inspects `InterviewAIContext`:
  - Technical architecture competency is **sufficiently covered** (Score: 8.5, Evidence count: 2).
  - Target competency backlog requires **Product & Customer Impact** evaluation.
- Meta-Orchestrator returns `NextAction`:
  - `type`: `SWITCH_AGENT`
  - `next_agent_id`: `"jordan"`
  - `target_competency`: `"customer_impact"`
  - `rationale`: *"Technical scalability verified by Alex; transitioning to Jordan for product impact evaluation."*
  - `handoff_context`: `{"previous_agent": "alex", "project": "Payment API", "technical_achievement": "Redis caching & horizontal scaling"}`

#### Step 3: Jordan Takes Over with Grounded Context
- Jordan does **not** receive 20 pages of raw chat logs. Instead, Jordan receives the distilled handoff context:
  - *Context Summary*: Candidate scaled Payment API with Redis and FastAPI workers.
  - *Jordan's Goal*: Assess customer metrics, business downtime reduction, and product trade-offs.
- **Jordan speaks naturally**:
  - *"Hi, I'm Jordan, Product Lead. Alex covered the technical architecture of your Payment API scaling. I'd love to understand the business and customer impact. How did introducing Redis caching improve transaction success rates or checkout latency for your end users?"*

---

## 5. Cross-Round Memory Persistence

```
ROUND 1: Technical Deep Dive (Alex)
    ↓
Candidate answers technical questions
    ↓
M1 extracts technical evidence & scores
    ↓
Written to Persistent Knowledge Graph (PostgreSQL)
    ↓
ROUND 1 COMPLETES
─────────────────────────────────────────────────────────────
(Hours or Days Pass — Session Terminated)
─────────────────────────────────────────────────────────────
ROUND 2: Product & Leadership (Jordan / Morgan)
    ↓
Candidate connects to fresh Agora voice session
    ↓
Fresh InterviewAIContext initialized
    +
Hydrated from Persistent Knowledge Graph (Round 1 evidence loaded)
    ↓
Jordan begins with full awareness of Round 1 findings:
"Welcome back! In your technical round with Alex, you discussed your experience
scaling real-time pipelines. Today, let's explore how you prioritize product roadmap
features when dealing with technical debt..."
```

---

## 6. Subsystem Technical Specifications & Data Contracts

### 6.1 M1 Interview Intelligence Data Schema

```python
class M1AnswerAnalysis(BaseModel):
    """Output produced by M1 semantic analysis of candidate speech turns."""
    relevance_score: float = Field(ge=0.0, le=10.0, description="0-10 score of answer relevance")
    depth_score: float = Field(ge=0.0, le=10.0, description="0-10 score of technical/substantive depth")
    confidence_score: float = Field(ge=0.0, le=10.0, description="0-10 score of communication clarity")
    demonstrated_competencies: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    vagueness_detected: bool = False
    off_topic_detected: bool = False
    detected_contradictions: list[ContradictionItem] = Field(default_factory=list)
    extracted_evidence: list[EvidenceItem] = Field(default_factory=list)
    key_takeaways: str = ""
    suggested_follow_up_topic: str | None = None
```

### 6.2 Meta-Orchestrator NextAction Data Schema

```python
class ActionType(StrEnum):
    ASK_QUESTION = "ASK_QUESTION"
    FOLLOW_UP = "FOLLOW_UP"
    INCREASE_DIFFICULTY = "INCREASE_DIFFICULTY"
    DECREASE_DIFFICULTY = "DECREASE_DIFFICULTY"
    SWITCH_AGENT = "SWITCH_AGENT"
    COMPLETE = "COMPLETE"

class NextAction(BaseModel):
    """Decision output produced by the LangGraph Meta-Orchestrator."""
    type: ActionType
    active_agent_id: str  # e.g., "alex", "jordan"
    next_agent_id: str | None = None
    target_competency: str
    difficulty_level: str = "medium"  # "easy" | "medium" | "hard" | "expert"
    generated_utterance: str  # Spoken text for Agora TTS synthesis
    rationale: str  # Explainable justification for recruiter audit
    handoff_context: dict[str, Any] | None = None
```

### 6.3 Persistent Knowledge Graph Data Schema

```python
class CandidateKnowledgeGraph(BaseModel):
    """Grounded candidate context stored across turns and interview rounds."""
    candidate_id: str
    candidate_name: str
    claims: list[ClaimNode] = Field(default_factory=list)          # From CV
    evidence: list[EvidenceNode] = Field(default_factory=list)      # From Spoken Answers
    contradictions: list[ContradictionNode] = Field(default_factory=list)
    competency_scores: dict[str, CompetencyScore] = Field(default_factory=dict)
    updated_at: str
```

---

## 7. Zero-Overhead Infrastructure Blueprint

### 7.1 Rejection of Unnecessary Heavy Infrastructure
To maintain high reliability, maintainability, and sub-second latency, the following frameworks are **explicitly excluded**:

| Rejected Technology | Reason for Rejection | Intra AI Lightweight Replacement |
|---|---|---|
| **Kafka / RabbitMQ** | Extreme operational complexity and message broker overhead for single-session voice interactions. | Direct async Python asyncio task queues + FastAPI background tasks. |
| **Kubernetes** | Unnecessary orchestration overhead for MVP / early stage deployment. | Docker Compose multi-container architecture. |
| **Dedicated Graph DB (Neo4j / Memgraph)** | Heavyweight JVM/C++ services requiring separate clustering and query drivers. | **PostgreSQL 16 Relational + JSONB Schema** with typed Python graph traversal algorithms. |
| **TEN Framework / Complex RTC Middleware** | Proprietary C++ runtime layers adding debugging friction. | **Agora Conversational AI / Agent Studio** direct WebRTC client + Custom LLM Adapter webhook. |

---

## 8. Baseline Forensic Assessment

### 8.1 Reusable ATS Assets (KEEP)
- **Recruiter Admin Dashboard** (`frontend/src/app/admin/dashboard/page.tsx`): Greenhouse-style KPI cards and recent interview views.
- **Candidate Pipeline Kanban Board** (`frontend/src/app/admin/candidates/page.tsx`): 5-stage pipeline management (`applied` $\rightarrow$ `shortlisted` $\rightarrow$ `scheduled` $\rightarrow$ `in_progress` $\rightarrow$ `completed`).
- **Job Creation & Round Setup Wizard** (`frontend/src/app/admin/jobs/new/page.tsx`): Multi-round configurator for technical, behavioral, and product stages.
- **Public Job Board & Application Flow** (`frontend/src/app/(public)/jobs/`): Clean candidate application wizard with resume upload.
- **Candidate Portal & Calendar Scheduling** (`frontend/src/app/(candidate)/portal/` & `schedule/`): Self-service slot booking.
- **Database Schema Foundation** (`docker/init-db/01-init.sql`): 19 well-structured relational tables covering core ATS entities.

### 8.2 Legacy Components to Replace / Extend (REPLACE / EXTEND)
- **Simulated Interview Room** (`frontend/src/app/(candidate)/interview/[token]/page.tsx`):
  - Current state: Mock timer and static question toggling.
  - Target state: Agora Web RTC SDK client with dynamic persona badges (**Alex** vs **Jordan**), live wave visualizer, and realtime transcript.
- **Monolithic GPT-4o Client** (`backend/app/integrations/openai_client.py`):
  - Current state: Single-turn stateless prompt completions.
  - Target state: Modular **M1 Interview Intelligence** and **LangGraph Meta-Orchestrator**.

---

## 9. Latency-Optimized Execution Path

To ensure the conversational voice experience feels completely natural with **< 800ms response latency**, Intra AI isolates the critical audio path from background knowledge persistence:

```
[Candidate Finishes Speaking]
         │
         ▼ (Realtime Critical Path — Target: < 600ms)
Agora STT Transcribes Utterance
         ↓
Custom LLM Adapter Receives Webhook
         ↓
FastAPI invokes Meta-Orchestrator (LangGraph Turn Decision)
         ↓
Persona Streams Spoken Response Tokens (SSE)
         ↓
Agora TTS Synthesizes Audio & Plays to Candidate Speakers

─────────────────────────────────────────────────────────────
         ▼ (Asynchronous Background Path — Off Critical Path)
M1 Executes Deep Semantic AnswerAnalysis
         ↓
Knowledge Graph Ingests Evidence & Contradiction Nodes
         ↓
PostgreSQL Stores Graph State & Audit Log
```

---

## 10. Audit Conclusions & Success Criteria Verification

### 10.1 Success Criteria Scorecard

| Success Criterion | Architectural Mechanism | Verification Status |
|---|---|---|
| **1. Dynamic, Non-Scripted Questions** | Meta-Orchestrator generates questions per turn based on remaining competency gaps. | **VERIFIED DESIGN** |
| **2. Answer-Influenced Trajectory** | M1 `AnswerAnalysis` informs Meta-Orchestrator difficulty shift and follow-up prompts. | **VERIFIED DESIGN** |
| **3. Real-Time Adaptive Difficulty** | LangGraph branches to harder or simpler topics based on cumulative score. | **VERIFIED DESIGN** |
| **4. Dynamic Persona Switching** | `SWITCH_AGENT` action transitions active speaker between Alex and Jordan. | **VERIFIED DESIGN** |
| **5. Shared Candidate Context** | Unified Knowledge Graph provides grounding data to all personas without raw transcript dumps. | **VERIFIED DESIGN** |
| **6. Cross-Turn Persistence** | Evidence nodes written to PostgreSQL at every turn. | **VERIFIED DESIGN** |
| **7. Cross-Round Candidate Memory** | Round 2 hydrates from persistent candidate Knowledge Graph created in Round 1. | **VERIFIED DESIGN** |
| **8. Evidence-Backed Scorecards** | Final report links every score to specific speech evidence snippets (`ev-XXX`). | **VERIFIED DESIGN** |
| **9. Explainable Decision Rationale** | Every `NextAction` includes a human-readable `rationale` string for recruiter audit. | **VERIFIED DESIGN** |
| **10. Low-Latency Voice Experience** | Agora Conversational AI powers the audio runtime with critical-path separation. | **VERIFIED DESIGN** |

### 10.2 Final Audit Verdict
**The Intra AI multi-agent architecture is sound, modular, and completely feasible.** The ATS frontend and database layer combine with Agora Agent Studio and the M1/LangGraph/Knowledge-Graph backend to deliver an adaptive multi-persona voice interview experience without unnecessary infrastructure.
