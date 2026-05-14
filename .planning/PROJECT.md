# Developer Productivity Agent Platform

## What This Is

A multi-agent system that turns complex, natural-language developer queries into
executed SDLC actions against GitHub. A planner agent decomposes a query into a
multi-step plan, a retriever agent pulls context from a hybrid RAG index (code,
issues/PRs, docs, commits), and an executor agent calls GitHub tools — synthesizing
a final answer or performing confirmed write actions. It is CLI-first and built as a
portfolio-grade showcase of agent, RAG, and evaluation engineering.

## Core Value

Given a complex developer query, the agent autonomously produces a correct multi-step
plan and executes it against GitHub with measurably high task-completion and tool-call
accuracy — and the eval harness proves it.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Multi-agent orchestration: planner decomposes queries into multi-step plans; retriever and executor agents carry them out and synthesize responses
- [ ] Hybrid RAG pipeline (LlamaIndex + pgvector): BM25 + dense vector retrieval over repo source code, issues/PRs, READMEs/docs, and commit history
- [ ] GitHub tool integration via MCP-style tool definitions: read operations (search, fetch issues/PRs/commits/files) and write operations (create issue, comment on PR) gated behind explicit user confirmation
- [ ] Query coverage: code/repo Q&A, issue/PR triage & summary, action execution (writes), cross-source investigation
- [ ] CLI interface for submitting queries and reviewing/confirming agent plans and actions
- [ ] Benchmarking & evaluation harness: measures task completion rate, tool-call accuracy, and hallucination rate across 200+ test cases
- [ ] Prompt engineering framework with chain-of-thought scaffolding to iteratively improve agent reliability against eval metrics
- [ ] Dockerized deployment (docker-compose) with setup documentation; AWS deployment described in docs but not required to run live

### Out of Scope

- Jira integration — deferred to v2; GitHub-only keeps v1 focused and deep
- Confluence integration — deferred to v2; same reason
- Web UI / chat frontend — CLI-first for v1; a developer tool reads naturally in the terminal
- Live AWS-hosted instance — showcase ships dockerized + documented; live hosting adds cost/maintenance without proportional showcase value
- Fully autonomous writes without confirmation — all GitHub mutations require explicit user confirmation in v1

## Context

- Portfolio / resume showcase project. Polish, clarity of architecture, and a compelling
  demo matter as much as raw functionality. Should read well as an engineering artifact.
- Tech stack (from the original spec): Python, LangChain (multi-agent orchestration),
  LlamaIndex (RAG), FastAPI, PostgreSQL/pgvector, OpenAI API, Docker, AWS.
- The three-agent decomposition (planner / retriever / executor) and the eval harness
  are the headline engineering stories — both should be first-class, not afterthoughts.
- "MCP-style tool definitions" means GitHub capabilities are exposed as structured,
  declaratively-defined tools the executor agent can call.

## Constraints

- **Tech stack**: Python + LangChain + LlamaIndex + FastAPI + PostgreSQL/pgvector + OpenAI API — fixed by the project spec
- **Integrations**: GitHub only for v1 — Jira/Confluence explicitly deferred
- **Interface**: CLI-first — no web frontend in v1
- **Safety**: All GitHub write actions require explicit user confirmation before execution
- **Deployment**: Must be runnable via docker-compose with documented setup; live hosting not required
- **Evaluation**: Eval harness must cover 200+ test cases across the three metrics — it is a core deliverable, not optional

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| GitHub-only for v1 | Ship one integration deeply rather than three shallowly; richest and most demo-able source | — Pending |
| Eval harness is a core deliverable | Headline engineering story for a portfolio showcase; proves agent reliability quantitatively | — Pending |
| CLI-first interface | Natural for a developer tool; fastest path to a working, demo-able system | — Pending |
| Read + write with confirmation | Demonstrates real SDLC action execution while keeping mutation risk controlled | — Pending |
| Dockerized + docs, not live AWS | Showcase value without ongoing hosting cost/maintenance | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-14 after initialization*
