"""CLI configuration resolution.

Precedence (highest first): command-line flag -> .devagent.yml in the current
directory -> environment defaults (devagent.config.Settings).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from devagent.config import get_settings

CONFIG_FILENAME = ".devagent.yml"


@dataclass
class CliConfig:
    repo: str
    api_base_url: str


def _load_file() -> dict:
    path = Path.cwd() / CONFIG_FILENAME
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return {}


def resolve_config(*, repo: str | None = None, api_base_url: str | None = None) -> CliConfig:
    settings = get_settings()
    file_cfg = _load_file()
    return CliConfig(
        repo=repo or file_cfg.get("repo") or settings.default_repo,
        api_base_url=api_base_url or file_cfg.get("api_base_url") or settings.api_base_url,
    )
