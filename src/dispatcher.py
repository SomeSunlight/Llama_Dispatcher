"""Thin runtime adapter around the Dispatcher core.

The core intentionally remains focused on Dispatcher semantics. This launcher adds
machine-local binary/model roots as explicit process inputs and applies backend-
specific engine environment variables when Dispatcher launches llama.cpp.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

import dispatcher_core as core
from engine_environment import (
    EngineEnvironmentError,
    applied_process_environment,
    engine_name_from_config,
    load_engine_environment,
)
from runtime_paths import (
    RuntimePathError,
    expand_model_root,
    resolve_runtime_path_options,
    task_binary_name,
)


def install_runtime_overrides(bin_dir: str | None, model_root: str | None) -> None:
    """Install process-local runtime overrides before the core parser runs."""
    original_load_yaml = core.LlamaOrchestrator.load_yaml
    original_load_profile = core.LlamaOrchestrator.load_profile
    original_resolve_server_binary = core.LlamaOrchestrator._resolve_server_binary
    original_compile_task_profile = core.LlamaOrchestrator.compile_task_profile
    original_parse_cli_overrides = core.parse_cli_overrides
    original_canonicalize_params = core.canonicalize_params
    original_run_profile_server_loop = core.LlamaOrchestrator.run_profile_server_loop
    original_run_server_loop = core.LlamaOrchestrator.run_server_loop
    original_run_bench = core.LlamaOrchestrator.run_bench
    original_run_eval = core.LlamaOrchestrator.run_eval

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

    def canonicalize_params(params: dict[str, Any]) -> dict[str, Any]:
        # `environment` is Dispatcher engine policy, not a llama.cpp CLI option.
        filtered = {
            key: value
            for key, value in params.items()
            if core.canonical_key(key) not in {"environment", "env"}
        }
        return original_canonicalize_params(filtered)

    def environment_for_config(config_folder: Path, config_name: str) -> dict[str, str]:
        config_file = config_folder / f"{config_name}.yaml"
        if not config_file.exists():
            return {}
        raw_config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_config, dict):
            return {}
        engine_name = engine_name_from_config(raw_config)
        return load_engine_environment(
            engine_name,
            config_folder.parent / "engines",
            core.DEFAULTS_DIR / "engine-templates",
        )

    async def run_profile_server_loop(self, profile_name: str, overrides: dict):
        environment = environment_for_config(core.PROFILES_DIR, profile_name)
        with applied_process_environment(environment):
            return await original_run_profile_server_loop(self, profile_name, overrides)

    async def run_server_loop(self, ensemble_name: str, overrides: dict):
        environment = environment_for_config(core.ENSEMBLES_DIR, ensemble_name)
        with applied_process_environment(environment):
            return await original_run_server_loop(self, ensemble_name, overrides)

    async def run_bench(self, profile_name: str, overrides: dict):
        environment = environment_for_config(core.PROFILES_DIR, profile_name)
        with applied_process_environment(environment):
            return await original_run_bench(self, profile_name, overrides)

    async def run_eval(self, profile_name: str, dataset: str, overrides: dict):
        environment = environment_for_config(core.PROFILES_DIR, profile_name)
        with applied_process_environment(environment):
            return await original_run_eval(self, profile_name, dataset, overrides)

    core.LlamaOrchestrator.load_yaml = load_yaml
    core.LlamaOrchestrator.load_profile = load_profile
    core.LlamaOrchestrator._resolve_server_binary = resolve_server_binary
    core.LlamaOrchestrator.compile_task_profile = compile_task_profile
    core.LlamaOrchestrator.run_profile_server_loop = run_profile_server_loop
    core.LlamaOrchestrator.run_server_loop = run_server_loop
    core.LlamaOrchestrator.run_bench = run_bench
    core.LlamaOrchestrator.run_eval = run_eval
    core.parse_cli_overrides = parse_cli_overrides
    core.canonicalize_params = canonicalize_params


def main() -> None:
    try:
        runtime = resolve_runtime_path_options(sys.argv[1:])
        sys.argv = [sys.argv[0], *runtime.argv]
        install_runtime_overrides(runtime.bin_dir, runtime.model_root)
        core.main()
    except (RuntimePathError, EngineEnvironmentError) as exc:
        raise SystemExit(f"[ERROR] {exc}") from exc


if __name__ == "__main__":
    main()
