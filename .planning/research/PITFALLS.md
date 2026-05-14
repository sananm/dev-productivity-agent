# Pitfalls Research

**Domain:** Multi-agent developer productivity platform (CLI, hybrid RAG, GitHub integration, eval harness)
**Researched:** 2026-05-14
**Confidence:** HIGH (most pitfalls verified across multiple production post-mortems and official docs)

---

## Critical Pitfalls

### Pitfall 1: Error Amplification Across Agent Hops

**What goes wrong:**
The planner produces a subtly wrong plan — wrong branch name, misidentified issue number, ambiguous intent. The retriever treats this as ground truth and fetches the wrong context. The executor then acts on that bad context. Research shows unstructured multi-agent pipelines amplify errors up to 17x compared to single-agent baselines. By the time the executor runs, no agent has visibility into the original mistake.

**Why it happens:**
Agents pass raw message history or full outputs between hops rather than validated, structured state objects. Each agent trusts upstream output without cross-checking preconditions. LangChain's default agent-to-agent communication is conversational (text-in, text-out), not schema-validated.

**How to avoid:**
Define a typed `PlanStep` and `RetrievalResult` Pydantic schema. Each agent receives and emits these validated objects, never raw text. Add a lightweight validation gate after the planner: before the retriever runs, assert the plan references resources that actually exist (repo, issue ID, branch). Use structured outputs (OpenAI `response_format=json_schema` with `strict=True`) on every inter-agent boundary.

**Warning signs:**
- Executor calls a GitHub endpoint on a resource that doesn't exist
- Retriever returns chunks unrelated to the original query
- Final answer contains correct-sounding but wrong entity names (wrong PR number, wrong filename)

**Phase to address:** Multi-agent orchestration build phase (planner + retriever + executor wiring)

---

### Pitfall 2: Agent Infinite Loops and Token Budget Exhaustion

**What goes wrong:**
An agent hits a tool call that fails (e.g., GitHub 404, empty retrieval result) and re-plans, re-tries, or asks a clarifying question that another agent cannot answer. The loop runs until the context window is exhausted or the API bill explodes. A single runaway agent can burn hundreds of dollars in minutes.

**Why it happens:**
No hard loop limit is set. LangChain's AgentExecutor has a `max_iterations` parameter that defaults to 15 — often left at default without considering that 15 × large tool output = massive context. There is also no circuit breaker when a tool call returns an error N times in a row.

**How to avoid:**
Set `max_iterations=5` for the executor agent and `max_iterations=3` for the planner. Add a per-task token budget enforced in the orchestrator (e.g., 8K tokens consumed → abort and surface error). Implement a circuit breaker: if the same tool is called with the same arguments twice consecutively, abort. Set hard OpenAI API account spending limits. Use `handle_parsing_errors=True` in LangChain but also add your own error-count ceiling.

**Warning signs:**
- OpenAI cost per query exceeding $0.50 during dev testing
- Latency per query exceeding 30 seconds
- Logs showing the same tool call repeated with nearly identical arguments
- `max_iterations` hit consistently on a class of queries

**Phase to address:** Multi-agent orchestration build phase; cost/observability instrumentation phase

---

### Pitfall 3: Context Window Bloat from Raw History Passing

**What goes wrong:**
Each agent pass appends full conversation history, tool outputs, and retrieval chunks to the next agent's context. By the third agent (executor), the context is dominated by retrieval noise rather than actionable plan state. The model starts contradicting earlier decisions or ignoring critical plan details buried deep in context.

**Why it happens:**
The naive LangChain pattern passes `chat_history` as a list of messages. When retrieval returns 10 chunks of 500 tokens each, plus planner CoT, plus tool call outputs, the executor receives 6K+ tokens of noise before seeing the actual task.

**How to avoid:**
Pass structured summaries between agents, not raw history. The orchestrator maintains a `AgentState` dataclass with: `original_query`, `plan` (list of `PlanStep`), `retrieved_context` (top-3 chunks only, pre-filtered), `execution_log` (tool call results, compact format). Each agent receives only its relevant slice of `AgentState`. For retrieval, pass at most 3-5 chunks; re-rank before passing to executor.

**Warning signs:**
- Input token count growing linearly with plan complexity
- Executor ignoring plan steps that appear early in context
- LLM outputs that repeat or contradict planner decisions

**Phase to address:** Multi-agent orchestration + RAG pipeline integration phase

---

### Pitfall 4: Naive Code Chunking Destroying Retrieval Quality

**What goes wrong:**
Fixed-size token chunking (e.g., 512 tokens with 50-token overlap) splits Python functions in the middle, separates class definitions from their methods, and severs docstrings from the function signatures they describe. BM25 then scores these fragments poorly on keyword queries, and dense retrieval averages out the signal from incoherent fragments. Retrieval precision collapses silently — the RAG pipeline returns chunks, but they are wrong chunks.

**Why it happens:**
LlamaIndex's default `SimpleNodeParser` uses fixed-size chunking. Developers accept the default without recognizing that code has syntactic structure that must be preserved. A 1000-line file split every 512 tokens will have function bodies split across 2-3 chunks with no chunk being self-contained.

**How to avoid:**
Use LlamaIndex's `CodeSplitter` (tree-sitter-based) for source files — it splits on function/class boundaries. Use 80-160 token chunks for code (per LlamaIndex team recommendation). For issues, PRs, and commits (prose), use `SentenceWindowNodeParser` with window_size=3. Maintain separate indices per document type (code index, issue index, commit index) with type-aware chunking configs. Test retrieval quality on 20 hand-curated queries before wiring to agents.

**Warning signs:**
- Retrieved chunks ending mid-function or starting in the middle of a class body
- Retrieval returning the same file multiple times with different fragment offsets
- Agent answers that are close but wrong (right file, wrong function body)

**Phase to address:** RAG pipeline build phase (indexing + chunking design)

---

### Pitfall 5: BM25/Dense Fusion Weight Tuning Ignored

**What goes wrong:**
RRF (Reciprocal Rank Fusion) is used as default with k=60 regardless of corpus size. On a small repository (< 500 files, < 5K chunks), k=60 flattens meaningful rank differences between positions 1 and 10, making the hybrid search perform worse than dense-only. The developer sees mediocre retrieval, doesn't know why, and tunes prompts instead of the retrieval layer.

**Why it happens:**
RRF is presented as parameter-free and safe. The k parameter (default 60) is rarely documented as corpus-size-sensitive. LlamaIndex's hybrid retrieval wiring abstracts this away, making it invisible.

**How to avoid:**
For a portfolio-scale repo corpus (< 10K chunks), drop k to 10-15. Measure retrieval quality with a held-out set of 20-30 query/expected-chunk pairs using Hit Rate@5 and MRR before integrating with agents. If BM25 is hurting results on semantic queries, reduce its weight; if dense retrieval misses exact symbol names, increase BM25 weight. Document the tuning rationale — it's a showcase artifact.

**Warning signs:**
- Hybrid retrieval performing worse than pure dense on the same query set
- BM25 returning chunks that repeat a query keyword 50+ times but have no semantic relevance
- Hit Rate@5 below 0.7 on your hand-curated query set

**Phase to address:** RAG pipeline build phase

---

### Pitfall 6: GitHub API Rate Limit Exhaustion During Index Build

**What goes wrong:**
The indexing pipeline fetches all issues, PRs, commits, and file contents using unauthenticated or PAT-authenticated requests. A medium-sized repository (500+ issues, 200+ PRs, 1K+ commits) will exhaust the 5,000 req/hour limit mid-indexing, causing partial index builds that fail silently. The secondary rate limit (100 concurrent requests) trips even earlier if the pipeline is async without throttling.

**Why it happens:**
Each GitHub API resource (issue body, comment, file content) is a separate request. Listing paginated results also counts. Developers fetch eagerly without checking `X-RateLimit-Remaining` headers. GitHub's secondary rate limit on concurrent requests is poorly documented and hits before primary limits on async pipelines.

**How to avoid:**
Use a GitHub App installation token (higher limits, up to 15K req/hour for apps vs 5K for PATs). Implement exponential backoff on 429/403 responses, reading the `Retry-After` or `X-RateLimit-Reset` header. Throttle to no more than 80 concurrent requests. Cache raw API responses to disk (or a simple SQLite) before embedding — this decouples fetch from index and allows re-runs without re-fetching. Paginate with explicit `per_page=100`. Pre-check `X-RateLimit-Remaining` before large batch fetches.

**Warning signs:**
- 403 or 429 responses with `X-RateLimit-Remaining: 0`
- Index build completing with fewer documents than expected (partial index)
- `abuse detection mechanism` errors in GitHub API response body

**Phase to address:** GitHub integration + RAG indexing phase

---

### Pitfall 7: Tool Call Hallucination and Malformed Arguments

**What goes wrong:**
The executor agent calls a GitHub tool with arguments that look plausible but are wrong: an issue number that doesn't exist, a branch name with a typo, or a `body` field that exceeds GitHub's character limit. Worse, the agent hallucinates a tool entirely (e.g., `bulk_search_issues`) that isn't defined. Without output validation, the tool call either silently fails or the error propagates back into context where the agent may retry with equally bad arguments.

**Why it happens:**
LLMs are probabilistic. Without strict JSON schema enforcement on tool call outputs, GPT-4o achieves under 40% schema compliance in unguarded settings (per OpenAI's own research). LangChain tools with loosely typed `args_schema` let malformed inputs through to the actual HTTP call.

**How to avoid:**
Use OpenAI's `strict=True` structured outputs for all tool calls. Define Pydantic v2 schemas for every GitHub tool's input args and validate before execution. Add a `tool_exists` guard: maintain an explicit registry of available tool names; if the LLM calls a name not in the registry, surface an error before any HTTP call is made. Validate output constraints (e.g., GitHub issue body <= 65,536 chars) at the tool layer. Use `response_format={"type": "json_schema", "json_schema": {...}, "strict": True}` on executor agent calls.

**Warning signs:**
- HTTP 422 from GitHub API (validation failed — malformed request body)
- HTTP 404 from GitHub API (resource referenced by agent doesn't exist)
- LangChain `OutputParserException` on tool argument parsing
- Same tool called 3+ times with slight argument variations

**Phase to address:** Executor agent + tool definition phase

---

### Pitfall 8: Eval Harness Non-Determinism Making Metrics Meaningless

**What goes wrong:**
The eval harness runs 200 test cases, but because temperature > 0, the same test passes on one run and fails the next. Developers report a "task completion rate of 82%" that is actually 78-87% depending on the run. The metric becomes noise, the harness loses credibility as a portfolio artifact, and prompt iteration can't be measured reliably.

**Why it happens:**
LLMs are non-deterministic at temperature > 0. Eval harnesses that use LLM-as-a-judge inherit this non-determinism at two levels: the system under test and the judge. Test cases with subjective pass/fail criteria (e.g., "is this a good summary?") make variance worse. Most RAG/agent evals don't set `temperature=0` on the evaluation calls.

**How to avoid:**
Set `temperature=0` (or `temperature=0.1` max) for all eval runs. Use deterministic metrics where possible: tool-call accuracy (correct tool + correct args = 1, else 0), exact-match or fuzzy-match on extracted entities (PR number, issue title), and presence-of-required-fields checks. For hallucination rate: define it as "ratio of factual claims in output that contradict ground-truth GitHub data" — verifiable mechanically. Reserve LLM-as-judge only for plan quality scoring, and run it 3 times and take the majority vote. Seed random number generators in test fixture setup.

**Warning signs:**
- Same test case flipping pass/fail across consecutive runs
- Metric variance > 5 percentage points between identical eval runs
- LLM judge scores that correlate more with output length than accuracy

**Phase to address:** Eval harness build phase (core deliverable — must be designed right from the start)

---

### Pitfall 9: Gameable Task Completion Metric

**What goes wrong:**
Task completion rate is measured as "did the agent produce an output?" rather than "did the agent produce the correct output?" An agent that always returns a confident-sounding answer scores 100% completion but 30% accuracy. The metric looks good on the portfolio but doesn't prove what it claims to prove.

**Why it happens:**
Task completion is easy to measure (non-empty output = complete). Correctness requires ground truth. Building 200 ground-truth test cases is laborious, so developers measure the proxy instead of the real thing.

**How to avoid:**
Treat task completion as a necessary but not sufficient metric. Define a separate `task_success` metric: completion + correct tool called + correct resource identified + output matches expected summary (fuzzy match against ground-truth). Build ground truth for at least 50 cases manually (test cases over real repos), use templates for the remaining 150. Document the distinction clearly in the portfolio — showing you know the difference is more impressive than a high number.

**Warning signs:**
- Task completion rate significantly higher than tool-call accuracy rate
- Agent outputs that are fluent but contain wrong file paths, wrong branch names, wrong PR authors

**Phase to address:** Eval harness build phase

---

### Pitfall 10: Stale RAG Index After Repository Changes

**What goes wrong:**
The index is built once during setup. After new commits, issues, or PRs are created in the target repo, the agent retrieves outdated context and gives answers that reference merged branches, closed issues, or superseded code. For a portfolio demo, the agent appears to hallucinate when it's actually answering based on stale data.

**Why it happens:**
Incremental indexing is harder than full re-indexing. Developers defer it as "nice to have." The BM25 index is a separate artifact from the pgvector index — updating one without the other creates inconsistency.

**How to avoid:**
Build a `refresh` CLI command that re-indexes a specific resource type (issues, PRs, commits, code) without a full teardown. Use GitHub webhook events (or a polling mechanism on a cron) to detect changes. Store a `last_indexed_at` timestamp per document in the metadata; include it in retrieval results so the agent can signal "this context is N days old." Ensure BM25 and vector indices are updated atomically or with a clear ordering (vector first, then BM25 rebuild from same corpus).

**Warning signs:**
- Agent references closed issues as open
- Agent gives code answers that don't match current `main` branch
- Retrieval metadata shows `last_indexed_at` timestamps days old for active repos

**Phase to address:** RAG pipeline + indexing phase; operational tooling phase

---

### Pitfall 11: pgvector HNSW Index Created Before Data Load

**What goes wrong:**
The Docker setup creates the HNSW or IVFFlat index on an empty or partially-loaded table. Index creation on the final data volume then requires a `REINDEX`, which blocks reads in non-concurrent mode and OOMs Docker containers with default memory settings if `maintenance_work_mem` is not tuned.

**Why it happens:**
Init scripts run index creation as part of schema setup, before data is loaded. HNSW index builds on large datasets require significantly more memory than default PostgreSQL settings provide inside Docker.

**How to avoid:**
Run `CREATE INDEX` only after the initial data load, never in schema init. In `docker-compose.yml`, set `shm_size: '256mb'` and environment `POSTGRES_INITDB_ARGS: "--data-checksums"`. Set `maintenance_work_mem=256MB` for index builds. For IVFFlat, set `lists = sqrt(num_rows)` (not the default 100). Run `EXPLAIN ANALYZE` on vector queries in dev to verify index is being used (catch seq scans). Use `CREATE INDEX CONCURRENTLY` for production-like data refreshes.

**Warning signs:**
- Docker container OOM during `CREATE INDEX`
- `EXPLAIN ANALYZE` output showing `Seq Scan` instead of `Index Scan` on vector queries
- Index build taking 10x longer than expected

**Phase to address:** Infrastructure / Docker setup phase

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Passing raw LangChain `chat_history` between agents | Fast to implement | Context bloat, error amplification, hard to debug | Never — use `AgentState` schema from day one |
| Default LangChain `max_iterations=15` | No config needed | Runaway loops, $50+ surprise API bills | Never — set explicitly and document |
| Fixed-size 512-token chunking for code | Works out of the box | Silently bad retrieval, hard to diagnose | Never for code; acceptable for prose-only MVP |
| Building eval with completion rate only | Quick metric | Misleading portfolio metric, no real signal | Never — define `task_success` from the start |
| Single monolithic pgvector index for all document types | Simpler schema | Chunking strategy conflicts, retrieval cross-contamination | Acceptable for very early prototype only |
| No spending limit on OpenAI account | Zero config | Budget exhaustion during a runaway agent | Never — set hard limit before any agent runs |
| Fetching GitHub data at query time (no caching) | No index infra needed | Rate limit exhaustion, 10s+ latency per query | Never for production-like demo |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| GitHub REST API | Using unauthenticated requests (60 req/hr limit) | Always authenticate; prefer GitHub App tokens (15K req/hr) over PATs |
| GitHub REST API | Not handling pagination (defaulting to first page only) | Always paginate with `per_page=100`, follow `Link` header `next` rel |
| GitHub REST API | Treating ETag caching as per-collection | ETags are per-page; do not assume page 1 cache hit means all pages unchanged |
| GitHub REST API | Secondary rate limit on async concurrent fetching | Cap concurrent requests at 80; back off on 403 with `X-RateLimit-Retry-After` |
| OpenAI API | Not using `strict=True` on structured outputs | Enforce JSON schema strictly for all tool call arguments |
| OpenAI API | Sending full retrieval chunks (10 × 500 tokens) to executor | Pre-filter to 3-5 highest-scored chunks; use reranker before executor |
| pgvector | Running vector queries without confirming index use | `EXPLAIN ANALYZE` every vector query in dev; catch seq scans before demo |
| LlamaIndex | Using default `SimpleNodeParser` for code files | Use `CodeSplitter` (tree-sitter) with language-aware boundaries |
| LangChain | `handle_parsing_errors=True` silently swallowing errors | Log every parsing error; add your own error-count ceiling per task |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| N+1 GitHub API requests (one per file/issue) | Index build takes hours, rate limit hit | Batch with `per_page=100`, cache raw responses to disk before embedding | Any repo > 200 issues |
| Embedding all chunks at query time | 3-10s latency per query | Pre-embed at index time, store in pgvector; only embed the query at runtime | Immediately on first query |
| Full context history passed to each agent | Token cost grows quadratically with plan length | `AgentState` with compact structured fields only | Plans with > 3 steps |
| IVFFlat with `lists=100` on small corpus | Poor recall, hybrid search worse than dense-only | Set `lists = sqrt(num_rows)` empirically | Corpus < 10K chunks with default lists=100 |
| No prompt caching on static system prompts | 2-3x higher cost on every agent invocation | Structure prompts so static prefix is first; OpenAI auto-caches prefixes > 1024 tokens | Any production-level usage |
| LLM-as-judge eval at temperature > 0 | Metric variance ±10pp between runs | `temperature=0` on all eval calls | Any eval run comparison |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing GitHub PAT in `.env` committed to repo | Token exposure, unauthorized repo access | Use `.env.example`, add `.env` to `.gitignore`, document token setup in README |
| Executor agent performing writes without re-confirming the exact diff | Accidental PR comments, issue creation on wrong repo | Surface exact API payload to CLI for user confirmation before HTTP POST/PATCH |
| Logging full GitHub API responses containing private issue bodies | Data leakage in logs | Redact issue body content in debug logs; only log IDs and titles |
| Accepting arbitrary repo URLs as input without validation | SSRF via GitHub API proxy pattern | Allowlist `github.com` domain; validate `owner/repo` format before any API call |
| No rate-limit-aware retry causing cascading GitHub ban | App-level IP ban from GitHub abuse detection | Respect `Retry-After` header; implement exponential backoff with jitter; never retry immediately on 429 |

---

## UX Pitfalls (CLI)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No streaming output — user sees nothing for 15-20s | Appears broken; demo feels slow | Stream planner CoT to terminal as it runs; show "Retrieving context..." progress |
| Confirmation prompt dumps raw JSON payload | User can't parse what they're confirming | Pretty-print the planned GitHub action: repo, action type, affected resource, body preview |
| Error messages from GitHub API surfaced as raw stack traces | Looks unprofessional in demo | Catch GitHub API exceptions; map to human-readable messages ("PR #42 not found in owner/repo") |
| No `--dry-run` flag for write operations | Can't demo without risking actual GitHub mutations | Implement `--dry-run` that shows the plan and confirmed action without executing the HTTP write |

---

## "Looks Done But Isn't" Checklist

- [ ] **Hybrid RAG:** Index reports success but hit Rate@5 never measured — verify with 20 held-out query/chunk pairs before wiring to agents
- [ ] **Multi-agent orchestration:** Agents produce output on happy path but loop limit and circuit breaker not tested — verify with a query that deliberately fails tool calls
- [ ] **Eval harness:** 200 test cases defined but pass/fail criteria are "non-empty output" — verify each case has a specific expected entity (PR number, issue title, file path) in ground truth
- [ ] **GitHub writes:** Confirmation prompt shown but actual HTTP call not gated behind it — verify with `--dry-run` that no write fires without explicit confirmation
- [ ] **pgvector:** Schema created and data loaded but index never built — verify with `\d+ embeddings` in psql and `EXPLAIN ANALYZE` on a vector query
- [ ] **Cost guardrails:** Code runs correctly in dev but no spending limit set — verify OpenAI account hard limit is set before any multi-step agent demo
- [ ] **Stale index:** Index built once but no `refresh` command — verify a document update in GitHub is reflected in retrieval within a documented SLA
- [ ] **BM25 + dense fusion:** Hybrid retrieval returns results but RRF k value never tuned — verify Hit Rate@5 with hybrid >= dense-only on your query set

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Error amplification across agent hops | HIGH | Introduce `AgentState` schema; requires touching planner, retriever, executor interfaces |
| Agent infinite loop / budget exhaustion | MEDIUM | Add `max_iterations` + circuit breaker; no architectural change required |
| Naive code chunking | HIGH | Re-chunk and re-embed entire corpus; requires `CodeSplitter` integration and full re-index |
| BM25/dense fusion not tuned | LOW | Adjust k parameter and weights; re-run eval set; no data migration |
| GitHub rate limit exhaustion | MEDIUM | Add caching layer + backoff; requires new infrastructure but no agent logic change |
| Tool call hallucination | MEDIUM | Add strict JSON schema enforcement + tool registry; touches executor agent prompt and tool layer |
| Eval non-determinism | MEDIUM | Pin `temperature=0` on eval calls; rewrite pass/fail criteria; rebuild ground truth for weak test cases |
| pgvector OOM on index build | LOW | Tune `maintenance_work_mem`, `shm_size`; rebuild index with `CREATE INDEX CONCURRENTLY` |
| Stale RAG index | MEDIUM | Implement `refresh` CLI command; add `last_indexed_at` metadata to all documents |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Error amplification across agent hops | Multi-agent orchestration build | Run a deliberately corrupted planner output through the pipeline; verify executor surfaces error rather than acting on it |
| Agent infinite loops | Multi-agent orchestration build | Submit a query that causes a tool call to fail repeatedly; verify loop exits within `max_iterations` |
| Context window bloat | Multi-agent orchestration + RAG integration | Measure input token count on a 5-step plan; must be < 6K tokens at executor |
| Naive code chunking | RAG pipeline / indexing phase | Manual inspection of 10 chunks from a Python file; all must be syntactically complete |
| BM25/dense fusion not tuned | RAG pipeline / indexing phase | Hit Rate@5 on held-out query set must be >= 0.75 before agent integration |
| GitHub rate limit exhaustion | GitHub integration phase | Simulate indexing a 500-issue repo; must complete without 429 errors |
| Tool call hallucination | Executor agent + tool definition phase | Submit 10 adversarial queries designed to elicit non-existent tool calls; all must be caught by tool registry |
| Eval non-determinism | Eval harness build phase | Run same 10 test cases 3 times; metric variance must be < 2pp |
| Gameable task completion metric | Eval harness build phase | Verify `task_success` rate is lower than `task_completion` rate on intentionally hard cases |
| Stale RAG index | Operational tooling phase | Update one issue in GitHub; run `refresh`; verify updated content appears in retrieval |
| pgvector HNSW index timing | Infrastructure / Docker setup phase | Run `EXPLAIN ANALYZE` on a vector query after initial load; must show Index Scan |
| No cost guardrails | First agent integration phase | Confirm OpenAI account hard limit set; verify `max_iterations` config present in agent init |

---

## Sources

- "Why Multi-Agent LLM Systems Fail" — orq.ai, augmentcode.com, redis.io, galileo.ai
- "Why Your Multi-Agent System is Failing: Escaping the 17x Error Trap" — Towards Data Science
- "Why Do Multi-Agent LLM Systems Fail?" — arxiv.org/html/2503.13657v1
- "Production Pitfalls of LangChain Nobody Warns You About" — Medium/CodeToDeploy
- "LangChain Tooling Hell: Why Your Agent Keeps Hallucinating APIs" — Medium
- "Your Chunks Failed Your RAG in Production" — Towards Data Science
- "Optimizing RAG with Hybrid Search & Reranking" — superlinked.com/vectorhub
- "Building a Production RAG Pipeline: Dense + BM25 + RRF" — Medium
- "Rate limits for the REST API" — docs.github.com (official)
- "Rate limits for GitHub Apps" — docs.github.com (official)
- "Stop Blaming the LLM: JSON Schema Is the Cheapest Fix for Flaky AI Agents" — Medium
- "Tool Call Validation: JSON Schema Validation for Tool Outputs" — understandingdata.com
- "Avoiding Common Pitfalls in LLM Evaluation" — honeyhive.ai
- "Latency optimization / Cost optimization / Prompt caching" — developers.openai.com (official)
- "Docker + pgvector Production Integration Guide" — markaicode.com
- pgvector GitHub README — github.com/pgvector/pgvector

---
*Pitfalls research for: multi-agent developer productivity platform (Python, LangChain, LlamaIndex, FastAPI, pgvector, OpenAI, GitHub, Docker)*
*Researched: 2026-05-14*
