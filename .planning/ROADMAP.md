# Roadmap: Developer Productivity Agent Platform

## Overview

Build in strict dependency order: the database schema and GitHub tool layer are leaf nodes that everything downstream imports, so they go first. The ingestion pipeline populates the index the RAG retriever depends on. The RAG retriever must pass an independent quality gate (Hit Rate@5 >= 0.75) before being wired into the LangGraph agent graph. The agent graph and FastAPI service are built together because PostgresSaver must be live before the HITL interrupt() confirmation gate can work. The CLI is a thin HTTP client and only comes after FastAPI is running. The eval harness imports the full agent graph and requires all prior components; its golden-dataset schema is seeded in Phase 1 so test cases shape what gets built rather than score what already exists. Prompt iteration closes the loop by measuring metric deltas against the stable eval baseline.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - PostgreSQL/pgvector schema, GitHub read tools, ingestion pipeline, and initial docker-compose
- [ ] **Phase 2: Hybrid RAG Layer** - BM25 + dense vector retrieval with RRF fusion, Hit Rate@5 validation gate
- [ ] **Phase 3: Agent Orchestration + FastAPI** - LangGraph StateGraph (planner/retriever/executor/synthesizer), PostgresSaver, FastAPI endpoints
- [ ] **Phase 4: CLI + HITL Confirmation Gate** - Typer CLI, Rich-formatted plan display, streaming output, write confirmation UX
- [ ] **Phase 5: Eval Harness** - 200+ golden test cases, three DeepEval metrics, CI runner, JSONL trace integration
- [ ] **Phase 6: Prompt Engineering + Polish** - Prompt iteration workflow, on-demand refresh, Langfuse tracing, deployment docs

## Phase Details

### Phase 1: Foundation
**Goal**: The data layer, GitHub tool layer, and ingestion pipeline are operational — the system can ingest a repo and store structured, queryable chunks ready for retrieval
**Depends on**: Nothing (first phase)
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05, GH-01, GH-05, DEPLOY-01
**Success Criteria** (what must be TRUE):
  1. `docker-compose up` starts PostgreSQL with pgvector extension enabled, all tables created (vector_nodes, checkpoints, eval_cases, eval_results), and HNSW index deferred until after data load
  2. User can run `devagent index <owner/repo>` and the system ingests source code (AST-chunked via CodeSplitter), issues/PRs, READMEs, and commit history from the GitHub API with retry-on-rate-limit and raw-response disk caching
  3. Ingested chunks are stored in pgvector with embeddings, source metadata (file path, issue number, commit SHA) attached to every node
  4. GitHub read tools (fetch file, search code, list issues, get PR diff, list commits) are callable as Pydantic-schemed functions and return typed outputs
  5. Every write action is recorded in an append-only audit log table; 20-30 eval case schemas are seeded in the eval_cases table
**Plans**: TBD

### Phase 2: Hybrid RAG Layer
**Goal**: Hybrid BM25 + dense vector retrieval with RRF fusion is independently validated to Hit Rate@5 >= 0.75 before being wired into agents
**Depends on**: Phase 1
**Requirements**: RAG-01, RAG-02, RAG-03, RAG-04
**Success Criteria** (what must be TRUE):
  1. A retrieval query returns results that combine BM25 keyword scoring and dense vector similarity, merged via Reciprocal Rank Fusion (RRF with k tuned for portfolio-scale corpus)
  2. Every returned chunk includes source metadata (file:line, issue number, commit SHA) alongside its content
  3. The retriever routes queries across all four indexed source types (code, issues/PRs, docs, commits) and can fetch fresh issue/PR state live from the GitHub API when query freshness demands it
  4. Hit Rate@5 measured against 20 held-out query/chunk pairs is >= 0.75 before Phase 3 begins — this is a hard gate
**Plans**: TBD

### Phase 3: Agent Orchestration + FastAPI
**Goal**: A working LangGraph planner/retriever/executor/synthesizer pipeline with typed AgentState, PostgresSaver checkpointing, cost guardrails, and FastAPI endpoints is operational end-to-end
**Depends on**: Phase 2
**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06, AGENT-07, AGENT-08, GH-02, GH-03, GH-04
**Success Criteria** (what must be TRUE):
  1. Submitting a natural-language query to POST /query returns a structured multi-step plan (planner uses ReAct/CoT with GPT-4o strict=True structured output) before any tool calls execute
  2. The retriever node fetches context from the hybrid RAG layer and the executor node dispatches GitHub tools; every tool invocation is exported to a JSONL trace (tool name, input params, output, latency, step index)
  3. Every agent-to-agent boundary passes a typed Pydantic AgentState — no raw message history — and circuit breakers (max_iterations=5 executor, max_iterations=3 planner) are active on all agent invocations
  4. Any plan step that would execute a GitHub write action suspends via LangGraph interrupt() and waits for an explicit POST /confirm before the HTTP write fires; --dry-run mode prints the exact GitHub API call without executing it
  5. Every synthesized answer includes source citations (file:line, issue number, commit SHA) for the facts it asserts
**Plans**: TBD
**UI hint**: no

### Phase 4: CLI + HITL Confirmation Gate
**Goal**: A developer can submit queries, review agent plans, stream answers, and confirm or reject write actions entirely from the terminal
**Depends on**: Phase 3
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-07
**Success Criteria** (what must be TRUE):
  1. `devagent ask "<query>"` submits a query to FastAPI, renders the planner's multi-step plan in a Rich-formatted panel, and streams the final synthesized answer token-by-token to the terminal
  2. When the agent proposes a write action, the CLI displays a human-readable confirmation prompt (repo, action type, affected resource, body preview) and requires explicit y/N before sending POST /confirm
  3. `--verbose` mode surfaces the agent's Thought/Action/Observation reasoning steps; `--dry-run` shows the exact GitHub API call without executing it
  4. Target repo is configurable via `--repo owner/name` flag or a .devagent.yml project config file; GitHub/OpenAI API errors and rate-limit waits are surfaced with root-cause messages, not stack traces
  5. CLI contains zero agent logic — it is a pure HTTP client against the FastAPI service
**Plans**: TBD
**UI hint**: yes

### Phase 5: Eval Harness
**Goal**: A deterministic, CI-runnable eval harness with 200+ golden test cases measures task completion, tool-call accuracy, and hallucination rate against the full agent pipeline
**Depends on**: Phase 3
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, EVAL-06, EVAL-07
**Success Criteria** (what must be TRUE):
  1. The eval/ package contains 200+ YAML/JSON test cases, each with a developer query, expected tool calls, expected plan steps, and a ground-truth answer referencing real repo entities
  2. `pytest eval/` (or `devagent eval run`) executes all cases with temperature=0, scores ToolCorrectnessMetric, TaskCompletionMetric, and HallucinationMetric via DeepEval, and stores results in the eval_results PostgreSQL table
  3. Metric variance across three consecutive runs of the same 10 cases is less than 2 percentage points (determinism gate)
  4. The harness mocks GitHub write tools so eval runs make no real mutations against GitHub; eval results are written as a pytest report consumable in CI
  5. A prompt-engineering framework exists that lets an engineer change an agent prompt and re-run eval to observe metric deltas
**Plans**: TBD

### Phase 6: Prompt Engineering + Polish
**Goal**: Prompt iteration is measurable against a stable eval baseline, the index can be refreshed on demand, Langfuse tracing is instrumented throughout, and the project is demo-ready with complete deployment documentation
**Depends on**: Phase 5
**Requirements**: DEPLOY-02
**Success Criteria** (what must be TRUE):
  1. `devagent eval run --compare v1 v2` runs both prompt versions and displays a metric delta table (task completion, tool-call accuracy, hallucination rate) so the impact of a prompt change is quantified
  2. `devagent refresh` triggers on-demand re-indexing of a specific resource type (issues, PRs, code, commits) without a full teardown; retrieved chunks include a last_indexed_at staleness timestamp
  3. Langfuse tracing is instrumented throughout all agent nodes so every query has a full observability trace accessible in the self-hosted Langfuse docker-compose service
  4. Setup documentation covers local run via docker-compose, API key configuration, target repo selection, and the described AWS deployment path; a README demo script produces a compelling end-to-end showcase run
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/TBD | Not started | - |
| 2. Hybrid RAG Layer | 0/TBD | Not started | - |
| 3. Agent Orchestration + FastAPI | 0/TBD | Not started | - |
| 4. CLI + HITL Confirmation Gate | 0/TBD | Not started | - |
| 5. Eval Harness | 0/TBD | Not started | - |
| 6. Prompt Engineering + Polish | 0/TBD | Not started | - |
