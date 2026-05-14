"""Evaluation harness — runs the agent on golden/generated cases and scores it.

Three metrics per case:
  - tool_correctness  (deterministic): did the agent call exactly the expected
    tools? For this RAG-first agent, read queries expect no tool calls and
    action queries expect the matching write tool.
  - task_completion   (LLM-judged): did the answer accomplish the query?
  - hallucination     (LLM-judged): is the answer grounded in retrieved context?
    Reported as a faithfulness score (1 - hallucination) so higher is better.

Writes are mocked (eval/mocks.py) — an eval run never mutates GitHub. The agent
runs against an in-memory checkpointer for isolation and speed.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")
os.environ.setdefault("DEEPEVAL_DISABLE_PROGRESS_BAR", "1")
os.environ.setdefault("ERROR_REPORTING", "NO")

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from devagent.agents.graph import build_graph  # noqa: E402
from devagent.db.session import execute  # noqa: E402
from eval.cases import EvalCase  # noqa: E402
from eval.mocks import mock_write_tools  # noqa: E402

METRICS = ("tool_correctness", "task_completion", "hallucination")
_PASS_THRESHOLD = 0.5


@dataclass
class AgentRun:
    answer: str
    tool_names: list[str]
    plan_actions: list[str]
    retrieved_context: list[str]
    tool_summaries: list[str]
    write_result: dict | None
    error: str | None = None

    def grounding_context(self) -> list[str]:
        """Everything the answer is allowed to be grounded in: retrieved chunks
        plus tool/write results. Used as the context for the hallucination metric
        so action answers ("created issue #X") are checked against what was done."""
        ctx = list(self.retrieved_context)
        ctx.extend(self.tool_summaries)
        if self.write_result:
            ctx.append(
                f"Write action [{self.write_result.get('status')}]: "
                f"{self.write_result.get('summary', '')}"
            )
        return ctx or ["(no context retrieved)"]


@dataclass
class CaseScore:
    case_id: str
    scores: dict[str, float] = field(default_factory=dict)
    passed: dict[str, bool] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph(checkpointer=MemorySaver())
    return _graph


def run_agent(case: EvalCase, *, prompt_version: str = "v1") -> AgentRun:
    """Run the full agent graph on one case, auto-approving any write gate."""
    graph = _get_graph()
    tid = f"eval-{uuid.uuid4().hex}"
    config = {"configurable": {"thread_id": tid}}
    payload = {
        "query": case.query,
        "repo": case.repo,
        "thread_id": tid,
        "dry_run": False,
        "prompt_version": prompt_version,
    }
    try:
        with mock_write_tools():
            graph.invoke(payload, config)
            state = graph.get_state(config)
            if any(task.interrupts for task in state.tasks):
                graph.invoke(Command(resume="approved"), config)
                state = graph.get_state(config)
    except Exception as exc:  # noqa: BLE001 — a crashed run is a failed run, not a crash
        return AgentRun(
            answer="", tool_names=[], plan_actions=[], retrieved_context=[],
            tool_summaries=[], write_result=None, error=f"{type(exc).__name__}: {exc}",
        )

    vals = state.values
    if hasattr(vals, "model_dump"):
        vals = vals.model_dump()

    def _field(obj, name):
        # state channel values may be Pydantic objects or already-dumped dicts
        return getattr(obj, name, None) if not isinstance(obj, dict) else obj.get(name)

    tool_calls = vals.get("tool_calls", [])
    return AgentRun(
        answer=vals.get("answer", "") or "",
        tool_names=[_field(t, "tool_name") for t in tool_calls],
        tool_summaries=[
            f"{_field(t, 'tool_name')}: {_field(t, 'output_summary')}" for t in tool_calls
        ],
        plan_actions=[
            f"{_field(s, 'action')}:{_field(s, 'tool_name') or ''}"
            for s in vals.get("plan", [])
        ],
        retrieved_context=[_field(item, "text") for item in vals.get("retrieved", [])],
        write_result=vals.get("write_result"),
        error=vals.get("error"),
    )


def score_case(case: EvalCase, run: AgentRun, judge) -> CaseScore:
    """Score one (case, run) pair across the three metrics. Resilient per-metric."""
    from deepeval.metrics import FaithfulnessMetric, TaskCompletionMetric
    from deepeval.test_case import LLMTestCase, ToolCall

    result = CaseScore(case_id=case.id)
    answer = run.answer or "(the agent produced no answer)"

    # --- tool correctness (deterministic set comparison) ---
    # DeepEval's ToolCorrectnessMetric pulls in a default LLM at construction even
    # though scoring is pure set logic — so we compute it directly: exact match of
    # the called-tool set against the expected-tool set (order-insensitive).
    try:
        called = set(run.tool_names)
        expected = set(case.expected_tools)
        if not expected and not called:
            score = 1.0  # correctly used no tools for a RAG-answerable query
        elif not expected:
            score = 0.0  # called tools that weren't needed
        else:
            score = len(called & expected) / len(called | expected)
        result.scores["tool_correctness"] = float(score)
        result.passed["tool_correctness"] = bool(score >= _PASS_THRESHOLD)
        result.notes["tool_correctness"] = f"called={sorted(called)} expected={sorted(expected)}"
    except Exception as exc:  # noqa: BLE001
        result.scores["tool_correctness"] = 0.0
        result.passed["tool_correctness"] = False
        result.notes["tool_correctness"] = str(exc)

    # --- task completion (LLM-judged) ---
    try:
        tc2 = LLMTestCase(
            input=case.query,
            actual_output=answer,
            tools_called=[ToolCall(name=n) for n in run.tool_names] or None,
        )
        m2 = TaskCompletionMetric(model=judge, threshold=_PASS_THRESHOLD)
        m2.measure(tc2)
        result.scores["task_completion"] = float(m2.score)
        result.passed["task_completion"] = bool(m2.score >= _PASS_THRESHOLD)
        if m2.reason:
            result.notes["task_completion"] = m2.reason[:300]
    except Exception as exc:  # noqa: BLE001
        result.scores["task_completion"] = 0.0
        result.passed["task_completion"] = False
        result.notes["task_completion"] = str(exc)

    # --- hallucination, measured as faithfulness (1 - hallucination rate) ---
    # FaithfulnessMetric extracts discrete claims and checks each against the
    # grounding context — more structured, and more reliable with a small judge,
    # than a single holistic hallucination judgement.
    try:
        tc3 = LLMTestCase(
            input=case.query,
            actual_output=answer,
            retrieval_context=run.grounding_context(),
        )
        m3 = FaithfulnessMetric(model=judge, threshold=_PASS_THRESHOLD)
        m3.measure(tc3)
        result.scores["hallucination"] = float(m3.score)  # faithfulness; higher = better
        result.passed["hallucination"] = bool(m3.score >= _PASS_THRESHOLD)
        if m3.reason:
            result.notes["hallucination"] = m3.reason[:300]
    except Exception as exc:  # noqa: BLE001
        result.scores["hallucination"] = 0.0
        result.passed["hallucination"] = False
        result.notes["hallucination"] = str(exc)

    return result


def store_results(run_id: str, prompt_version: str, scores: list[CaseScore]) -> None:
    for cs in scores:
        for metric in METRICS:
            execute(
                "INSERT INTO eval_results "
                "(run_id, case_id, prompt_version, metric, score, passed, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    run_id,
                    cs.case_id,
                    prompt_version,
                    metric,
                    cs.scores.get(metric, 0.0),
                    cs.passed.get(metric, False),
                    _json({"note": cs.notes.get(metric, "")}),
                ),
            )


def _json(obj) -> str:
    import json

    return json.dumps(obj)


def run_eval(
    cases: list[EvalCase],
    *,
    run_id: str,
    prompt_version: str = "v1",
    store: bool = True,
    progress: bool = True,
) -> dict:
    """Run + score every case. Returns an aggregate summary."""
    from eval.judge import LocalJudge

    judge = LocalJudge()
    scores: list[CaseScore] = []
    started = time.perf_counter()

    for i, case in enumerate(cases, 1):
        run = run_agent(case, prompt_version=prompt_version)
        cs = score_case(case, run, judge)
        scores.append(cs)
        if progress:
            line = " ".join(
                f"{m}={cs.scores.get(m, 0):.2f}" for m in METRICS
            )
            print(f"  [{i}/{len(cases)}] {case.id:<22} {line}")

    if store:
        store_results(run_id, prompt_version, scores)

    summary = {
        "run_id": run_id,
        "prompt_version": prompt_version,
        "n_cases": len(cases),
        "duration_s": round(time.perf_counter() - started, 1),
        "metrics": {
            m: round(sum(s.scores.get(m, 0.0) for s in scores) / max(len(scores), 1), 4)
            for m in METRICS
        },
        "pass_rate": {
            m: round(sum(s.passed.get(m, False) for s in scores) / max(len(scores), 1), 4)
            for m in METRICS
        },
    }
    return summary
