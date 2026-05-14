"""Load and seed evaluation cases.

Golden cases live in eval/golden/*.yaml. They are seeded into the eval_cases
table in Phase 1 so test cases shape what gets built. Phase 5's generator
appends source='generated' rows to the same table.

Run directly:  python -m eval.cases   (seeds golden cases)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from devagent.db.session import execute, fetch_all

GOLDEN_DIR = Path(__file__).with_name("golden")


@dataclass
class EvalCase:
    id: str
    repo: str
    query: str
    category: str
    expected_tools: list[str] = field(default_factory=list)
    expected_plan: list[str] = field(default_factory=list)
    ground_truth: str = ""
    source: str = "golden"


def load_golden() -> list[EvalCase]:
    cases: list[EvalCase] = []
    for path in sorted(GOLDEN_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        if not isinstance(doc, dict) or "cases" not in doc:
            continue  # e.g. retrieval_pairs.yaml — not a case file
        repo = doc["repo"]
        for raw in doc["cases"]:
            cases.append(
                EvalCase(
                    id=raw["id"],
                    repo=repo,
                    query=raw["query"],
                    category=raw["category"],
                    expected_tools=raw.get("expected_tools", []),
                    expected_plan=raw.get("expected_plan", []),
                    ground_truth=raw.get("ground_truth", "").strip(),
                    source="golden",
                )
            )
    return cases


def upsert_cases(cases: list[EvalCase]) -> int:
    for case in cases:
        execute(
            """
            INSERT INTO eval_cases
                (id, repo, query, category, expected_tools, expected_plan, ground_truth, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                repo = EXCLUDED.repo,
                query = EXCLUDED.query,
                category = EXCLUDED.category,
                expected_tools = EXCLUDED.expected_tools,
                expected_plan = EXCLUDED.expected_plan,
                ground_truth = EXCLUDED.ground_truth,
                source = EXCLUDED.source
            """,
            (
                case.id,
                case.repo,
                case.query,
                case.category,
                json.dumps(case.expected_tools),
                json.dumps(case.expected_plan),
                case.ground_truth,
                case.source,
            ),
        )
    return len(cases)


def load_cases_from_db(*, source: str | None = None, repo: str | None = None) -> list[EvalCase]:
    sql = "SELECT * FROM eval_cases"
    clauses, params = [], []
    if source:
        clauses.append("source = %s")
        params.append(source)
    if repo:
        clauses.append("repo = %s")
        params.append(repo)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    rows = fetch_all(sql, tuple(params))
    return [
        EvalCase(
            id=r["id"],
            repo=r["repo"],
            query=r["query"],
            category=r["category"],
            expected_tools=r["expected_tools"],
            expected_plan=r["expected_plan"],
            ground_truth=r["ground_truth"],
            source=r["source"],
        )
        for r in rows
    ]


def main() -> None:
    cases = load_golden()
    n = upsert_cases(cases)
    print(f"[eval] seeded {n} golden cases into eval_cases")


if __name__ == "__main__":
    main()
