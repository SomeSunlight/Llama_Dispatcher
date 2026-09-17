"""Thin runtime-path adapter around the Dispatcher core.

The core intentionally remains focused on Dispatcher semantics. This launcher adds
machine-local binary/model roots as explicit process inputs so one instance can be
shared across Windows and WSL without duplicating profiles.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import dispatcher_core as core
from runtime_paths import (
    RuntimePathError,
    expand_model_root,
    resolve_runtime_path_options,
    task_binary_name,
)


def install_runtime_path_overrides(bin_dir: str | None, model_root: str | None) -> None:
    """Install process-local overrides before the Dispatcher core parser runs."""
    original_load_yaml = core.LlamaOrchestrator.load_yaml
    original_load_profile = core.LlamaOrchestrator.load_profile
    original_resolve_server_binary = core.LlamaOrchestrator._resolve_server_binary
    original_compile_task_profile = core.LlamaOrchestrator.compile_task_profile
    original_parse_cli_overrides = core.parse_cli_overrides

    def load_yaml(self, folder: str | Path, name: str) -> dict:
        return expand_model_root(original_load_yaml(self, folder, name), model_root)

    def load_profile(self, profile_name: str) -> dict:
        profile = expand_model_root(original_load_profile(self, profile_name), model_root)
        if bin_dir:
            profile["bin_dir"] = bin_dir
        return profile

    def resolve_server_binary(self, engine: dict[str, Any]) -> str:
        effective_engine = dict(engine)
        if bin_dir:
            effective_engine["bin_dir"] = bin_dir
        return original_resolve_server_binary(self, effective_engine)

    def compile_task_profile(self, profile_name: str, mode: str, overrides: dict) -> tuple[str, dict, list]:
        binary, params, cli_args = original_compile_task_profile(
            self,
            profile_name,
            mode,
            expand_model_root(overrides, model_root),
        )
        if bin_dir or os.name != "nt":
            effective_bin_dir = Path(bin_dir) if bin_dir else Path(binary).parent
            binary = str(effective_bin_dir / task_binary_name(mode))
        return binary, params, cli_args

    def parse_cli_overrides(unknown_args: list) -> dict:
        return expand_model_root(original_parse_cli_overrides(unknown_args), model_root)

    core.LlamaOrchestrator.load_yaml = load_yaml
    core.LlamaOrchestrator.load_profile = load_profile
    core.LlamaOrchestrator._resolve_server_binary = resolve_server_binary
    core.LlamaOrchestrator.compile_task_profile = compile_task_profile
    core.parse_cli_overrides = parse_cli_overrides


def main() -> None:
    try:
        runtime = resolve_runtime_path_options(sys.argv[1:])
    except RuntimePathError as exc:
        raise SystemExit(f"[ERROR] {exc}") from exc

    sys.argv = [sys.argv[0], *runtime.argv]
    install_runtime_path_overrides(runtime.bin_dir, runtime.model_root)
    core.main()


if __name__ == "__main__":
    main()
