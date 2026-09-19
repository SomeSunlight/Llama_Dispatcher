from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence

MODEL_ROOT_TOKEN = "${LLAMA_MODEL_ROOT}"
_WINDOWS_ROOT = re.compile(r"^[A-Za-z]:[\\/]")


class RuntimePathError(ValueError):
    """Invalid or incomplete machine-local runtime path configuration."""


@dataclass(frozen=True)
class RuntimePathOptions:
    argv: list[str]
    bin_dir: str | None
    model_root: str | None
    model_root_source: str | None


def _extract_single_option(argv: Sequence[str], option: str) -> tuple[list[str], str | None]:
    cleaned: list[str] = []
    value: str | None = None
    seen = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == option:
            if seen:
                raise RuntimePathError(f"{option} may be specified only once")
            if i + 1 >= len(argv):
                raise RuntimePathError(f"{option} requires a path")
            value = argv[i + 1]
            if not value:
                raise RuntimePathError(f"{option} requires a non-empty path")
            seen = True
            i += 2
            continue
        prefix = option + "="
        if arg.startswith(prefix):
            if seen:
                raise RuntimePathError(f"{option} may be specified only once")
            value = arg[len(prefix):]
            if not value:
                raise RuntimePathError(f"{option} requires a non-empty path")
            seen = True
            i += 1
            continue
        cleaned.append(arg)
        i += 1
    return cleaned, value


def resolve_runtime_path_options(
    argv: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> RuntimePathOptions:
    """Remove Dispatcher runtime-path options before delegating to the legacy parser."""
    env = os.environ if environ is None else environ
    cleaned, bin_dir = _extract_single_option(argv, "--bin-dir")
    cleaned, cli_model_root = _extract_single_option(cleaned, "--model-root")

    if cli_model_root is not None:
        model_root = cli_model_root
        source = "cli"
    else:
        model_root = env.get("LLAMA_MODEL_ROOT") or None
        source = "environment" if model_root else None

    return RuntimePathOptions(
        argv=cleaned,
        bin_dir=bin_dir,
        model_root=model_root,
        model_root_source=source,
    )


def _join_model_root(root: str, suffix: str) -> str:
    """Join a portable `/`-separated profile suffix to a Windows or POSIX root."""
    root = str(root).rstrip("/\\")
    suffix_parts = PurePosixPath(suffix.lstrip("/\\").replace("\\", "/")).parts
    if _WINDOWS_ROOT.match(root) or root.startswith("\\\\"):
        return str(PureWindowsPath(root, *suffix_parts))
    return str(PurePosixPath(root, *suffix_parts))


def expand_model_root(value: Any, model_root: str | None) -> Any:
    """Recursively resolve the one supported portable model-root placeholder."""
    if isinstance(value, dict):
        return {key: expand_model_root(item, model_root) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_model_root(item, model_root) for item in value]
    if isinstance(value, tuple):
        return tuple(expand_model_root(item, model_root) for item in value)
    if not isinstance(value, str) or MODEL_ROOT_TOKEN not in value:
        return value

    if not model_root:
        raise RuntimePathError(
            f"Configuration uses {MODEL_ROOT_TOKEN}, but no --model-root was supplied "
            "and LLAMA_MODEL_ROOT is not set."
        )

    if value == MODEL_ROOT_TOKEN:
        return str(model_root)
    if value.startswith(MODEL_ROOT_TOKEN + "/") or value.startswith(MODEL_ROOT_TOKEN + "\\"):
        return _join_model_root(str(model_root), value[len(MODEL_ROOT_TOKEN):])
    return value.replace(MODEL_ROOT_TOKEN, str(model_root))


def task_binary_name(mode: str, os_name: str | None = None) -> str:
    platform_name = os.name if os_name is None else os_name
    base = "llama-perplexity" if mode == "eval" else f"llama-{mode}"
    return base + (".exe" if platform_name == "nt" else "")
