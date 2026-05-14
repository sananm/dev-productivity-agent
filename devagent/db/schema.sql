-- Developer Productivity Agent — core schema.
-- The vector table (data_vector_nodes) is created/managed by LlamaIndex PGVectorStore.
-- LangGraph checkpoint tables are created by PostgresSaver.setup().
-- The HNSW index on the embedding column is created AFTER initial data load
-- (see devagent.db.migrate.create_vector_index) to avoid Docker OOM on an empty table.

CREATE EXTENSION IF NOT EXISTS vector;

-- Golden + generated evaluation cases. Seeded in Phase 1 so cases shape the build.
CREATE TABLE IF NOT EXISTS eval_cases (
    id              TEXT PRIMARY KEY,
    repo            TEXT NOT NULL,
    query           TEXT NOT NULL,
    category        TEXT NOT NULL,           -- code_qa | issue_triage | action | cross_source
    expected_tools  JSONB NOT NULL DEFAULT '[]',   -- ordered list of expected tool names
    expected_plan   JSONB NOT NULL DEFAULT '[]',   -- list of expected plan-step descriptions
    ground_truth    TEXT NOT NULL DEFAULT '',      -- reference answer
    source          TEXT NOT NULL DEFAULT 'golden',-- golden | generated
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per (eval_run, case, metric).
CREATE TABLE IF NOT EXISTS eval_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL,
    case_id         TEXT NOT NULL REFERENCES eval_cases(id),
    prompt_version  TEXT NOT NULL DEFAULT 'v1',
    metric          TEXT NOT NULL,           -- tool_correctness | task_completion | hallucination
    score           DOUBLE PRECISION NOT NULL,
    passed          BOOLEAN NOT NULL,
    detail          JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id);

-- Append-only audit log of every GitHub write action the executor attempts.
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    thread_id       TEXT,
    repo            TEXT NOT NULL,
    action          TEXT NOT NULL,           -- create_issue | comment_on_pr
    params          JSONB NOT NULL,
    status          TEXT NOT NULL,           -- proposed | confirmed | rejected | executed | dry_run | error
    result          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_thread ON audit_log(thread_id);
