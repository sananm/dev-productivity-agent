"""Typed agent state.

Every node-to-node boundary in the graph passes this Pydantic model — never raw
message history. The state is the single source of truth: it is checkpointed by
PostgresSaver, so a query interrupted at the write-confirmation gate can be
resumed in a later request with full context intact.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StepAction = Literal["retrieve", "tool", "answer"]


class PlanStep(BaseModel):
    index: int = Field(description="0-based position of this step in the plan")
    action: StepAction = Field(description="retrieve | tool | answer")
    description: str = Field(description="what this step accomplishes")
    tool_name: str | None = Field(
        default=None, description="tool to call when action is 'tool'"
    )
    tool_args: dict = Field(
        default_factory=dict, description="concrete arguments for the tool"
    )


class Plan(BaseModel):
    """Structured-output schema the planner LLM emits."""

    reasoning: str = Field(description="chain-of-thought: query type, needed context, tools")
    steps: list[PlanStep] = Field(description="ordered plan steps; last step action='answer'")


class ToolCallTrace(BaseModel):
    """One executed tool call — also written to the JSONL trace file."""

    step_index: int
    tool_name: str
    input: dict
    output_summary: str
    ok: bool
    latency_ms: float
    citation: str | None = None


class PendingWrite(BaseModel):
    """A GitHub write action suspended at the confirmation gate."""

    tool_name: str
    args: dict
    description: str


class AgentState(BaseModel):
    # --- inputs ---
    query: str
    repo: str
    thread_id: str
    dry_run: bool = False
    prompt_version: str = "v1"

    # --- planner ---
    plan: list[PlanStep] = Field(default_factory=list)
    planner_reasoning: str = ""

    # --- retriever ---
    retrieved: list[dict] = Field(default_factory=list)  # serialized RetrievedChunk

    # --- executor ---
    tool_calls: list[ToolCallTrace] = Field(default_factory=list)
    pending_write: PendingWrite | None = None
    write_decision: str | None = None  # "approved" | "rejected"
    write_result: dict | None = None

    # --- synthesizer ---
    answer: str = ""
    citations: list[str] = Field(default_factory=list)

    # --- control ---
    error: str | None = None
