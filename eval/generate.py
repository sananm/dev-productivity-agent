"""Generate 200+ evaluation cases from real repo fixtures.

The ~25 hand-written golden cases anchor dataset quality; this script expands
the set by templating queries over real entities — source files, top-level
symbols, issues/PRs, labels, and commits — so every generated case has a
checkable ground truth derived from the fixtures themselves.

Run directly:  python -m eval.generate            (default repo)
               python -m eval.generate psf/requests
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from devagent.config import FIXTURES_DIR, get_settings
from eval.cases import EvalCase, upsert_cases

_SYMBOL_RE = re.compile(r"^(?:class|def)\s+([A-Za-z_]\w+)", re.M)
# source files worth asking about — skip dunder, tests, conftest
_SKIP_FILE = re.compile(r"(__init__|__version__|conftest|test_)")


def _load_fixtures(repo: str) -> dict:
    d = FIXTURES_DIR / repo.replace("/", "__")
    return {
        "files": json.loads((d / "files.json").read_text()),
        "commits": json.loads((d / "commits.json").read_text()),
        "issues": json.loads((d / "issues.json").read_text())
        if (d / "issues.json").exists()
        else [],
    }


def _module_summary(path: str, content: str) -> str:
    """First line of the module docstring, found with plain string ops.

    A regex with re.S over large files risks catastrophic backtracking — avoid it.
    """
    # scan the first few non-blank lines for a docstring opener
    for line in content.splitlines()[:10]:
        stripped = line.lstrip("ru").strip()
        for quote in ('"""', "'''"):
            if stripped.startswith(quote):
                rest = stripped[len(quote):]
                end = rest.find(quote)
                text = rest[:end] if end != -1 else rest
                summary = " ".join(text.split())
                if summary:
                    return summary[:200]
    return f"the {Path(path).stem} module"


def _gen_code_cases(repo: str, files: dict) -> list[EvalCase]:
    cases: list[EvalCase] = []
    n = 0
    for path, info in files.items():
        if not path.endswith(".py") or _SKIP_FILE.search(path):
            continue
        content = info["content"]
        # file-purpose case
        n += 1
        cases.append(
            EvalCase(
                id=f"gen-codeqa-{n:03d}",
                repo=repo,
                query=f"What is the purpose of the file {path}?",
                category="code_qa",
                expected_tools=[],  # RAG retrieval handles code Q&A
                expected_plan=[f"retrieve context for {path}", "summarize its purpose"],
                ground_truth=f"{path} — {_module_summary(path, content)}",
                source="generated",
            )
        )
        # symbol-search cases (cap 2 per file to keep the set balanced)
        symbols = _SYMBOL_RE.findall(content)[:2]
        for sym in symbols:
            n += 1
            cases.append(
                EvalCase(
                    id=f"gen-search-{n:03d}",
                    repo=repo,
                    query=f"Where is `{sym}` defined in the codebase?",
                    category="code_qa",
                    expected_tools=[],  # RAG retrieval handles symbol lookup
                    expected_plan=[f"retrieve context for {sym}", "report the file"],
                    ground_truth=f"`{sym}` is defined in {path}.",
                    source="generated",
                )
            )
    return cases


def _gen_issue_cases(repo: str, issues: list[dict]) -> list[EvalCase]:
    cases: list[EvalCase] = []
    labels: set[str] = set()
    for i, issue in enumerate(issues, 1):
        labels.update(issue.get("labels", []))
        kind = "PR" if issue.get("pull_request") else "issue"
        body_first = " ".join((issue.get("body") or "").split())[:160]
        cases.append(
            EvalCase(
                id=f"gen-triage-{i:03d}",
                repo=repo,
                query=f"What is {kind} #{issue['number']} about?",
                category="issue_triage",
                expected_tools=[],  # issues are indexed; retrieval handles triage
                expected_plan=[f"retrieve context for {kind} #{issue['number']}", "summarize it"],
                ground_truth=f"#{issue['number']} \"{issue['title']}\": {body_first}",
                source="generated",
            )
        )
    for j, label in enumerate(sorted(labels), 1):
        cases.append(
            EvalCase(
                id=f"gen-label-{j:03d}",
                repo=repo,
                query=f"Are there any open issues labeled '{label}'?",
                category="issue_triage",
                expected_tools=[],
                expected_plan=[f"retrieve open issues for label {label}"],
                ground_truth=f"The answer should list open issues carrying the '{label}' label, or state none exist.",
                source="generated",
            )
        )
    return cases


def _gen_cross_source_cases(repo: str, files: dict, commits: list[dict]) -> list[EvalCase]:
    cases: list[EvalCase] = []
    # file-history cases
    touched: dict[str, int] = {}
    for c in commits:
        for f in c.get("files", []):
            touched[f] = touched.get(f, 0) + 1
    n = 0
    for path in sorted(touched):
        if path not in files or not path.endswith((".py", ".md", ".rst")):
            continue
        n += 1
        cases.append(
            EvalCase(
                id=f"gen-cross-{n:03d}",
                repo=repo,
                query=f"What recent commits have touched {path}?",
                category="cross_source",
                expected_tools=[],  # commit history is indexed
                expected_plan=[f"retrieve commit history for {path}", "summarize the changes"],
                ground_truth=f"{path} was modified in {touched[path]} of the recent commits.",
                source="generated",
            )
        )
    # individual-commit cases
    for k, commit in enumerate(commits[:35], 1):
        subject = commit["message"].splitlines()[0]
        cases.append(
            EvalCase(
                id=f"gen-commit-{k:03d}",
                repo=repo,
                query=f"What did commit {commit['sha'][:10]} change?",
                category="cross_source",
                expected_tools=[],
                expected_plan=[f"retrieve context for commit {commit['sha'][:10]}", "describe the change"],
                ground_truth=f"Commit {commit['sha'][:10]}: {subject}",
                source="generated",
            )
        )
    return cases


def _gen_action_cases(repo: str) -> list[EvalCase]:
    topics = [
        "improving the test coverage of the connection adapter",
        "adding type hints to the public API",
        "clarifying the retry/backoff documentation",
        "a flaky test in the redirect handling suite",
        "deprecating an undocumented internal helper",
        "improving error messages for invalid URLs",
        "documenting the streaming upload pattern",
    ]
    cases = [
        EvalCase(
            id=f"gen-action-{i:03d}",
            repo=repo,
            query=f"Open an issue about {topic}.",
            category="action",
            expected_tools=["create_issue"],
            expected_plan=["draft the issue", "request confirmation", "create the issue"],
            ground_truth=f"The agent drafts a clear issue about {topic} and creates it only after explicit confirmation.",
            source="generated",
        )
        for i, topic in enumerate(topics, 1)
    ]
    comment_targets = [6803, 6800, 6797, 6790, 6772, 6755]
    for j, number in enumerate(comment_targets, 1):
        cases.append(
            EvalCase(
                id=f"gen-action-c{j:03d}",
                repo=repo,
                query=f"Leave a constructive review comment on PR #{number}.",
                category="action",
                expected_tools=["comment_on_pr"],
                expected_plan=[f"draft a comment for PR #{number}", "request confirmation", "post it"],
                ground_truth=f"The agent drafts a constructive comment for PR #{number} and posts it only after confirmation.",
                source="generated",
            )
        )
    return cases


def generate(repo: str) -> list[EvalCase]:
    fx = _load_fixtures(repo)
    cases = [
        *_gen_code_cases(repo, fx["files"]),
        *_gen_issue_cases(repo, fx["issues"]),
        *_gen_cross_source_cases(repo, fx["files"], fx["commits"]),
        *_gen_action_cases(repo),
    ]
    return cases


def main() -> None:
    repo = sys.argv[1] if len(sys.argv) > 1 else get_settings().default_repo
    cases = generate(repo)
    n = upsert_cases(cases)
    by_cat: dict[str, int] = {}
    for c in cases:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    print(f"[eval] generated {n} cases for {repo}: {by_cat}")


if __name__ == "__main__":
    main()
