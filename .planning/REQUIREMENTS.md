# Requirements: Developer Productivity Agent Platform

**Defined:** 2026-05-14
**Core Value:** Given a complex developer query, the agent autonomously produces a correct multi-step plan and executes it against GitHub with measurably high task-completion and tool-call accuracy — and the eval harness proves it.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Ingestion & Indexing

- [ ] **INGEST-01**: System can ingest a target GitHub repo's source code, issues/PRs, READMEs/docs, and commit history via the GitHub API
- [ ] **INGEST-02**: Ingestion caches raw GitHub API responses to disk and uses retry-with-backoff to survive rate limits
- [ ] **INGEST-03**: Source code is chunked into a Postgres/pgvector index with embeddings (function/class-boundary-aware chunking preferred; fixed-size with overlap acceptable for v1)
- [ ] **INGEST-04**: Issues, PRs, READMEs/docs, and commit history are chunked and embedded into the index with source metadata (file path, issue #, commit SHA)
- [ ] **INGEST-05**: User can trigger (re)indexing of a repo via a CLI command

### Retrieval (RAG)

- [ ] **RAG-01**: Retrieval combines BM25 keyword search and dense vector search, fused via reciprocal-rank fusion (hybrid retrieval)
- [ ] **RAG-02**: Retriever returns chunk metadata (file:line, issue #, commit SHA) alongside content so answers can cite sources
- [ ] **RAG-03**: Retriever can route queries across the multiple indexed sources (code, issues/PRs, docs, commits) for cross-source investigation
- [ ] **RAG-04**: Retriever can fetch fresh issue/PR state live from the GitHub API when query freshness requires it, rather than relying only on the index

### Agent Orchestration

- [ ] **AGENT-01**: A planner agent decomposes a complex developer query into an explicit, ordered multi-step plan
- [ ] **AGENT-02**: A retriever agent executes retrieval steps against the hybrid RAG index and live GitHub API
- [ ] **AGENT-03**: An executor agent dispatches GitHub tool calls and synthesizes a final response
- [ ] **AGENT-04**: Agents pass state through typed schemas at every inter-agent boundary (no raw-text/history passing)
- [ ] **AGENT-05**: Planner uses chain-of-thought / ReAct scaffolding (Thought → Action → Observation) for tool selection
- [ ] **AGENT-06**: Orchestration enforces loop limits / circuit breakers to bound iterations and OpenAI cost
- [ ] **AGENT-07**: Every answer includes source citations (file:line, issue #, commit SHA) for the facts it asserts
- [ ] **AGENT-08**: Every tool invocation is exported to a structured JSONL trace (tool name, input params, output, latency, step index)

### GitHub Tools & Actions

- [ ] **GH-01**: Agent exposes GitHub read tools via MCP-style declarative tool definitions: fetch file, search code, list/get issues, get PR diff, list commits
- [ ] **GH-02**: Agent exposes GitHub write tools: create issue, comment on PR
- [ ] **GH-03**: All write actions are gated behind an explicit user confirmation step before execution
- [ ] **GH-04**: A `--dry-run` mode prints the exact GitHub API call that would be made without executing it
- [ ] **GH-05**: Every executed write action is recorded in an append-only audit log (action, parameters sent, API response)

### CLI Interface

- [ ] **CLI-01**: User can submit a natural-language query via a CLI command (`ask`)
- [ ] **CLI-02**: CLI renders the planner's multi-step plan in readable form before any execution
- [ ] **CLI-03**: CLI streams the final synthesized answer token-by-token rather than blocking on a blank terminal
- [ ] **CLI-04**: A verbose/trace mode surfaces the agent's Thought/Action/Observation reasoning steps
- [ ] **CLI-05**: User can specify the target GitHub repo via flag or project config file
- [ ] **CLI-06**: CLI surfaces GitHub/OpenAI API errors and rate-limit waits with actionable, root-cause messages
- [ ] **CLI-07**: CLI is a thin HTTP client against the FastAPI service (no agent logic embedded in the CLI)

### Evaluation Harness

- [ ] **EVAL-01**: A golden dataset of 200+ developer-query test cases exists, each with expected outcome / ground truth
- [ ] **EVAL-02**: Harness measures task completion rate across the test cases
- [ ] **EVAL-03**: Harness measures tool-call accuracy (correct tool name + arguments) across the test cases
- [ ] **EVAL-04**: Harness measures hallucination / faithfulness rate of answers against retrieved context
- [ ] **EVAL-05**: Eval runs are deterministic (temperature pinned to 0 on all eval calls)
- [ ] **EVAL-06**: Eval harness is runnable from the CLI and in CI, producing a metric report
- [ ] **EVAL-07**: A prompt-engineering framework allows iterating agent prompts and re-running eval to observe metric deltas

### Deployment

- [ ] **DEPLOY-01**: `docker-compose up` starts all services (Postgres/pgvector, FastAPI, supporting services) with no manual setup steps
- [ ] **DEPLOY-02**: Setup documentation covers local run, configuration (API keys, target repo), and the described AWS deployment path

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Integrations

- **INT-01**: Jira integration (tickets, sprint/board queries, status transitions)
- **INT-02**: Confluence integration (docs/wiki retrieval for RAG context)

### Enhancements

- **ENH-01**: AST-aware code chunking via tree-sitter (function/class boundaries) to improve retrieval precision
- **ENH-02**: Prompt-iteration diff workflow (`eval run --compare v1 v2`) with metric delta tables
- **ENH-03**: Incremental on-demand re-indexing rather than full re-index
- **ENH-04**: Multi-repo cross-search with per-repo index isolation and auth scoping
- **ENH-05**: Live observability/tracing dashboard (e.g. Langfuse) wired into docker-compose

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Web UI / chat frontend | CLI-first for v1; doubles scope with no backend-engineering showcase value |
| Fully autonomous writes (no confirmation) | One hallucinated target causes real damage; destroys demo credibility |
| Live AWS-hosted instance | Showcase ships dockerized + documented; live hosting adds cost/maintenance |
| Streaming real-time re-indexing on every git push | Webhook + incremental-diff plumbing is a project in itself |
| LLM fine-tuning on codebase data | GPU cost and eval-contamination risk; RAG + few-shot already achieves high faithfulness |
| Autonomous issue/PR creation without human-reviewed content | Hallucinated bodies/labels are embarrassing; agent drafts, human reviews before confirmation |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INGEST-01 | Phase 1 | Pending |
| INGEST-02 | Phase 1 | Pending |
| INGEST-03 | Phase 1 | Pending |
| INGEST-04 | Phase 1 | Pending |
| INGEST-05 | Phase 1 | Pending |
| GH-01 | Phase 1 | Pending |
| GH-05 | Phase 1 | Pending |
| DEPLOY-01 | Phase 1 | Pending |
| RAG-01 | Phase 2 | Pending |
| RAG-02 | Phase 2 | Pending |
| RAG-03 | Phase 2 | Pending |
| RAG-04 | Phase 2 | Pending |
| AGENT-01 | Phase 3 | Pending |
| AGENT-02 | Phase 3 | Pending |
| AGENT-03 | Phase 3 | Pending |
| AGENT-04 | Phase 3 | Pending |
| AGENT-05 | Phase 3 | Pending |
| AGENT-06 | Phase 3 | Pending |
| AGENT-07 | Phase 3 | Pending |
| AGENT-08 | Phase 3 | Pending |
| GH-02 | Phase 3 | Pending |
| GH-03 | Phase 3 | Pending |
| GH-04 | Phase 3 | Pending |
| CLI-01 | Phase 4 | Pending |
| CLI-02 | Phase 4 | Pending |
| CLI-03 | Phase 4 | Pending |
| CLI-04 | Phase 4 | Pending |
| CLI-05 | Phase 4 | Pending |
| CLI-06 | Phase 4 | Pending |
| CLI-07 | Phase 4 | Pending |
| EVAL-01 | Phase 5 | Pending |
| EVAL-02 | Phase 5 | Pending |
| EVAL-03 | Phase 5 | Pending |
| EVAL-04 | Phase 5 | Pending |
| EVAL-05 | Phase 5 | Pending |
| EVAL-06 | Phase 5 | Pending |
| EVAL-07 | Phase 5 | Pending |
| DEPLOY-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 36 total
- Mapped to phases: 36
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-14*
*Last updated: 2026-05-14 after roadmap creation*
