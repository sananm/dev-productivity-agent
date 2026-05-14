"""Build offline GitHub fixtures from a local git clone.

Converts a cloned repo (.fixtures_src/) into normalized JSON fixtures that
FakeGitHubClient serves — code files and commit history, no API token needed.
Issues/PRs are hand-authored in fixtures/<repo>/issues.json (committed
separately, kept consistent with the golden eval cases).

Usage:  python scripts/build_fixtures.py psf/requests .fixtures_src
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = PROJECT_ROOT / "fixtures"

INCLUDE_DIRS = ("src/", "docs/", "tests/", "ext/")
INCLUDE_TOP_LEVEL = {".md", ".rst", ".txt", ".toml", ".cfg", ".ini"}
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".c", ".h", ".sh",
    ".md", ".rst", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml",
}
MAX_FILE_BYTES = 200_000
MAX_COMMITS = 250


def _git(src: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(src), *args], text=True)


def build_files(src: Path) -> dict[str, dict]:
    files: dict[str, dict] = {}
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        keep = rel.startswith(INCLUDE_DIRS) or (
            "/" not in rel and path.suffix in INCLUDE_TOP_LEVEL
        )
        if not keep or path.suffix not in TEXT_EXTENSIONS:
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        sha = _git(src, "hash-object", rel).strip()
        files[rel] = {"content": content, "sha": sha, "size": path.stat().st_size}
    return files


def build_commits(src: Path) -> list[dict]:
    # Two passes keep parsing robust: commit bodies are multi-line, so mixing
    # metadata and --name-only output in one stream is fragile.
    # Pass 1: metadata. %x1f = field sep, %x1e = record sep.
    meta_raw = _git(
        src, "log", f"-n{MAX_COMMITS}", "--pretty=format:%H%x1f%an%x1f%aI%x1f%s%x1f%b%x1e"
    )
    meta: dict[str, dict] = {}
    order: list[str] = []
    for record in meta_raw.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, author, date, subject, body = record.split("\x1f")
        message = subject if not body.strip() else f"{subject}\n\n{body.strip()}"
        meta[sha] = {"sha": sha, "author_name": author, "date": date, "message": message}
        order.append(sha)

    # Pass 2: files touched per commit.
    files_raw = _git(src, "log", f"-n{MAX_COMMITS}", "--pretty=format:%x1e%H", "--name-only")
    for block in files_raw.split("\x1e"):
        block = block.strip("\n")
        if not block:
            continue
        lines = block.splitlines()
        sha = lines[0]
        if sha in meta:
            meta[sha]["files"] = [ln for ln in lines[1:] if ln.strip()]

    return [{**meta[sha], "files": meta[sha].get("files", [])} for sha in order]


def main() -> None:
    repo = sys.argv[1] if len(sys.argv) > 1 else "psf/requests"
    src = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJECT_ROOT / ".fixtures_src"
    if not src.exists():
        sys.exit(f"clone not found at {src} — run: git clone --depth 250 https://github.com/{repo} {src}")

    out_dir = FIXTURES_DIR / repo.replace("/", "__")
    out_dir.mkdir(parents=True, exist_ok=True)

    default_branch = _git(src, "rev-parse", "--abbrev-ref", "HEAD").strip()
    files = build_files(src)
    commits = build_commits(src)

    (out_dir / "meta.json").write_text(
        json.dumps({"repo": repo, "default_branch": default_branch}, indent=2)
    )
    (out_dir / "files.json").write_text(json.dumps(files, indent=1))
    (out_dir / "commits.json").write_text(json.dumps(commits, indent=1))

    print(f"[fixtures] {repo}: {len(files)} files, {len(commits)} commits -> {out_dir}")
    if not (out_dir / "issues.json").exists():
        print(f"[fixtures] note: {out_dir/'issues.json'} not present — hand-author it")


if __name__ == "__main__":
    main()
