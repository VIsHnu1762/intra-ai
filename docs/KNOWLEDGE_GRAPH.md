# Intra AI Knowledge Graph Foundation

## 1. Overview & Architectural Role

Intra AI uses a dual-database architecture:

* **Supabase / PostgreSQL = System of Record**:
  Primary operational datastore. Manages candidate accounts, authentication, interview tokens, session metadata, billing, and raw transcript logs.
* **Neo4j AuraDB = Knowledge Graph / Candidate Memory Projection**:
  Dedicated projection layer storing structured, multi-round candidate knowledge (skills, projects, technologies, and atomic behavioral/technical evidence).

```
   ┌──────────────────────────────────────────────────────────────┐
   │                     PostgreSQL / Supabase                    │
   │               (Operational System of Record)                 │
   │       Candidates, Sessions, Tokens, Transcripts, Auth        │
   └──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼ (asymmetric background projection)
   ┌──────────────────────────────────────────────────────────────┐
   │                       Neo4j AuraDB                           │
   │               (Knowledge Graph Projection)                   │
   │      Skills, Projects, Technologies, Evidence, Provenance    │
   └──────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Live Path Boundary**:
> The Knowledge Graph does **NOT** determine live interview routing.
> - **M1 Interview Intelligence** analyzes candidate answers turn-by-turn.
> - **Meta-Orchestrator** determines agent handoffs and interview routing.
> - **Knowledge Graph** persistently captures cumulative candidate context across interview turns and rounds for cross-round evaluation and deep context retrieval.

---

## 2. Core Domain Entities

All nodes are typed using Pydantic models in `backend/app/knowledge_graph/models.py`. Every entity enforces a unique stable identifier.

| Entity | ID Field | Description | Key Attributes |
|---|---|---|---|
| `Candidate` | `candidate_id` | Root candidate node | `name`, `email`, `created_at`, `metadata` |
| `InterviewRound` | `round_id` | Interview session round | `interview_id`, `candidate_id`, `round_type`, `status` |
| `Question` | `question_id` | Spoken interview question | `round_id`, `agent_id`, `competency`, `question_text`, `difficulty` |
| `Answer` | `answer_id` | Transcribed candidate response | `question_id`, `candidate_id`, `round_id`, `answer_text`, `duration_seconds` |
| `Evidence` | `evidence_id` | Atomic evaluated evidence | `answer_id`, `candidate_id`, `round_id`, `source_agent_id`, `competency`, `signal`, `score`, `timestamp` |
| `Competency` | `competency_id` | Evaluated competency benchmark | `name`, `category`, `description` |
| `Project` | `project_id` | Candidate portfolio / work project | `candidate_id`, `name`, `description` |
| `Technology` | `technology_id` | Tool, library, or framework | `name`, `category` |
| `Skill` | `skill_id` | Technical or behavioral capability | `name`, `category` |

---

## 3. Strict Provenance Tracking

Candidate knowledge must never be created as detached "facts" without an origin.
Every `Evidence` item enforces strict provenance attributes via Pydantic validators:

```python
class Evidence(BaseModel):
    evidence_id: str        # Unique identifier
    answer_id: str          # Originating answer
    candidate_id: str       # Associated candidate
    round_id: str           # Round in which evidence was gathered
    source_agent_id: str    # Agent who elicited the evidence (e.g. 'alex', 'jordan')
    competency: str         # Competency being evaluated
    signal: str             # Concrete behavioral/technical observation
    score: Optional[float]  # 0.0 - 10.0 score
    timestamp: datetime     # When observation was recorded
```

Empty strings or missing provenance values are rejected at validation time before reaching the database.

---

## 4. Canonical Relationship Vocabulary

Relationships are strictly controlled via `GraphRelationshipType` and verified against `ALLOWED_RELATIONSHIPS`:

```
Candidate
  ├── PARTICIPATED_IN ──> InterviewRound
  │                          ├── HAS_QUESTION ──> Question
  │                          │                       ├── HAS_ANSWER ──> Answer
  │                          │                       └── TARGETS_COMPETENCY ──> Competency
  │                          └── HAS_ANSWER ────> Answer
  │                                                  └── SUPPORTED_BY ──> Evidence
  │                                                                         └── SUPPORTS_COMPETENCY ──> Competency
  ├── HAS_PROJECT ──────> Project
  │                          ├── USES_TECHNOLOGY ──> Technology
  │                          └── DEMONSTRATES_SKILL ──> Skill
  ├── HAS_SKILL ────────> Skill
  ├── KNOWS_TECHNOLOGY ─> Technology
  └── HAS_EVIDENCE ─────> Evidence
```

Callers cannot supply arbitrary relationship names or connect incompatible node types. Attempting to create an invalid relationship raises `RelationshipValidationError`.

---

## 5. Repository Abstraction

All application access to the Knowledge Graph is encapsulated behind the `KnowledgeGraphRepository` interface (`backend/app/knowledge_graph/repository.py`):

* `upsert_candidate(candidate: Candidate) -> Candidate`
* `upsert_interview_round(round_data: InterviewRound) -> InterviewRound`
* `upsert_question(question: Question) -> Question`
* `upsert_answer(answer: Answer) -> Answer`
* `upsert_evidence(evidence: Evidence) -> Evidence`
* `upsert_competency(competency: Competency) -> Competency`
* `upsert_project(project: Project) -> Project`
* `upsert_technology(technology: Technology) -> Technology`
* `upsert_skill(skill: Skill) -> Skill`
* `create_relationship(relationship: GraphRelationship) -> GraphRelationship`
* `get_candidate(candidate_id: str) -> Optional[Candidate]`
* `get_entity_by_id(label: str, entity_id: str) -> Optional[dict]`
* `get_candidate_graph(candidate_id: str, depth: int = 1) -> CandidateGraphResponse`
* `verify_connectivity() -> bool`
* `close() -> None`

### Implementations:
1. **`InMemoryKnowledgeGraphRepository`**: Complete in-memory graph used for automated tests and offline local development without external dependencies.
2. **`Neo4jKnowledgeGraphRepository`**: Production implementation targeting Neo4j AuraDB.

### Query Safety & Parameterization
- **No string interpolation of user data:** All user content, question text, signals, and properties are passed strictly as query parameters (`$id`, `$props`, `$candidate_id`).
- **Whitelisted labels & relationship types:** Labels and relationship types are checked against internal enums before query formatting.

---

## 6. Environment Configuration

Add the following placeholders to your environment or `backend/.env`:

```bash
# Neo4j AuraDB Configuration
NEO4J_URI=neo4j+s://<your-instance-id>.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<your-instance-password>
NEO4J_DATABASE=neo4j
```

> [!WARNING]
> Never commit real Neo4j credentials to git, frontend code, or log files.
> If credentials are not configured, the rest of the application (M1, Agora, Fast Path) continues running normally without failure.

---

## 7. Schema Initialization (Constraints & Indexes)

Uniqueness constraints and lookup indexes are declared idempotently (`IF NOT EXISTS`) in `backend/app/knowledge_graph/schema.py`.

### Uniqueness Constraints
- `(c:Candidate).candidate_id` IS UNIQUE
- `(r:InterviewRound).round_id` IS UNIQUE
- `(q:Question).question_id` IS UNIQUE
- `(a:Answer).answer_id` IS UNIQUE
- `(e:Evidence).evidence_id` IS UNIQUE
- `(c:Competency).competency_id` IS UNIQUE
- `(p:Project).project_id` IS UNIQUE
- `(t:Technology).technology_id` IS UNIQUE
- `(s:Skill).skill_id` IS UNIQUE

### How to Run Schema Initialization
```python
from app.knowledge_graph import Neo4jKnowledgeGraphRepository, initialize_neo4j_schema

repo = Neo4jKnowledgeGraphRepository.from_settings()
executed = initialize_neo4j_schema(repo._driver, database="neo4j")
print(f"Applied {len(executed)} constraints and indexes.")
```

---

## 8. Running Tests

### Unit Tests (Offline / No Neo4j required)
The full test suite runs without requiring an active AuraDB instance:

```bash
cd backend
source .venv/bin/activate
pytest tests/test_knowledge_graph.py -v
```

### Optional Live Neo4j Integration Test
To execute end-to-end integration tests against a live Neo4j AuraDB instance:

```bash
RUN_NEO4J_INTEGRATION_TESTS=1 \
NEO4J_URI="neo4j+s://<instance>.databases.neo4j.io" \
NEO4J_USERNAME="neo4j" \
NEO4J_PASSWORD="<password>" \
pytest tests/test_knowledge_graph.py -k test_live_neo4j_integration
```

---

## 9. M1 Interview Intelligence → Knowledge Graph Persistence Flow

### Data Flow & Architectural Boundary
Interview questions, candidate answers, evaluated evidence, and competency findings are persisted asynchronously into the Knowledge Graph as a **side-effect projection** of evaluated turns:

```
Candidate Answer
       │
       ▼
Agora Voice Runtime
       │
       ▼
CustomLLMAdapter.process_turn_async()
       │
       ├──> [1] Fast-Path Classifier (Bypasses M1 & KG on control turns)
       │
       ├──> [2] M1 Interview Intelligence (Evaluates AnswerAnalysis)
       │
       ├──> [3] Context Mutation (Updates InterviewAIContext in-memory state)
       │
       ├──> [4] Meta-Orchestrator (Determines NextAction: question/switch/complete)
       │
       └──> [5] KnowledgeGraphPersistenceService (Side-Effect Memory Projection)
                   │
                   ▼
       KnowledgeGraphRepository (Neo4j / InMemory)
```

> [!IMPORTANT]
> **Strict Routing Separation**:
> The Knowledge Graph is **NEVER** queried to decide `NextAction`, interview routing, or interviewer agent switching.
> Graph retrieval is **NOT** implemented in this task; persistent memory is currently **WRITE-ONLY**.

### Entities Persisted Per Evaluated Turn
For every completed candidate turn evaluated by M1:
1. **`Candidate`**: Authoritative `candidate_id`, name, and email from session context.
2. **`InterviewRound`**: Unique session round node (`round_id = f"{interview_id}_{round_name}"`).
3. **`Question`**: The spoken question that prompted the answer (`question_id = f"{round_id}_q_{hash}"`), targeted competency, and difficulty.
4. **`Answer`**: The transcribed response text, duration, and evaluation metrics (`overall_performance`, `confidence`, `vague`, `contradiction_detected`).
5. **`Competency`**: Normalized canonical competency nodes (e.g. `'System Design'` -> `'system_design'`).
6. **`Evidence`**: Atomic behavioral and technical observations preserving strict provenance.

### Graph Edges Created Per Turn
- `(:Candidate)-[:PARTICIPATED_IN]->(:InterviewRound)`
- `(:InterviewRound)-[:HAS_QUESTION]->(:Question)`
- `(:InterviewRound)-[:HAS_ANSWER]->(:Answer)`
- `(:Question)-[:HAS_ANSWER]->(:Answer)`
- `(:Question)-[:TARGETS_COMPETENCY]->(:Competency)`
- `(:Answer)-[:SUPPORTED_BY]->(:Evidence)`
- `(:Evidence)-[:SUPPORTS_COMPETENCY]->(:Competency)`
- `(:Candidate)-[:HAS_EVIDENCE]->(:Evidence)`

### Provenance Guarantee
Every `Evidence` node retains complete auditability:
- `candidate_id`: Identifies the candidate.
- `round_id`: Identifies the interview round.
- `answer_id`: Identifies the exact spoken answer from which the signal was drawn.
- `source_agent_id`: Identifies the interviewer persona (e.g. `alex`, `jordan`) who observed the signal.
- `competency`: Identifies the specific evaluated skill or competency.
- `signal`: The concrete technical observation.
- `timestamp`: UTC observation timestamp.

### Idempotency
- Duplicate webhooks, transcript retries, or re-processed turns execute idempotent `MERGE` queries.
- Reprocessing the exact same turn updates properties in place without creating duplicate nodes or edges.

### Error Isolation
- Neo4j persistence is fully decoupled from the conversational turn response.
- If Neo4j AuraDB experiences network partitioning or authentication failure, `CustomLLMAdapter._persist_to_knowledge_graph_safe()` logs the structured error:
  `knowledge_graph_persistence_failed`
  and allows the candidate to receive the interviewer voice response without delay or exception.

### Durability Limitations
- In this task, background execution runs in-process. In the event of a sudden server crash during turn processing, unwritten in-memory tasks would be lost.
- Durable queue infrastructure (e.g. Redis / Celery / event bus) will be introduced in subsequent infrastructure tasks.

---

## 10. Persistent Candidate Memory Retrieval (Task 4)

### Overview
Task 4 implements the read/retrieval side of the Knowledge Graph, making persistent candidate context available to the application layer.

```
Knowledge Graph (Neo4j AuraDB / InMemory)
      ↓
KnowledgeGraphRepository (Candidate-scoped queries)
      ↓
CandidateMemoryService (Validation, filtering, context budgeting)
      ↓
PersistentCandidateMemory (Typed structured memory)
      ↓
Available to Application Layer
```

> [!IMPORTANT]
> **Task 4 Routing Boundary**:
> Task 4 provides persistent memory retrieval but does **NOT** yet feed retrieved memory into Meta-Orchestrator routing.
> Knowledge Graph memory is **NOT** authoritative for routing decisions in this task.
> Meta-Orchestrator, M1 Interview Intelligence, Agora Voice Runtime, and the Candidate Interview UI remain completely unchanged in their runtime behavior.

### Domain Models (`app.knowledge_graph.memory_models`)
- **`PersistentCandidateMemory`**: Root Pydantic model representing unified candidate history.
  - `candidate_id`: Canonical candidate identifier (validated non-empty).
  - `name`, `email`: Identity projection from graph.
  - `evidence`: List of `RetrievedEvidence` items.
  - `competencies`: List of aggregated `CompetencySummary` objects with average scores and observation counts.
  - `projects`: List of `ProjectSummary` items with associated technologies and skills.
  - `skills`: List of demonstrated skills.
  - `technologies`: List of known/used technologies.
  - `interview_rounds`: List of `InterviewHistorySummary` objects detailing prior rounds attended.
  - `source_agents`: Rollup list of all agents who evaluated the candidate across history.
  - `source_rounds`: Rollup list of all round IDs attended by the candidate.
  - `filter_applied`: Deterministic filters and limits applied during retrieval.
- **`RetrievedEvidence`**: Strongly typed evidence item with non-empty provenance fields:
  - `evidence_id`, `answer_id`, `candidate_id`, `round_id`, `source_agent_id`, `competency`, `signal`, `score`, `timestamp`, `source_type`.
- **`MemorySourceType`**: Enum distinguishing evidence origins (`INTERVIEW_EVIDENCE`, `RESUME`, `APPLICATION`, `OTHER`).

### CandidateMemoryService (`app.knowledge_graph.memory_service`)
An isolated, read-only service that queries the repository layer and normalizes graph facts into `PersistentCandidateMemory`.
- Synchronous API: `get_candidate_memory(candidate_id, competency=None, round_id=None, source_agent_id=None, ...)`
- Asynchronous API: `get_candidate_memory_async(...)` using `asyncio.to_thread` to prevent blocking the asyncio event loop.

### Core Guarantees

#### 1. Candidate-Scoped Retrieval & Tenant Isolation
All graph queries anchor strictly on `(c:Candidate {candidate_id: $candidate_id})`. Retrieval is scoped strictly to the authenticated `candidate_id`. Queries never leak or traverse into another candidate's graph data.

#### 2. Cross-Agent Unified Memory
Memory belongs to the **candidate**, not the interviewer persona.
- Alex (System Design agent) in Round 1 observes caching and event streaming.
- Jordan (Concurrency agent) in Round 2 retrieves the candidate's persistent memory, seeing both Alex's and Jordan's prior findings.
- Agent identities are retained as provenance (`source_agent_id = "alex"`).

#### 3. Cross-Round Unified Memory
Observations span all completed and active interview rounds (`round_1`, `round_2`, etc.). By default, retrieval returns prior relevant information across rounds, with optional filtering by specific `round_id`.

#### 4. Deterministic Relevance Filtering
Targeted retrieval allows callers to filter by:
- `competency` (e.g. `competency="system_design"`): Returns evidence and summaries matching the normalized competency.
- `round_id`: Scopes evidence to a specific interview round.
- `source_agent_id`: Scopes evidence to a specific interviewer persona.
No LLM ranking, rewriting, or vector embeddings are used; all filtering is deterministic based on graph properties.

#### 5. Strict Provenance Preservation
Every retrieved evidence item retains full auditability:
`evidence_id`, `answer_id`, `candidate_id`, `round_id`, `source_agent_id`, `competency`, `signal`, `score`, `timestamp`.

#### 6. Context Budget Limits
To prevent unbounded graph growth when injecting memory into LLM prompts in future tasks, retrieval enforces explicit configurable limits:
- `DEFAULT_MAX_EVIDENCE = 20`
- `DEFAULT_MAX_PROJECTS = 10`
- `DEFAULT_MAX_SKILLS = 20`
- `DEFAULT_MAX_TECHNOLOGIES = 20`
- `DEFAULT_MAX_ROUNDS = 10`

#### 7. Strictly Read-Only
Retrieval operations perform pure reads. Calling `get_candidate_memory()` never mutates nodes, creates relationships, or modifies session state.

#### 8. Repository Abstraction Parity
Both `InMemoryKnowledgeGraphRepository` and `Neo4jKnowledgeGraphRepository` implement the same contract:
- `get_candidate_evidence(...)`
- `get_candidate_competencies(...)`
- `get_candidate_projects(...)`
- `get_candidate_skills(...)`
- `get_candidate_technologies(...)`
- `get_candidate_interview_rounds(...)`

---

## 9. Integration with Unified Agent Turn Context (`AgentTurnContext`)

In **Task 5**, the read side of the Knowledge Graph is integrated into the unified turn context layer:

1. **`AgentTurnContextBuilder`** calls `CandidateMemoryService.get_candidate_memory(...)` to assemble persistent evidence for each turn.
2. **Competency-Targeted Retrieval**: When M1 evaluates a specific competency (e.g. `customer_impact`), retrieval prioritizes matching verified evidence from prior turns and agents.
3. **Turn Isolation**: Retrieved graph memory is encapsulated inside an immutable per-turn snapshot `AgentTurnContext`.
4. **Prompt Delimiters**: Injected into the Meta-Orchestrator prompt under `[DATA CONTEXT - EVALUATION ONLY]` headers with full provenance badges (`source_type="INTERVIEW_EVIDENCE"`).
5. **Bidirectional Handoffs**: During agent transitions (Alex ↔ Jordan), `PersistentCandidateMemory` is carried forward seamlessly so the receiving agent never begins from an empty state.

For comprehensive architectural specifications, model schemas, and prompt budgeting details, see [`docs/AGENT_CONTEXT.md`](file:///Users/user/Desktop/intra_AI/docs/AGENT_CONTEXT.md).


