"""Pytest entrypoint for the eval harness.

  pytest eval/                      -> seeded-cases check + sample eval run
  RUN_SLOW=1 pytest eval/           -> also runs the 3x determinism gate

The sample run is deterministic and CI-friendly; the full 200+ case run is
`python -m eval.runner --full` (or `devagent eval run --full`).
"""

from __future__ import annotations

import os

import pytest

from devagent.db.session import fetch_one
from eval.harness import METRICS, run_agent, score_case
from eval.runner import select_cases

RUN_SLOW = os.getenv("RUN_SLOW") == "1"


def test_cases_seeded() -> None:
    """The eval dataset must contain 200+ cases (golden + generated)."""
    total = fetch_one("SELECT count(*) c FROM eval_cases")["c"]
    assert total >= 200, f"expected >=200 eval cases, found {total}"


def test_eval_sample_runs_and_scores() -> None:
    """A stratified sample runs end-to-end and every case gets all three metrics."""
    from eval.judge import LocalJudge

    cases = select_cases(full=False)
    assert len(cases) >= 4, "sample should cover multiple categories"

    judge = LocalJudge()
    scored = 0
    tool_correct = []
    for case in cases:
        run = run_agent(case)
        cs = score_case(case, run, judge)
        # every metric present and in [0, 1]
        for metric in METRICS:
            assert metric in cs.scores, f"{case.id} missing {metric}"
            assert 0.0 <= cs.scores[metric] <= 1.0, f"{case.id} {metric} out of range"
        tool_correct.append(cs.scores["tool_correctness"])
        scored += 1

    assert scored == len(cases)
    # tool_correctness is deterministic; for this RAG-first agent it should be high
    mean_tool = sum(tool_correct) / len(tool_correct)
    assert mean_tool >= 0.5, f"tool-correctness unexpectedly low: {mean_tool:.2f}"


@pytest.mark.skipif(not RUN_SLOW, reason="set RUN_SLOW=1 to run the determinism gate")
def test_determinism_gate() -> None:
    """Metric variance across 3 runs of the same 10 cases must stay bounded.

    tool_correctness is fully deterministic (no LLM judge) and must be stable to
    <2pp. The LLM-judged metrics carry inherent jitter even at temperature=0; we
    bound them loosely to catch gross instability.
    """
    from eval.judge import LocalJudge

    judge = LocalJudge()
    cases = select_cases(full=True)[:10]
    n_runs = 3

    per_run_means: list[dict[str, float]] = []
    for _ in range(n_runs):
        scores = [score_case(c, run_agent(c), judge) for c in cases]
        per_run_means.append(
            {m: sum(s.scores[m] for s in scores) / len(scores) for m in METRICS}
        )

    spread = {
        m: max(r[m] for r in per_run_means) - min(r[m] for r in per_run_means)
        for m in METRICS
    }
    print(f"\ndeterminism spread across {n_runs} runs: {spread}")
    assert spread["tool_correctness"] < 0.02, f"tool_correctness not deterministic: {spread}"
    assert spread["task_completion"] < 0.20, f"task_completion too jittery: {spread}"
    assert spread["hallucination"] < 0.20, f"hallucination too jittery: {spread}"
