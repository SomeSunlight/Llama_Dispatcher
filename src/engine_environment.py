from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

import yaml

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EngineEnvironmentError(ValueError):
    """Invalid engine-owned process environment configuration."""


def engine_name_from_config(config: Mapping[str, Any]) -> str | None:
    defaults = config.get("defaults") or {}
    if not isinstance(defaults, Mapping):
        return None
    value = defaults.get("engine")
    return str(value).strip() if value else None


def load_engine_environment(
    engine_name: str | None,
    instance_engines: Path,
    template_engines: Path,
) -> dict[str, str]:
    """Load the first matching engine's process environment.

    The search order mirrors Dispatcher engine resolution: instance engine first,
    then the public engine template fallback. Environment variables are engine
    policy and are never read from profiles or ensembles.
    """
    if not engine_name:
        return {}

    engine_file: Path | None = None
    for search_dir in (instance_engines, template_engines):
        candidate = search_dir / f"{engine_name}.yaml"
        if candidate.exists():
            engine_file = candidate
            break
    if engine_file is None:
        return {}

    data = yaml.safe_load(engine_file.read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise EngineEnvironmentError(f"Engine config must contain a YAML object: {engine_file}")

    raw_environment = data.get("environment") or {}
    if not isinstance(raw_environment, Mapping):
        raise EngineEnvironmentError(
            f"Engine 'environment' must be a mapping in {engine_file}"
        )

    environment: dict[str, str] = {}
    for raw_name, raw_value in raw_environment.items():
        name = str(raw_name)
        if not _ENV_NAME.fullmatch(name):
            raise EngineEnvironmentError(
                f"Invalid environment variable name {name!r} in {engine_file}"
            )
        if raw_value is None or isinstance(raw_value, (dict, list, tuple)):
            raise EngineEnvironmentError(
                f"Environment variable {name} must have a scalar value in {engine_file}"
            )
        if isinstance(raw_value, bool):
            value = "true" if raw_value else "false"
        else:
            value = str(raw_value)
        environment[name] = value
    return environment


@contextmanager
def applied_process_environment(overrides: Mapping[str, str]) -> Iterator[None]:
    """Apply engine variables only inside the Dispatcher process lifetime block.

    Child llama.cpp processes inherit the values. The caller's shell and WSL
    environment are never modified, and previous Dispatcher-process values are
    restored when the operation finishes.
    """
    missing = object()
    previous: dict[str, str | object] = {
        name: os.environ.get(name, missing) for name in overrides
    }
    os.environ.update(overrides)
    try:
        yield
    finally:
        for name, old_value in previous.items():
            if old_value is missing:
                os.environ.pop(name, None)
            else:
                os.environ[name] = str(old_value)
