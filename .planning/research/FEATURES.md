# Feature Research

**Domain:** Multi-agent developer-productivity / AI coding-assistant CLI
**Researched:** 2026-05-14
**Confidence:** HIGH (core agent/eval patterns), MEDIUM (RAG-for-code specifics), HIGH (GitHub tool surface — official MCP server docs)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any credible multi-agent developer tool must have. Missing any of these makes the product feel incomplete to a senior engineer reviewer.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Natural-language query interface (CLI) | Every AI coding tool accepts free-form questions | LOW | `devagent ask "..."` is the entry point; readline/prompt_toolkit for interactive mode |
| Code Q&A over a repository | Core RAG use case; Copilot, Cursor, and every peer do this | MEDIUM | Requires indexed repo; answers must cite file:line |
| Issue and PR read access | Developers expect the agent to know project state | MEDIUM | Fetch issue body, comments, labels, linked PRs via GitHub REST/MCP tools |
| Cross-source investigation | Query that spans code + issue + commit history in one answer | HIGH | The planner must route retrieval across multiple indexes; table stakes for a "deep" agent |
| Source citations in every answer | Without citations, hallucination is invisible | MEDIUM | Every fact in the answer must link to chunk origin (file, issue #, commit SHA) |
| Hybrid retrieval (BM25 + dense vector) | Pure vector search misses exact identifiers; pure keyword misses semantics | HIGH | pgvector for dense; BM25 via PostgreSQL full-text or rank-BM25; reciprocal-rank fusion to merge |
| Write actions gated by explicit user confirmation | Developers will not trust a tool that writes without asking | LOW | Print the action plan in plain language, `[y/N]` prompt before any mutation |
| Structured plan display before execution | Planner output must be readable before user confirms | MEDIUM | Pretty-print plan steps with tool names and parameters; show dry-run cost |
| Error messages that explain root cause | Vague errors destroy trust | LOW | Wrap all tool exceptions; surface GitHub API errors with actionable text |
| Streaming output for long responses | Blank terminal during multi-second LLM calls is unacceptable | MEDIUM | Stream tokens from OpenAI API; flush to stdout incrementally |
| Configurable GitHub repo context | Must know which repo(s) to operate on | LOW | `--repo owner/name` flag or `.devagent.yml` project config |
| Rate-limit and API error resilience | GitHub and OpenAI both rate-limit; agent must not crash | LOW | Exponential backoff with jitter; surface wait time to user |
| Docker-compose single-command startup | Reviewers will run this; complex setup = bad first impression | LOW | `docker-compose up` must start all services (Postgres, API, CLI) with no manual steps |

### Differentiators (Competitive Advantage)

Features that showcase engineering depth and set this project apart as a portfolio piece.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Eval harness with 200+ test cases measuring three metrics | Proves agent reliability quantitatively — no competitor showcases this openly | HIGH | Task completion rate, tool-call accuracy, hallucination/faithfulness rate; structured as golden dataset → deepeval-style test cases |
| Three-agent decomposition (Planner / Retriever / Executor) | Explicit separation makes each agent's role inspectable and improvable; most tools are black-box | HIGH | Planner: LangChain agent with CoT/ReAct scaffold; Retriever: LlamaIndex query engine; Executor: tool-dispatch with confirmation gate |
| AST-aware code chunking | Line-based splits break function boundaries; AST chunking preserves semantic units | HIGH | Use tree-sitter to chunk by function/class boundaries; attach metadata (lang, file, symbol name) to each chunk |
| Chain-of-thought + ReAct scaffolding with logged reasoning traces | Reasoning traces are visible in the CLI output; users see why each tool was chosen | MEDIUM | Emit Thought/Action/Observation steps to stderr or a `--verbose` flag; stored in trace log for eval replay |
| Dual retrieval path: GitHub live API + pre-indexed RAG | Fresh issues/PRs fetched live; code and commit history from indexed store | MEDIUM | Retriever agent routes to live vs. indexed based on query type and data freshness requirements |
| Prompt-iteration workflow tied to eval metrics | Developers can change a prompt, re-run eval, and see metric deltas — this is the engineering story | HIGH | `devagent eval run --compare v1 v2` shows metric diff table |
| Hallucination rate as a first-class dashboard metric | Most tools ignore this; surfacing it is a trust-builder | MEDIUM | Faithfulness scorer using LLM-as-judge against retrieved context; logged per query |
| Tool-call trace export (JSONL) | Enables post-hoc debugging and eval replay without rerunning the agent | MEDIUM | Each tool invocation logged: tool name, input params, output, latency, agent step index |
| Commit history RAG (semantic search over diffs and messages) | Copilot and Cursor do not index commit history for Q&A | HIGH | Chunk commits as (message + diff summary); enables queries like "when was X introduced and why?" |
| Confirmed write actions with full plan audit log | Every mutation is logged with who confirmed it, what was sent, and the API response | MEDIUM | Append-only audit log in Postgres; CLI shows summary after execution |

### Anti-Features (Explicitly Not Buildable or Harmful)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Fully autonomous writes (no confirmation) | Feels more "agentic"; reduces friction | One hallucinated file path or PR target causes real damage; destroys demo credibility | Explicit `[y/N]` gate; `--dry-run` flag that prints the exact API call without executing |
| Web UI / chat frontend | Looks more polished to non-technical observers | Doubles scope (React app, auth, WebSockets) with no engineering showcase value for backend-heavy portfolio | CLI is the right interface for a developer tool; invest saved time in eval harness depth instead |
| Jira / Confluence integration (v1) | Natural ask for SDLC tooling | Requires OAuth flows, different data model, separate RAG indexes, and doubles test surface; GitHub is richer for a portfolio demo | Defer to v2; document the extension point clearly in architecture |
| Streaming real-time re-indexing on every git push | Feels impressive in demos | Webhook plumbing, incremental diff chunking, and index consistency are a project in themselves | Scheduled or on-demand re-index; document how to trigger it |
| Multi-repo cross-search (v1) | Developers often work across repos | Requires per-repo index isolation, auth scoping per repo, and query routing complexity | Single-repo deep integration in v1; multi-repo is an additive layer, note the extension point |
| LLM fine-tuning on codebase data | Seems like the "right" approach | GPU cost, training pipeline, eval contamination; unnecessary when RAG + few-shot already achieves high faithfulness | RAG + few-shot examples in system prompt; fine-tuning deferred indefinitely |
| Autonomous issue/PR creation without human-written content | Feels like AI magic | Hallucinated issue bodies, wrong labels, or PRs targeting wrong branches are embarrassing in a portfolio demo | Agent drafts the body and presents it for review; human edits before confirmation |

---

## Feature Dependencies

```
[Hybrid RAG Index (BM25 + dense)]
    └──requires──> [Document ingestion pipeline (code, issues, commits)]
                       └──requires──> [GitHub read tools (files, issues, commits)]
                       └──requires──> [AST-aware code chunker]
                       └──requires──> [pgvector schema + embeddings]

[Planner Agent]
    └──requires──> [LangChain agent executor with ReAct/CoT scaffold]
    └──requires──> [Tool registry (all GitHub tool definitions)]

[Retriever Agent]
    └──requires──> [Hybrid RAG Index]
    └──requires──> [GitHub live API read tools]

[Executor Agent]
    └──requires──> [Tool registry]
    └──requires──> [Confirmation gate (y/N prompt)]
    └──requires──> [Audit log (Postgres)]

[Write actions (create issue, comment PR)]
    └──requires──> [Executor Agent]
    └──requires──> [Confirmation gate]

[Eval harness]
    └──requires──> [Tool-call trace export (JSONL)]
    └──requires──> [Golden dataset (200+ test cases)]
    └──requires──> [Metric scorers: task completion, tool-call accuracy, faithfulness]
    └──enhances──> [Prompt-iteration workflow]

[Chain-of-thought / ReAct scaffold]
    └──enhances──> [Planner Agent]
    └──enhances──> [Tool-call trace export] (traces are CoT outputs)

[Hallucination rate metric]
    └──requires──> [Faithfulness scorer (LLM-as-judge)]
    └──requires──> [Retrieved context captured per query]

[Source citations in answers]
    └──requires──> [Retriever Agent returning chunk metadata]
    └──requires──> [Answer generation that references chunk IDs]

[Prompt-iteration workflow]
    └──requires──> [Eval harness]
    └──requires──> [Tool-call trace export]
    └──enhances──> [All three agents' system prompts]

[Streaming output]
    └──conflicts──> [Synchronous batch plan display] (must buffer plan before streaming answer)
```

### Dependency Notes

- **Hybrid RAG Index requires GitHub read tools:** The ingestion pipeline calls GitHub API to pull files, issues, and commits before chunking and embedding. GitHub read tooling is therefore a Phase 1 prerequisite for everything downstream.
- **Eval harness requires tool-call trace export:** Without structured JSONL traces, the tool-call accuracy metric has nothing to score against. Traces must be wired in before the harness is built.
- **Confirmation gate requires Executor Agent:** The gate is not a standalone feature — it is the Executor's output step. Build together in the same phase.
- **Hallucination rate requires retrieved context captured per query:** The faithfulness scorer compares the final answer against retrieved chunks. The Retriever must log which chunks contributed to each answer; this is a non-obvious data dependency.
- **Streaming output conflicts with synchronous plan display:** When the Planner produces a multi-step plan, the CLI must render the full plan before executing and streaming the final answer. Implement plan display as a synchronous step, then switch to streaming for the synthesis phase.

---

## MVP Definition

### Launch With (v1)

- [ ] Hybrid RAG index over code, issues, READMEs, commit history — core value delivery
- [ ] Planner / Retriever / Executor three-agent split with ReAct/CoT scaffolding — headline architecture story
- [ ] GitHub read tools: fetch file, list issues, get PR diff, list commits — retrieval foundation
- [ ] GitHub write tools: create issue, add comment on PR — demonstrates real SDLC action
- [ ] Confirmation gate for all write actions — safety and trust
- [ ] Source citations (file:line, issue #, commit SHA) in every answer — hallucination visibility
- [ ] Tool-call trace export (JSONL) — required for eval harness
- [ ] Eval harness with 200+ golden test cases measuring task completion, tool-call accuracy, hallucination rate — core deliverable, not optional
- [ ] `docker-compose up` single-command deployment — reviewer experience
- [ ] CLI: `ask`, `eval run`, `index` subcommands with streaming output and verbose/trace mode

### Add After Validation (v1.x)

- [ ] AST-aware code chunking — improves retrieval precision; add once base chunking is benchmarked
- [ ] Prompt-iteration diff workflow (`eval run --compare v1 v2`) — add once eval harness is stable
- [ ] Incremental re-indexing (on-demand trigger) — add once initial indexing is proven correct

### Future Consideration (v2+)

- [ ] Jira / Confluence integration — deferred; clear extension point documented in architecture
- [ ] Multi-repo cross-search — additive layer on top of single-repo indexing
- [ ] GitHub Actions / workflow status tools — valuable but not part of core SDLC query/action loop

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Hybrid RAG index | HIGH | HIGH | P1 |
| Three-agent orchestration (Planner/Retriever/Executor) | HIGH | HIGH | P1 |
| GitHub read tools (7 core operations) | HIGH | MEDIUM | P1 |
| Confirmation gate + write tools (create issue, comment PR) | HIGH | LOW | P1 |
| Source citations in answers | HIGH | MEDIUM | P1 |
| Eval harness (200+ cases, 3 metrics) | HIGH | HIGH | P1 |
| Tool-call trace export (JSONL) | HIGH | MEDIUM | P1 |
| ReAct/CoT scaffolding in Planner | HIGH | MEDIUM | P1 |
| Streaming CLI output | MEDIUM | MEDIUM | P1 |
| docker-compose deployment | HIGH | LOW | P1 |
| AST-aware code chunking | MEDIUM | HIGH | P2 |
| Prompt-iteration diff workflow | MEDIUM | MEDIUM | P2 |
| Hallucination dashboard in CLI | MEDIUM | MEDIUM | P2 |
| Incremental on-demand re-indexing | MEDIUM | MEDIUM | P2 |
| Jira/Confluence integration | LOW | HIGH | P3 |
| Multi-repo cross-search | LOW | HIGH | P3 |
| Web UI | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | GitHub Copilot / Copilot Chat | Cursor | Our Approach |
|---------|-------------------------------|--------|--------------|
| Code Q&A | Yes — chat over current file/repo | Yes — Codebase index, semantic search | Yes — hybrid BM25 + vector over full repo |
| Issue/PR awareness | Partial (MCP integration in preview) | No native GitHub integration | Yes — first-class; live API + indexed |
| Cross-source investigation (code + issue + commit) | No | No | Yes — planner routes across all three sources |
| Commit history RAG | No | No | Yes — diff summaries indexed and searchable |
| Confirmed write actions via CLI | No (IDE-based) | No | Yes — confirmation gate before any mutation |
| Explicit agent plan display | No — black box | No | Yes — planner step list rendered before execution |
| Eval harness / quantified reliability | Not public | Not public | Yes — 200+ cases, three metrics, public in repo |
| Source citations per answer | Partial | Partial | Yes — required for every response |
| AST-aware chunking | Unknown | Partial (Cursor uses tree-sitter internally) | Yes (P2) — using tree-sitter explicitly |
| Reasoning trace visibility | No | No | Yes — `--verbose` shows Thought/Action/Observation |

---

## Sources

- [Confident AI: LLM Agent Evaluation Complete Guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide) — task completion, tool-call accuracy, faithfulness metrics
- [DeepEval GitHub](https://github.com/confident-ai/deepeval) — evaluation framework, golden dataset structure
- [GitHub MCP Server README](https://github.com/github/github-mcp-server/blob/main/README.md) — 22 toolsets, read vs write surface
- [ReAct Prompting Guide](https://www.promptingguide.ai/techniques/react) — Thought/Action/Observation scaffolding
- [cAST: AST-based Code Chunking](https://arxiv.org/html/2506.15655v1) — AST chunking rationale for code RAG
- [Citation-Grounded Code Comprehension](https://arxiv.org/html/2512.12117v1) — line-level citation verification for RAG
- [Weaviate: Chunking Strategies for RAG](https://weaviate.io/blog/chunking-strategies-for-rag) — chunking strategy tradeoffs
- [InfoQ: AI Agent CLI Patterns](https://www.infoq.com/articles/ai-agent-cli/) — confirmation prompts, dry-run, --no-interactive patterns
- [GitHub Agentic Workflows Blog](https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/) — issue triage, PR management, write-gating patterns
- [HyperAgent / MASAI architecture](https://dev.to/apssouza22/a-deep-dive-into-deep-agent-architecture-for-ai-coding-assistants-3c8b) — multi-agent decomposition patterns for coding
- [Evaluating LLM Agents in Multi-Step Workflows](https://www.codeant.ai/blogs/evaluate-llm-agentic-workflows) — end-to-end vs component-level eval

---

*Feature research for: Multi-agent developer-productivity platform (GitHub-focused CLI)*
*Researched: 2026-05-14*
