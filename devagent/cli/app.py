"""devagent CLI.

Phase 1 ships the data-plane commands (migrate, index, seed-eval). Phase 4
adds `ask` and the HITL confirmation UX as a pure HTTP client against FastAPI.
"""

from __future__ import annotations

import typer
from rich.console import Console

from devagent.config import get_settings

app = typer.Typer(
    name="devagent",
    help="Developer Productivity Agent — query and act on GitHub repos.",
    no_args_is_help=True,
)
console = Console()


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


if __name__ == "__main__":
    app()
