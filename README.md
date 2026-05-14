# Developer Productivity Agent Platform

A multi-agent system that turns natural-language developer queries into executed
GitHub SDLC actions. A **planner** decomposes a query into a multi-step plan, a
**retriever** pulls context from a hybrid RAG index (code, issues/PRs, docs,
commits), and an **executor** calls GitHub tools — synthesizing a cited answer or
performing confirmation-gated write actions.

> Full setup, architecture, and demo documentation land in Phase 6. This stub
> exists so the package builds.

## Quick start (Phase 1)

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -e ".[eval]"
cp .env.example .env          # fill in OPENAI_API_KEY + GITHUB_TOKEN
docker compose up -d          # PostgreSQL + pgvector
devagent migrate              # schema + checkpoint tables
devagent seed-eval            # golden eval cases
devagent index psf/requests   # ingest the default target repo
```

## Stack

Python 3.12 · LangGraph · LangChain · LlamaIndex · FastAPI · PostgreSQL/pgvector ·
OpenAI API · Typer + Rich · DeepEval · Langfuse · Docker.
