# Stack Research

**Domain:** CLI-first multi-agent developer productivity platform (GitHub + hybrid RAG + eval harness)
**Researched:** 2026-05-14
**Confidence:** HIGH (all versions verified against PyPI; architecture patterns verified against official docs and multiple sources)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | 3.11 is the stable sweet spot: significant perf gains over 3.10, full async support, widely available in Docker images. 3.12 is usable but some LangChain/LlamaIndex deps lag. |
| LangGraph | 1.2.0 | Multi-agent orchestration | LangChain's `AgentExecutor` is the legacy path; LangGraph is the current official recommendation for stateful, multi-actor systems. It exposes the graph as explicit nodes and edges, giving full control over planner→retriever→executor flow, state passing, conditional edges, and human-in-the-loop confirmation gates. Supervisor pattern from `langgraph-supervisor` maps directly to the planner decomposition. |
| LangChain | 1.3.0 | Tool abstractions, prompt templates, LLM integrations | Still the right layer for `@tool` decorators, `ChatPromptTemplate`, output parsers, and the chain-of-thought scaffolding. LangGraph IS LangChain's orchestration layer — they are complementary, not competing. Do not use standalone `AgentExecutor` for new code. |
| LlamaIndex Core | 0.14.21 | RAG pipeline — indexing, retrieval, query engine | Best-in-class RAG primitives: `VectorStoreIndex`, `BM25Retriever`, `QueryFusionRetriever` (RRF merge), node parsers for code/markdown/commits. Postgres pgvector integration via `llama-index-vector-stores-postgres`. Works alongside LangGraph via `LlamaIndexToolSpec`. |
| FastAPI | 0.115.x | Internal API layer for agent server | Spec choice is sound. Async-first, Pydantic v2 native, OpenAPI auto-docs. Useful for exposing the agent as a local service the CLI calls over HTTP/SSE — supports streaming agent responses cleanly. Do not skip this; it decouples CLI from agent runtime. |
| PostgreSQL + pgvector | PG 16, pgvector 0.8.x | Vector store + metadata store + BM25 full-text | Spec choice is sound for a portfolio project. Keeps the stack simple: one DB for vectors, BM25 text search, agent memory, and job state. pgvector 0.7+ supports HNSW indexing which is required for production-grade ANN latency. |
| OpenAI API | openai==2.36.0 | LLM backbone (GPT-4o) + embeddings (text-embedding-3-small) | Spec choice is sound. GPT-4o with `strict=True` function calling gives reliable structured tool invocation. Use `text-embedding-3-small` (1536-dim) for embeddings — good quality/cost balance. Use `text-embedding-3-large` only if retrieval quality proves insufficient. |
| Docker / docker-compose | Docker 27.x | Containerized local deployment | Spec choice is sound. `docker-compose.yml` should orchestrate: FastAPI agent server, PostgreSQL+pgvector, and (optionally) Langfuse. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langgraph-supervisor | 0.0.x (latest) | Supervisor/planner pattern for LangGraph | Use for the planner agent — it provides the supervisor node that dispatches to retriever and executor subagents without boilerplate. |
| llama-index-vector-stores-postgres | 0.4.x | pgvector integration for LlamaIndex | Required to connect LlamaIndex's `VectorStoreIndex` to PostgreSQL/pgvector. Supports HYBRID query mode (dense + BM25 via `tsvector`). |
| rank-bm25 | 0.2.2 | In-memory BM25 index for hybrid retrieval | Use as fallback or for local BM25 scoring outside PostgreSQL. The pgvector HYBRID mode handles BM25 natively via `tsvector`; `rank-bm25` is only needed if you want a Python-side BM25 pass independent of Postgres. |
| pgvector (Python) | 0.4.2 | pgvector Python adapter | Required for SQLAlchemy/psycopg2 integration with pgvector — provides `Vector` type, distance operators. |
| SQLAlchemy | 2.0.49 | ORM / query layer for PostgreSQL | Use for all Postgres interactions (metadata, agent state, eval results). 2.0 async API (`async_session`) pairs cleanly with FastAPI. |
| PyGithub | 2.9.1 | GitHub REST API client | The standard Python GitHub client. Covers all required read ops (search, issues, PRs, commits, file contents) and write ops (create issue, add comment). Includes rate limit introspection. Use with a PAT stored in env. |
| Typer | 0.25.1 | CLI framework | Built on Click, uses Python type hints — zero boilerplate for a developer-facing CLI. Add `rich` for styled output (plan display, confirmation prompts, streaming responses). Far less code than raw Click or argparse for this use case. |
| Rich | 14.x | Terminal output styling | Paired with Typer for tables (plan display), panels (agent responses), progress bars (indexing), and confirmation prompts. First-class portfolio visual. |
| Pydantic | 2.13.4 | Data validation / schema definitions | Used throughout: tool input/output schemas, agent state models, eval test case definitions. Pydantic v2 is required — do not use v1. FastAPI and LangChain both require v2. |
| DeepEval | 4.0.2 | Eval harness — agent tool-call accuracy, RAG metrics, hallucination | The right choice for this project. Pytest-native (`assert_test()`), has `ToolCorrectnessMetric` for agent tool-call accuracy, `FaithfulnessMetric`/`AnswerRelevancyMetric` for RAG, and `HallucinationMetric`. Supports 200+ test cases via dataset files. LangGraph agent callback handler built in. |
| RAGAS | 0.4.3 | RAG-specific evaluation metrics | Optional complement to DeepEval. Use for the RAG sub-pipeline evaluation specifically (context precision, context recall, answer faithfulness). DeepEval can import RAGAS metrics. If you pick one, pick DeepEval — it covers both RAG and agent tool-call evaluation. |
| Langfuse | 4.6.1 | Tracing / observability (self-hostable) | Preferred over LangSmith for this project: MIT-licensed, self-hostable via `docker-compose`, OpenTelemetry-native (v3+), framework-agnostic. LangSmith requires a paid enterprise license to self-host. Langfuse adds a single `docker-compose` service — keeps everything local. |
| python-dotenv | 1.x | Environment variable management | Standard for managing `OPENAI_API_KEY`, `GITHUB_TOKEN`, `DATABASE_URL` in `.env` files for local dev. |
| asyncpg | 0.30.x | Async PostgreSQL driver | Use with SQLAlchemy's async engine for non-blocking DB queries from FastAPI. |
| pytest | 8.x | Test runner | Pairs natively with DeepEval. Run `pytest` to execute the 200+ eval test cases. |
| pytest-asyncio | 0.24.x | Async test support | Required for testing async FastAPI routes and async LangGraph chains. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Fast package manager + virtual environments | Replaces `pip` + `venv`. `uv pip install` is 10-100x faster. Use for both local dev and Docker layer caching (`uv pip sync requirements.txt`). |
| ruff | Linting + formatting | Replaces `black` + `isort` + `flake8`. One tool, one config in `pyproject.toml`. |
| pre-commit | Git hooks | Run ruff on commit. Keeps code clean before CI. |
| Docker Compose v2 | Local orchestration | `docker compose up` (no hyphen in v2) for PostgreSQL + FastAPI + Langfuse. |

---

## Installation

```bash
# Core agent stack
uv pip install langgraph langchain langchain-openai openai

# RAG stack
uv pip install llama-index-core llama-index-vector-stores-postgres llama-index-llms-openai llama-index-embeddings-openai

# Database
uv pip install sqlalchemy asyncpg pgvector psycopg2-binary alembic

# GitHub integration
uv pip install PyGithub

# CLI
uv pip install typer rich

# Evaluation
uv pip install deepeval ragas

# Observability
uv pip install langfuse

# Utilities
uv pip install python-dotenv pydantic rank-bm25

# Dev
uv pip install --dev pytest pytest-asyncio ruff pre-commit
```

---

## Alternatives Considered

| Recommended | Alternative | Why Not / When Alternative Is Better |
|-------------|-------------|--------------------------------------|
| LangGraph 1.2 | LangChain AgentExecutor | AgentExecutor is officially deprecated for multi-agent use cases. LangGraph is the replacement. Only use AgentExecutor for a single-agent ReAct loop in a tutorial context. |
| LangGraph 1.2 | AutoGen (Microsoft) | AutoGen has a different philosophy (conversation-based, actor-model). Better for fully autonomous conversational agents. LangGraph gives more explicit control over plan→retrieve→execute flow and human confirmation steps — the right fit for this project. |
| LangGraph 1.2 | CrewAI | CrewAI is higher-level and opinionated. Good for rapid prototyping but hides state management. LangGraph is more transparent, which matters for a portfolio showcase proving engineering depth. |
| LlamaIndex | LangChain's RAG primitives | LangChain's retrievers work but LlamaIndex has significantly more mature RAG primitives: node parsers, metadata extractors, query fusion, hybrid retrieval. For a RAG-first project, use LlamaIndex for the RAG layer and LangGraph for orchestration. |
| PostgreSQL + pgvector | Qdrant, Weaviate, Chroma | Dedicated vector DBs have better ANN performance at scale, but pgvector on PostgreSQL keeps the stack to a single DB service. For a portfolio project under 1M vectors, pgvector HNSW is sufficient. Qdrant is the right choice if scaling beyond 10M vectors. |
| PostgreSQL + pgvector | Pinecone | Managed, excellent performance. Adds a cloud dependency and ongoing cost — incompatible with "runs fully local via docker-compose" requirement. |
| DeepEval | Custom pytest fixtures | Custom eval harness requires building metric implementations from scratch. DeepEval provides `ToolCorrectnessMetric`, `FaithfulnessMetric`, `HallucinationMetric` out of the box — directly matching the three headline eval metrics. |
| Langfuse | LangSmith | LangSmith requires Enterprise license to self-host. As an open-source MIT project running locally, Langfuse is strictly better: same capability, zero cost, one `docker-compose` service. |
| Typer | Click (raw) | Click requires more boilerplate. Typer generates help text, argument parsing, and completion from type hints — faster to build, easier to read in portfolio code review. |
| PyGithub | GitHub GraphQL (direct) | GraphQL gives access to more fields but requires writing queries manually. PyGithub covers all required operations (issues, PRs, commits, file content, search, comments) with a typed API. Use GraphQL only if PyGithub can't cover a specific required field. |
| text-embedding-3-small | all-MiniLM-L6-v2 (local) | Local embeddings avoid API cost but add infrastructure complexity (GPU/CPU inference server). For a portfolio project already using OpenAI API, `text-embedding-3-small` is the right tradeoff. Switch to a local model (via Ollama) only if API cost becomes a concern. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `langchain.agents.AgentExecutor` | Officially deprecated for multi-agent workflows. Creates a hidden ReAct loop with no state control. Does not support human-in-the-loop confirmation natively. | `langgraph` with explicit node graph |
| `llama-index` (top-level umbrella package v0.10 or earlier) | The old monolithic package. The ecosystem moved to modular packages in v0.10. Importing from the old package pulls in massive unused deps. | `llama-index-core` + specific integration packages |
| ChromaDB | Fine for prototyping but not production-ready in a Postgres-native stack. Adds a third DB service. You already have pgvector. | `llama-index-vector-stores-postgres` with pgvector |
| `gitpython` | Explicitly in maintenance mode — no new features, security fixes only. Designed for local git repo operations, not the GitHub API. | `PyGithub` for GitHub REST API calls |
| RAGAS as the sole eval framework | RAGAS covers RAG metrics well but lacks agent tool-call accuracy metrics. For this project's three-metric eval (task completion, tool-call accuracy, hallucination), RAGAS alone is insufficient. | `DeepEval` (which can import RAGAS metrics as a subset) |
| `black` + `isort` + `flake8` separately | Three tools doing one job. More config, more version conflicts, slower. | `ruff` handles all three |
| `pip` + `venv` | Dramatically slower than alternatives. Adds unnecessary friction to Docker builds. | `uv` |
| LangSmith (as primary observability) | Requires paid Enterprise license for self-hosting. Ties you to LangChain's closed platform. | `Langfuse` (MIT, self-hostable, OpenTelemetry-native) |
| `gpt-4-turbo` or `gpt-3.5-turbo` | Outdated. `gpt-4o` has the same or better capability at lower cost with faster inference. `gpt-3.5-turbo` is deprecated. | `gpt-4o` (function calling, structured outputs) |

---

## Stack Patterns by Variant

**For the planner→retriever→executor graph:**
- Use `LangGraph` `StateGraph` with typed `TypedDict` state
- Planner node: LangChain `ChatPromptTemplate` + GPT-4o → structured `Plan` (Pydantic model)
- Retriever node: LlamaIndex `QueryFusionRetriever` (BM25 + dense) → ranked `NodeWithScore` list
- Executor node: LangGraph `ToolNode` + PyGithub tool functions wrapped with `@tool`
- Human confirmation gate: LangGraph `interrupt()` before any write tool call

**For GitHub tool definitions (MCP-style):**
- Wrap each GitHub capability as a LangChain `@tool`-decorated function with a Pydantic input schema
- Group into read tools (no confirmation required) and write tools (require `interrupt()` confirmation)
- Register all tools with the executor node's `ToolNode`
- Do NOT use the actual MCP SDK unless you explicitly want a separate MCP server process — for v1, `@tool` definitions are equivalent and far simpler

**For hybrid retrieval:**
- Use LlamaIndex `PostgreSQLVectorStore` with `VectorStoreQueryMode.HYBRID` for BM25 + vector fusion at the DB level
- Apply Reciprocal Rank Fusion (RRF) as the merge strategy — already built into LlamaIndex's `QueryFusionRetriever`
- Add a cross-encoder reranker (`llama-index-postprocessor-cohere-rerank` or a local `cross-encoder/ms-marco-MiniLM`) for final candidate reranking

**For the eval harness:**
- Define test cases in JSON/YAML files: `query`, `expected_tools`, `expected_answer`, `reference_context`
- Use `DeepEval`'s `LLMTestCase` + `ToolCorrectnessMetric` for tool-call accuracy
- Use `FaithfulnessMetric` + `AnswerRelevancyMetric` for RAG quality
- Use `HallucinationMetric` for hallucination rate
- Run via `pytest` — DeepEval is pytest-native
- Target: ≥200 test cases, CI gate on aggregate metric thresholds

**For CLI streaming:**
- FastAPI SSE (`StreamingResponse`) for agent token-by-token output
- Typer command calls the FastAPI endpoint and streams to Rich `Live` display
- Rich `Panel` for plan display, `Confirm.ask()` for write confirmation

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| langgraph==1.2.0 | langchain==1.3.0 | LangGraph 1.x requires LangChain 0.3+/1.x. The 0.2.x LangGraph line requires LangChain 0.2.x. Do not mix. |
| llama-index-core==0.14.x | pydantic==2.x | LlamaIndex 0.10+ requires Pydantic v2. Do not use with Pydantic v1. |
| fastapi==0.115.x | pydantic==2.13.x | FastAPI 0.100+ requires Pydantic v2. Fully compatible. |
| pgvector==0.4.2 | sqlalchemy==2.0.x | pgvector Python 0.3+ supports SQLAlchemy 2.0 async. Use `asyncpg` as the driver for async. |
| deepeval==4.0.x | langchain==1.3.x | DeepEval 4.x has native LangGraph callback handler. Compatible with LangChain 1.x. |
| openai==2.36.0 | langchain-openai | Use `langchain-openai` which wraps the official `openai` SDK. Do not import `openai` directly in agent code — let LangChain manage the client. |
| Python 3.11 | All above | All packages support 3.11. Python 3.13 is still risky for some C-extension packages (pgvector, asyncpg). Stay on 3.11 until ecosystem catches up. |

---

## Sources

- PyPI: `langgraph` — verified version 1.2.0, released 2026-05-12 (HIGH confidence)
- PyPI: `llama-index-core` — verified version 0.14.21, released 2026-04-21 (HIGH confidence)
- PyPI: `langchain` — verified version 1.3.0, released 2026-05-12 (HIGH confidence)
- PyPI: `openai` — verified version 2.36.0, released 2026-05-07 (HIGH confidence)
- PyPI: `deepeval` — verified version 4.0.2, released 2026-05-13 (HIGH confidence)
- PyPI: `PyGithub` — verified version 2.9.1, released 2026-04-14 (HIGH confidence)
- PyPI: `pgvector` (Python) — verified version 0.4.2, released 2025-12-05 (HIGH confidence)
- PyPI: `ragas` — verified version 0.4.3, released 2026-01-13 (HIGH confidence)
- PyPI: `langfuse` — verified version 4.6.1, released 2026-05-08 (HIGH confidence)
- PyPI: `typer` — verified version 0.25.1, released 2026-04-30 (HIGH confidence)
- PyPI: `pydantic` — verified version 2.13.4, released 2026-05-06 (HIGH confidence)
- PyPI: `sqlalchemy` — verified version 2.0.49, released 2026-04-03 (HIGH confidence)
- PyPI: `rank-bm25` — verified version 0.2.2, released 2022-02-16 (HIGH confidence — stable, no updates needed)
- LangChain official: https://www.langchain.com/langgraph — LangGraph is the recommended multi-agent orchestration path (HIGH confidence)
- DeepEval docs: https://deepeval.com/docs/metrics-tool-correctness — `ToolCorrectnessMetric` confirmed (HIGH confidence)
- LlamaIndex docs: https://developers.llamaindex.ai/python/examples/retrievers/bm25_retriever/ — BM25Retriever + QueryFusionRetriever confirmed (HIGH confidence)
- Langfuse vs LangSmith: https://langfuse.com/faq/all/langsmith-alternative — self-host licensing difference confirmed (HIGH confidence)
- LlamaIndex pgvector: https://pypi.org/project/llama-index-vector-stores-postgres/ — HYBRID query mode confirmed (MEDIUM confidence — tested against docs summary)
- WebSearch: GitPython maintenance mode — confirmed via GitHub repo notice (HIGH confidence)
- WebSearch: FastAPI async + Pydantic v2 as greenfield LLM backend standard — confirmed by multiple sources (HIGH confidence)

---

*Stack research for: CLI-first multi-agent developer productivity platform*
*Researched: 2026-05-14*
