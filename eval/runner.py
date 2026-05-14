"""Eval runner — selects cases, runs the harness, prints + stores results.

`pytest eval/` and `devagent eval run` both call run(). The default is a small
deterministic stratified sample (fast, CI-friendly); --full runs all 200+ cases.
"""

from __future__ import annotations

import datetime as dt
import sys

from eval.cases import EvalCase, load_cases_from_db
from eval.harness import METRICS, run_eval

SAMPLE_PER_CATEGORY = 3


def select_cases(
    *, full: bool = False, limit: int | None = None, repo: str | None = None
) -> list[EvalCase]:
    """All cases (full) or a deterministic stratified sample across categories."""
    cases = sorted(load_cases_from_db(repo=repo), key=lambda c: c.id)
    if full:
        return cases[:limit] if limit else cases

    by_cat: dict[str, list[EvalCase]] = {}
    for c in cases:
        by_cat.setdefault(c.category, []).append(c)
    sample: list[EvalCase] = []
    for cat in sorted(by_cat):
        sample.extend(by_cat[cat][:SAMPLE_PER_CATEGORY])
    return sample[:limit] if limit else sample


def _new_run_id(prompt_version: str) -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{prompt_version}"


def run(
    *,
    full: bool = False,
    limit: int | None = None,
    prompt_version: str = "v1",
    store: bool = True,
    progress: bool = True,
) -> dict:
    cases = select_cases(full=full, limit=limit)
    run_id = _new_run_id(prompt_version)
    print(
        f"[eval] run_id={run_id}  cases={len(cases)}  "
        f"prompt={prompt_version}  mode={'full' if full else 'sample'}"
    )
    summary = run_eval(
        cases, run_id=run_id, prompt_version=prompt_version, store=store, progress=progress
    )
    _print_summary(summary)
    return summary


def compare(
    version_a: str,
    version_b: str,
    *,
    full: bool = False,
    limit: int | None = None,
) -> dict:
    """Run the same case set under two prompt versions and print a metric delta.

    This is the prompt-engineering feedback loop: change a prompt, re-run, and
    quantify the impact on task completion / tool accuracy / faithfulness.
    """
    cases = select_cases(full=full, limit=limit)
    print(f"[eval] comparing prompt '{version_a}' vs '{version_b}' on {len(cases)} cases\n")

    run_a = _new_run_id(version_a)
    run_b = _new_run_id(version_b)
    summary_a = run_eval(cases, run_id=run_a, prompt_version=version_a, store=True, progress=False)
    print(f"  {version_a} done ({summary_a['duration_s']}s)")
    summary_b = run_eval(cases, run_id=run_b, prompt_version=version_b, store=True, progress=False)
    print(f"  {version_b} done ({summary_b['duration_s']}s)")

    print("\n" + "=" * 72)
    print(f"  PROMPT COMPARISON — {version_a} vs {version_b}  ({len(cases)} cases)")
    print("-" * 72)
    print(f"  {'metric':<20}{version_a:>14}{version_b:>14}{'delta':>14}")
    for m in METRICS:
        a, b = summary_a["metrics"][m], summary_b["metrics"][m]
        delta = b - a
        arrow = "+" if delta > 0 else ""
        print(f"  {m:<20}{a:>14.3f}{b:>14.3f}{arrow + f'{delta:.3f}':>14}")
    print("=" * 72)
    return {"a": summary_a, "b": summary_b}


def _print_summary(summary: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  EVAL SUMMARY — {summary['run_id']}")
    print(f"  cases: {summary['n_cases']}   duration: {summary['duration_s']}s")
    print("-" * 60)
    print(f"  {'metric':<20} {'mean score':>12} {'pass rate':>12}")
    for m in METRICS:
        print(
            f"  {m:<20} {summary['metrics'][m]:>12.3f} "
            f"{summary['pass_rate'][m]:>11.1%}"
        )
    print("=" * 60)


def main() -> None:
    full = "--full" in sys.argv
    limit = None
    prompt_version = "v1"
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        if arg == "--prompt-version" and i + 1 < len(sys.argv):
            prompt_version = sys.argv[i + 1]
    run(full=full, limit=limit, prompt_version=prompt_version)


if __name__ == "__main__":
    main()
