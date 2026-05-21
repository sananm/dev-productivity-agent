"""devagent CLI — a pure HTTP client against the FastAPI service.

Data-plane commands (migrate, index, seed-eval, validate-rag) run locally.
`ask` speaks only HTTP: it submits a query, renders the plan, streams the
answer, and drives the write-confirmation handshake. No agent logic lives here.
"""

from __future__ import annotations

import typer

from devagent.cli.client import CliError, stream_confirm, stream_query
from devagent.cli.cli_config import resolve_config
from devagent.cli.render import (
    console,
    render_answer_header,
    render_confirmation,
    render_done,
    render_error,
    render_plan,
    render_status,
)
from devagent.config import get_settings

app = typer.Typer(
    name="devagent",
    help="Developer Productivity Agent — query and act on GitHub repos.",
    no_args_is_help=True,
)


# --- data-plane commands -------------------------------------------------


@app.command()
def migrate() -> None:
    """Apply the database schema and LangGraph checkpoint tables."""
    from devagent.db.migrate import main as run_migrate

    run_migrate()


@app.command()
def index(
    repo: str = typer.Argument(None, help="owner/name (defaults to DEFAULT_REPO)"),
    source: list[str] = typer.Option(
        None, "--source", help="restrict to: code, doc, issue, commit (repeatable)"
    ),
) -> None:
    """Ingest a GitHub repo into the pgvector index."""
    from devagent.ingestion.pipeline import ingest_repo

    repo = repo or get_settings().default_repo
    console.print(f"[bold]Indexing[/bold] {repo} ...")
    counts = ingest_repo(repo, source_types=source or None)
    for src, n in counts.items():
        console.print(f"  {src}: {n} chunks")
    console.print("[green]done[/green]")


@app.command()
def refresh(
    source: str = typer.Argument(..., help="source type to re-index: code, doc, issue, commit"),
    repo: str = typer.Option(None, "--repo", help="owner/name (defaults to DEFAULT_REPO)"),
) -> None:
    """Re-index a single source type on demand — no full teardown."""
    from devagent.ingestion.pipeline import ingest_repo
    from devagent.rag.corpus import reset_caches

    if source not in ("code", "doc", "issue", "commit"):
        console.print(f"[red]unknown source '{source}'[/red] — use: code, doc, issue, commit")
        raise typer.Exit(1)
    repo = repo or get_settings().default_repo
    console.print(f"[bold]Refreshing[/bold] {source} for {repo} ...")
    counts = ingest_repo(repo, source_types=[source])
    reset_caches()
    console.print(f"  {source}: {counts.get(source, 0)} chunks  [green]refreshed[/green]")


@app.command("validate-rag")
def validate_rag() -> None:
    """Run the Hit Rate@5 retrieval gate (must pass before agents use the retriever)."""
    from devagent.rag.validate import main as run_validate

    run_validate()


@app.command("seed-eval")
def seed_eval() -> None:
    """Seed the golden evaluation cases into the eval_cases table."""
    from eval.cases import main as run_seed

    run_seed()


# --- eval sub-app --------------------------------------------------------

eval_app = typer.Typer(help="Run the benchmarking + evaluation harness.")
app.add_typer(eval_app, name="eval")


@eval_app.command("run")
def eval_run(
    full: bool = typer.Option(False, "--full", help="run all 200+ cases (default: sample)"),
    limit: int = typer.Option(None, "--limit", help="cap the number of cases"),
    prompt_version: str = typer.Option("v1", "--prompt-version", help="agent prompt version"),
    compare: tuple[str, str] = typer.Option(
        (None, None), "--compare", help="compare two prompt versions, e.g. --compare v1 v2"
    ),
) -> None:
    """Run the eval harness — task completion, tool-call accuracy, hallucination.

    With --compare v1 v2, runs the same cases under both prompt versions and
    prints a metric delta table (the prompt-engineering feedback loop).
    """
    from eval.runner import compare as compare_versions
    from eval.runner import run as run_eval_cli

    if compare and compare[0] and compare[1]:
        compare_versions(compare[0], compare[1], full=full, limit=limit)
    else:
        run_eval_cli(full=full, limit=limit, prompt_version=prompt_version)


@eval_app.command("generate")
def eval_generate(repo: str = typer.Argument(None, help="repo to generate cases from")) -> None:
    """Expand the golden cases into 200+ generated cases from repo fixtures."""
    from devagent.config import get_settings
    from eval.cases import upsert_cases
    from eval.generate import generate

    repo = repo or get_settings().default_repo
    cases = generate(repo)
    n = upsert_cases(cases)
    by_cat: dict[str, int] = {}
    for c in cases:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    console.print(f"[green]generated {n} cases[/green] for {repo}: {by_cat}")


# --- query command (pure HTTP client) -----------------------------------


@app.command()
def health(
    api_url: str = typer.Option(None, "--api-url", help="override the API base URL"),
) -> None:
    """Check the devagent API and its active backends."""
    from devagent.cli.client import health as api_health

    cfg = resolve_config(api_base_url=api_url)
    try:
        info = api_health(cfg.api_base_url)
    except CliError as exc:
        render_error(str(exc))
        raise typer.Exit(1)
    console.print(f"[green]API ok[/green] @ {cfg.api_base_url}")
    for key in ("llm", "embedding", "github_mode", "default_repo"):
        console.print(f"  {key}: {info.get(key)}")


@app.command()
def ask(
    query: str = typer.Argument(..., help="natural-language query about the repo"),
    repo: str = typer.Option(None, "--repo", help="owner/name to target"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="show write actions without executing them"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="show planner reasoning and tool I/O"
    ),
    prompt_version: str = typer.Option("v1", "--prompt-version", help="agent prompt version"),
    api_url: str = typer.Option(None, "--api-url", help="override the API base URL"),
) -> None:
    """Ask the agent a question — or instruct it to take an action — about a repo."""
    cfg = resolve_config(repo=repo, api_base_url=api_url)
    console.print(f"[dim]repo:[/dim] {cfg.repo}  [dim]·[/dim]  [dim]api:[/dim] {cfg.api_base_url}"
                  + ("  [dim]·[/dim]  [yellow]dry-run[/yellow]" if dry_run else ""))

    state = {"thread_id": None, "pending": None, "answer_started": False}

    def handle(event: str, data: dict) -> None:
        if event == "thread":
            state["thread_id"] = data["thread_id"]
        elif event == "plan":
            render_plan(data, verbose=verbose)
        elif event == "status":
            render_status(data, verbose=verbose)
        elif event == "token":
            if not state["answer_started"]:
                render_answer_header()
                state["answer_started"] = True
            print(data.get("text", ""), end="", flush=True)
        elif event == "needs_confirmation":
            state["pending"] = data["pending_write"]
            state["thread_id"] = data["thread_id"]
        elif event == "done":
            if state["answer_started"]:
                print()
            render_done(data)
        elif event == "error":
            render_error(data.get("message", "unknown error"))

    try:
        for event, data in stream_query(
            cfg.api_base_url,
            query=query,
            repo=cfg.repo,
            dry_run=dry_run,
            prompt_version=prompt_version,
        ):
            handle(event, data)
            if event == "needs_confirmation":
                break

        if state["pending"]:
            approved = render_confirmation(state["pending"])
            decision = "approved" if approved else "rejected"
            for event, data in stream_confirm(
                cfg.api_base_url, thread_id=state["thread_id"], decision=decision
            ):
                handle(event, data)
    except CliError as exc:
        render_error(str(exc))
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
