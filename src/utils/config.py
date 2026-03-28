"""Load YAML config from `config/`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.utils.paths import project_root


def load_settings() -> dict[str, Any]:
    path = project_root() / "config" / "settings.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_instruments() -> dict[str, Any]:
    path = project_root() / "config" / "instruments.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
