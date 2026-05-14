"""Versioned prompt loader.

Prompts live in devagent/prompts/<version>/<name>.txt with {placeholder} fields.
Versioning is what makes prompt engineering measurable: the eval harness can run
v1 vs v2 and diff the metric deltas (Phase 6).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPTS_ROOT = Path(__file__).resolve().parent
DEFAULT_VERSION = "v1"


@lru_cache(maxsize=64)
def _read(version: str, name: str) -> str:
    path = PROMPTS_ROOT / version / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"No prompt {name!r} in version {version!r} ({path})")
    return path.read_text()


def load_prompt(name: str, *, version: str = DEFAULT_VERSION, **fields: object) -> str:
    """Load a prompt template and fill its {placeholder} fields."""
    template = _read(version, name)
    try:
        return template.format(**fields)
    except KeyError as exc:
        raise KeyError(f"Prompt {name!r}/{version} missing field: {exc}") from exc


def available_versions() -> list[str]:
    return sorted(p.name for p in PROMPTS_ROOT.iterdir() if p.is_dir() and p.name != "__pycache__")
