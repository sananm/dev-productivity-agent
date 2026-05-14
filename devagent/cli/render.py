"""Rich rendering for the CLI — plan panels, streaming output, confirmation UX."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

console = Console()

_STEP_STYLE = {"retrieve": "cyan", "tool": "yellow", "answer": "green"}


def render_plan(plan: dict, *, verbose: bool) -> None:
    steps = plan.get("steps", [])
    body = Text()
    for s in steps:
        action = s.get("action", "?")
        marker = Text(f" {s.get('index', '?')}. ", style="bold")
        label = Text(f"[{action}]", style=_STEP_STYLE.get(action, "white"))
        detail = s.get("description", "")
        if s.get("tool_name"):
            detail = f"{s['tool_name']} — {detail}"
        body.append_text(marker)
        body.append_text(label)
        body.append(f" {detail}\n")
    if verbose and plan.get("reasoning"):
        body.append("\n")
        body.append(Text(plan["reasoning"], style="dim italic"))
    console.print(Panel(body, title="[bold]Plan[/bold]", border_style="blue", expand=False))


def render_status(data: dict, *, verbose: bool) -> None:
    stage = data.get("stage", "")
    if stage == "retrieving":
        console.print(f"[dim]· retrieved {data.get('count', 0)} context chunks[/dim]")
    elif stage == "executing":
        calls = data.get("tool_calls", [])
        if calls:
            _render_tool_calls(calls, verbose=verbose)
        elif verbose:
            console.print("[dim]· no tool calls in this plan[/dim]")
    elif stage == "write":
        result = data.get("result") or {}
        console.print(f"[dim]· write {result.get('status', '?')}: {result.get('summary', '')}[/dim]")


def _render_tool_calls(calls: list[dict], *, verbose: bool) -> None:
    for c in calls:
        status = "[green]ok[/green]" if c.get("ok") else "[red]failed[/red]"
        console.print(f"[dim]· tool[/dim] [yellow]{c.get('tool_name')}[/yellow] {status}: {c.get('output_summary', '')}")
        if verbose:
            console.print(f"  [dim]input:[/dim] {c.get('input')}")
            console.print(f"  [dim]latency:[/dim] {c.get('latency_ms')} ms")


def render_confirmation(pending: dict) -> bool:
    """Show a human-readable write preview and require explicit y/N."""
    args = pending.get("args", {})
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Action", f"[yellow]{pending.get('tool_name')}[/yellow]")
    table.add_row("Repo", args.get("repo", "?"))
    if "title" in args:
        table.add_row("Title", args["title"])
    if "number" in args:
        table.add_row("Target", f"#{args['number']}")
    if args.get("labels"):
        table.add_row("Labels", ", ".join(args["labels"]))
    body = args.get("body", "")
    if body:
        preview = body if len(body) <= 600 else body[:600] + " ..."
        table.add_row("Body", preview)
    console.print(
        Panel(table, title="[bold red]Write action — confirmation required[/bold red]",
              border_style="red", expand=False)
    )
    return Confirm.ask("[bold]Proceed with this write action?[/bold]", default=False)


def render_answer_header() -> None:
    console.print()
    console.rule("[bold green]Answer[/bold green]", style="green")


def render_done(data: dict) -> None:
    console.print()
    citations = data.get("citations", [])
    if citations:
        console.print(
            Panel(
                Text("  ".join(citations), style="dim"),
                title="[bold]Sources[/bold]",
                border_style="green",
                expand=False,
            )
        )
    wr = data.get("write_result")
    if wr:
        style = {"executed": "green", "dry_run": "yellow", "rejected": "red", "error": "red"}.get(
            wr.get("status"), "white"
        )
        console.print(f"[{style}]write {wr.get('status')}:[/{style}] {wr.get('summary', '')}")
    if data.get("error"):
        console.print(f"[yellow]note:[/yellow] {data['error']}")


def render_error(message: str) -> None:
    console.print(Panel(Text(message, style="red"), title="[bold red]Error[/bold red]",
                        border_style="red", expand=False))
