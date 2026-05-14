# Project Research Summary

**Project:** Developer Productivity Agent Platform
**Domain:** CLI-first multi-agent developer productivity platform (GitHub + hybrid RAG + eval harness)
**Researched:** 2026-05-14
**Confidence:** HIGH

## Executive Summary

This is a portfolio-grade multi-agent developer tool: a planner/retriever/executor pipeline that accepts natural-language queries, retrieves context from a hybrid BM25 + dense RAG index over GitHub data (code, issues, PRs, commits), and executes confirmed write actions via declarative GitHub tool definitions. The right build pattern is LangGraph for orchestration (not LangChain AgentExecutor, which is deprecated for multi-agent use), LlamaIndex for the RAG layer, and a FastAPI service decoupling the CLI from agent logic. The eval harness — 200+ test cases measuring task completion, tool-call accuracy, and hallucination rate via DeepEval — is a core deliverable and must be treated as a first-class engineering artifact, not an afterthought.

The recommended approach is to build in strict dependency order: database schema and GitHub tool layer first (everything depends on them), then the ingestion pipeline and RAG retriever, then LangGraph agents and FastAPI, then CLI and the HITL confirmation gate, and finally the eval harness. This order is dictated by hard import and data dependencies. PostgreSQL + pgvector covers vector storage, BM25 full-text search, LangGraph checkpointing, and eval result storage in a single service — keeping the docker-compose footprint minimal and appropriate for a portfolio demo.

The dominant risks are error amplification across agent hops (unvalidated inter-agent state causes 17x error amplification), agent infinite loops from missing iteration caps, context bloat from passing raw history between agents, and naive fixed-size code chunking that silently destroys retrieval quality. All four are preventable from day one with typed AgentState, explicit max_iterations, AST-aware chunking via LlamaIndex CodeSplitter, and strict Pydantic schemas on every inter-agent boundary. Eval non-determinism (using temperature > 0 during eval runs) and gameable task completion metrics must also be designed against from the start.

## Key Findings

### Recommended Stack

The stack is Python 3.11, LangGraph 1.2 + LangChain 1.3 for orchestration, LlamaIndex 0.14 for the RAG pipeline, FastAPI 0.115 as the internal agent service, PostgreSQL 16 + pgvector 0.8 as the unified data store, OpenAI GPT-4o for LLM calls and text-embedding-3-small for embeddings, and DeepEval 4.0 as the eval framework. All versions verified against PyPI. Tooling is Typer + Rich for the CLI, PyGithub 2.9 for GitHub API, Langfuse (self-hostable, MIT) for observability, and uv + ruff for dev tooling. LangSmith is explicitly excluded (requires paid enterprise license to self-host). ChromaDB, GitPython, and LangChain AgentExecutor are all excluded.

**Core technologies:**
- LangGraph 1.2: Multi-agent orchestration — current official path for stateful multi-actor systems; supervisor pattern maps directly to planner/retriever/executor
- LlamaIndex 0.14: RAG pipeline — superior RAG primitives (QueryFusionRetriever, BM25Retriever, CodeSplitter, PGVectorStore) vs. LangChain retrievers
- PostgreSQL 16 + pgvector 0.8: Unified data store — vectors, BM25 full-text, LangGraph checkpoints, eval results in one service
- FastAPI 0.115: Agent service layer — decouples CLI from agent logic; SSE streaming; required for testability
- DeepEval 4.0: Eval harness — ToolCorrectnessMetric, FaithfulnessMetric, HallucinationMetric; pytest-native; LangGraph callback handler built in
- PyGithub 2.9: GitHub REST client — covers all required read/write ops with a typed API
- Langfuse 4.6: Observability — MIT, self-hostable via docker-compose, OpenTelemetry-native

### Expected Features

**Must have (table stakes):**
- Hybrid RAG index (BM25 + dense vector) over code, issues, PRs, READMEs, commits — core value delivery
- Three-agent decomposition: planner (query to structured plan), retriever (RAG fetch), executor (tool dispatch) — headline architecture story
- GitHub read tools: fetch file, list issues, get PR diff, list commits — retrieval foundation
- GitHub write tools: create issue, add PR comment — with explicit user confirmation gate
- Source citations (file:line, issue #, commit SHA) in every answer — hallucination visibility
- Streaming CLI output — blank terminal for 15-20s is unacceptable in demo
- docker-compose single-command deployment — reviewer experience requirement
- ReAct/CoT scaffolding in planner — reasoning traces visible in CLI

**Should have (competitive differentiators):**
- Eval harness: 200+ golden test cases, three metrics (task completion, tool-call accuracy, hallucination), CI-runnable — headline differentiator; no peer showcases this openly
- Tool-call trace export (JSONL) — required for eval harness; enables post-hoc debugging
- AST-aware code chunking (tree-sitter) — preserves function/class boundaries; prevents silent retrieval quality collapse
- Prompt-iteration diff workflow (eval run --compare v1 v2) — engineering showcase
- --dry-run flag for write operations — safe demo without real mutations
- Hallucination rate surfaced per-query in CLI output

**Defer (v2+):**
- Jira/Confluence integration — doubles scope with no v1 demo value
- Multi-repo cross-search — additive layer; build single-repo deep first
- Web UI/chat frontend — no portfolio value relative to cost for a developer tool
- Incremental real-time re-indexing on push — webhook plumbing is a separate project

### Architecture Approach

The system is layered: CLI (Typer/Rich) is a thin HTTP client that POSTs queries to a FastAPI service and streams SSE responses. FastAPI invokes a LangGraph StateGraph in-process (not as a separate microservice). The graph has four nodes — Planner, Retriever, Executor, Synthesizer — with LangGraph interrupt() suspending the Executor before any write tool call until the CLI sends a /confirm request. State is persisted to PostgreSQL via PostgresSaver after every node transition, enabling mid-graph resume. The RAG layer (LlamaIndex QueryFusionRetriever + BM25 + pgvector + optional cross-encoder reranker) is imported directly into the Retriever node. The GitHub tool layer is a standalone tools/ package importable by both the Executor node and the eval harness (for mocking). The eval harness (eval/) is a fully separate package that imports the agent graph directly, mocks write tools, and runs via pytest.

**Major components:**
1. CLI (cli/) — Typer/Rich; pure HTTP client; no agent logic; calls FastAPI over HTTP + SSE
2. FastAPI service (api/) — stateless gateway; routes to LangGraph; streams SSE; POST /query, POST /confirm, POST /ingest, GET /eval/run
3. LangGraph orchestrator (agents/) — StateGraph with typed AgentState; planner, retriever, executor, synthesizer nodes; PostgresSaver checkpointing
4. RAG layer (rag/) — LlamaIndex ingestion pipeline (AST chunker for code, sentence-window for prose) + HybridRetriever (BM25 + dense + RRF) + optional cross-encoder reranker
5. GitHub tool layer (tools/) — MCP-style declarative tool specs; Pydantic schemas; read tools (no gate) + write tools (interrupt gate)
6. Eval harness (eval/) — DeepEval + pytest; 200+ YAML/JSON cases; ToolCorrectness, Faithfulness, Hallucination metrics; CI-runnable
7. PostgreSQL (db/) — pgvector for embeddings, tsvector for BM25, checkpoints table for LangGraph, eval_cases and eval_results tables

### Critical Pitfalls

1. **Error amplification across agent hops** — Use typed Pydantic AgentState (never raw message history) at every inter-agent boundary; use OpenAI strict=True structured outputs on planner; add a lightweight plan validation gate before retriever runs. Recovery cost if ignored: HIGH (requires touching all three agent interfaces).

2. **Agent infinite loops and token budget exhaustion** — Set max_iterations=5 on executor, max_iterations=3 on planner; add circuit breaker (same tool + same args twice = abort); set hard OpenAI account spending limit before any multi-step agent demo runs. Recovery cost: MEDIUM.

3. **Naive code chunking destroying retrieval quality** — Use LlamaIndex CodeSplitter (tree-sitter) for all source files; 80-160 token chunks at function/class boundaries; sentence-window for prose. Measure Hit Rate@5 on 20 held-out queries before wiring to agents. Recovery cost if ignored: HIGH (full re-chunk and re-embed).

4. **Eval harness non-determinism** — Set temperature=0 on all eval LLM calls; use deterministic metrics (exact tool name match, entity extraction) not just LLM-as-judge; run LLM-as-judge 3x and take majority vote; verify metric variance < 2pp across consecutive runs of the same cases.

5. **pgvector HNSW index created before data load** — Never create the HNSW index in schema init; create it only after the initial data load; set shm_size: 256mb in docker-compose; set maintenance_work_mem=256MB for index builds; verify with EXPLAIN ANALYZE that vector queries use Index Scan, not Seq Scan.

## Implications for Roadmap

Based on the architecture's hard dependency graph, the required phase structure is:

### Phase 1: Foundation — Database Schema, GitHub Tools, Ingestion Pipeline

**Rationale:** Everything in the system depends on the database schema and GitHub tool layer. These have no internal dependencies. The ingestion pipeline must run before the RAG retriever can return anything. Building these first also allows 20-30 eval cases to be defined early (preventing the "optimise for what already works" trap).

**Delivers:** Runnable docker-compose with PostgreSQL + pgvector; GitHub read tool wrappers; initial data load (code, issues, PRs, commits indexed); basic devagent index CLI command; first 20-30 eval case schemas.

**Addresses (from FEATURES.md):** Hybrid RAG index (foundation), GitHub read tools (all 5 core ops), docker-compose deployment, configurable repo context.

**Avoids (from PITFALLS.md):** pgvector HNSW index timing (create after load); GitHub rate limit exhaustion (implement backoff + caching in this phase); naive code chunking (use CodeSplitter from day one).

### Phase 2: RAG Layer — Hybrid Retrieval

**Rationale:** The retriever node in LangGraph imports the RAG layer directly. RAG quality must be independently validated (Hit Rate@5 >= 0.75 on held-out queries) before being wired into agents — otherwise retrieval bugs become invisible inside the agent loop.

**Delivers:** LlamaIndex HybridRetriever (BM25 + dense + RRF); pgvector HNSW index on loaded data; retrieval quality benchmark on 20 held-out query/chunk pairs; optional cross-encoder reranker stub.

**Uses (from STACK.md):** llama-index-vector-stores-postgres, QueryFusionRetriever, BM25Retriever, rank-bm25, text-embedding-3-small.

**Implements (from ARCHITECTURE.md):** RAG layer component; rag/retriever.py, rag/index.py.

**Avoids:** BM25/dense fusion weight ignored (tune k to 10-15 for portfolio-scale corpus; measure Hit Rate@5 before proceeding).

### Phase 3: Agent Orchestration + FastAPI Service

**Rationale:** LangGraph agents depend on the RAG layer (Phase 2) and tool layer (Phase 1). FastAPI depends on the LangGraph graph. These are built together because the PostgresSaver checkpointer must be wired before any interrupt()-based confirmation gate can work — skipping it breaks the write confirmation flow.

**Delivers:** Working LangGraph StateGraph with typed AgentState; planner (GPT-4o, ReAct/CoT, structured plan output); retriever node (calls hybrid RAG); executor node (calls tools, interrupt() for writes); synthesizer node; FastAPI endpoints (POST /query, POST /confirm, POST /ingest); SSE streaming response; PostgresSaver checkpointing.

**Implements (from ARCHITECTURE.md):** Orchestration layer (all four nodes); FastAPI service layer; MCP-style confirmation gate pattern.

**Avoids:** Error amplification (typed AgentState from day one); context window bloat (pass top-3 chunks, not full history); agent infinite loops (max_iterations set at init).

### Phase 4: CLI + HITL Confirmation Gate

**Rationale:** CLI is a pure HTTP client and can only be built after FastAPI is running. The confirmation gate UX (pretty-printed plan, y/N prompt, --dry-run) depends on the /confirm FastAPI endpoint from Phase 3.

**Delivers:** Typer CLI (devagent ask, devagent index, devagent eval); Rich-formatted plan display; streaming output via SSE; confirmation prompt for write actions; --dry-run flag; --verbose trace mode (Thought/Action/Observation output); source citations displayed per answer.

**Addresses (from FEATURES.md):** All CLI table stakes; write confirmation gate; streaming output; structured plan display; error messages with root cause; --dry-run.

**Avoids:** UX pitfalls (streaming, pretty-print confirmation payload, human-readable GitHub API errors, --dry-run before any real mutations).

### Phase 5: Eval Harness

**Rationale:** The eval harness imports the agent graph directly and requires the full agent pipeline (Phase 3) and tool schemas (Phase 1) to be in place. Eval case schemas must be seeded in Phase 1 (not here) so they shape what gets built, not score what already exists. This phase implements the metric scorers, runner, and CI integration.

**Delivers:** DeepEval test suite with 200+ YAML/JSON cases; ToolCorrectnessMetric, TaskCompletionMetric, HallucinationMetric scorers; pytest eval/ runnable in CI; tool-call trace export (JSONL) wired into executor; eval results stored in PostgreSQL eval_results table; devagent eval run CLI command.

**Implements (from ARCHITECTURE.md):** Eval harness component; eval harness flow (runner to metrics to results DB to pytest report).

**Avoids:** Eval non-determinism (temperature=0 on all eval calls); gameable task completion metric (task_success = completion + correct tool + correct resource + fuzzy output match).

### Phase 6: Prompt Engineering Iteration + Polish

**Rationale:** Once the eval harness has stable, deterministic baselines, prompt changes can be measured against metric deltas. This is the engineering story: change a prompt, re-run eval, see the diff. This phase covers the eval run --compare workflow, incremental re-indexing (devagent refresh), and overall portfolio polish.

**Delivers:** Prompt iteration workflow (--compare flag); metric delta table in CLI output; devagent refresh command for on-demand re-indexing; index staleness metadata (last_indexed_at) in retrieval output; Langfuse tracing instrumented throughout; README and demo script.

**Addresses (from FEATURES.md):** Prompt-iteration diff workflow (P2), hallucination dashboard (P2), incremental re-indexing (P2).

**Avoids:** Stale RAG index (refresh command + staleness metadata); eval metrics that look done but are not (final "looks done but isn't" checklist verified).

### Phase Ordering Rationale

- Phase 1 before everything: database schema and GitHub tool layer are leaf nodes in the dependency graph; nothing else can start without them.
- Phase 2 before Phase 3: retrieval quality must be independently validated before being embedded in the agent loop — retrieval bugs are invisible inside the agent graph.
- Phase 3 before Phase 4: CLI is a pure HTTP client; FastAPI must exist first. PostgresSaver must be wired before interrupt() is used.
- Phase 5 after Phase 3: eval harness needs the full agent graph; but case schemas must be seeded in Phase 1 to avoid optimising for current behavior.
- Phase 6 last: prompt iteration requires a stable eval baseline; polish and refresh tooling are additive.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (RAG Layer):** Hybrid retrieval tuning (RRF k-value, BM25 weight, reranker choice) is corpus-sensitive and requires empirical validation against held-out queries. The LlamaIndex pgvector HYBRID query mode (MEDIUM confidence in source) needs verification against actual PGVectorStore API.
- **Phase 5 (Eval Harness):** DeepEval ToolCorrectnessMetric behavior with mocked GitHub tools and partial argument matching needs validation. Ground-truth dataset construction methodology for 200 cases needs a concrete plan.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** PyGithub usage, pgvector schema setup, LlamaIndex ingestion pipeline, and docker-compose orchestration all have extensive official documentation and verified patterns.
- **Phase 3 (Agents + FastAPI):** LangGraph StateGraph, PostgresSaver, interrupt() mechanics, and FastAPI SSE streaming are well-documented with reference implementations.
- **Phase 4 (CLI):** Typer + Rich patterns are straightforward; the HTTP client layer is a thin wrapper.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All package versions verified against PyPI; version compatibility matrix verified against official docs; alternatives analysis grounded in official deprecation notices |
| Features | HIGH | Core agent/eval patterns verified across multiple production sources; GitHub tool surface verified against official MCP server docs |
| Architecture | HIGH | LangGraph/LlamaIndex patterns well-documented; PostgresSaver mechanics verified against official docs; build order derived from hard dependency graph |
| Pitfalls | HIGH | Most pitfalls verified across multiple production post-mortems and official docs; error amplification figure (17x) from peer-reviewed arxiv paper |

**Overall confidence:** HIGH

### Gaps to Address

- **LlamaIndex pgvector HYBRID mode in PGVectorStore:** Documented as supported; needs hands-on verification that VectorStoreQueryMode.HYBRID works end-to-end with the project's schema and Postgres 16. Resolve in Phase 2 spike.
- **DeepEval ToolCorrectnessMetric with mocked tools:** The metric's behavior when write tools are dependency-injected as mocks (not real PyGithub calls) needs to be confirmed. Resolve in Phase 5 setup.
- **Ground-truth dataset scale:** 200 cases is specified as a hard requirement. The strategy for generating the remaining ~150 templated cases (after ~50 hand-curated cases) needs a concrete plan before Phase 5 begins.
- **OpenAI prompt caching impact on eval cost:** If static system prompts are structured to hit OpenAI's auto-cache (>1024 token prefix), eval run cost can be reduced 2-3x. Worth measuring after Phase 5 baseline is established.

## Sources

### Primary (HIGH confidence)
- PyPI package registry — all 14 core package versions verified 2026-05-14
- LangChain official (langchain.com/langgraph) — LangGraph as recommended multi-agent path
- DeepEval docs (confident-ai.com) — ToolCorrectnessMetric, FaithfulnessMetric confirmed
- LlamaIndex docs (developers.llamaindex.ai) — BM25Retriever, QueryFusionRetriever, CodeSplitter confirmed
- GitHub docs (docs.github.com) — REST API rate limits, pagination, secondary rate limits
- OpenAI docs (developers.openai.com) — strict=True structured outputs, prompt caching
- LangGraph docs — interrupt() mechanics, PostgresSaver, StateGraph patterns
- arxiv.org/html/2503.13657v1 — multi-agent error amplification (17x figure)
- arxiv.org/html/2506.15655v1 — AST-based code chunking rationale

### Secondary (MEDIUM confidence)
- LlamaIndex pgvector HYBRID query mode — verified via PyPI package docs summary (not direct API test)
- Langfuse vs LangSmith self-hosting comparison — langfuse.com/faq; licensing difference confirmed
- LlamaIndex alpha tuning for hybrid search — llamaindex.ai blog; BM25/dense weight guidance
- production-grade hybrid-rag reference repo — github.com/tim-ponomarev/hybrid-rag

### Tertiary (LOW confidence)
- RRF k-value corpus-size sensitivity — community guidance; needs empirical validation on actual corpus in Phase 2

---
*Research completed: 2026-05-14*
*Ready for roadmap: yes*
