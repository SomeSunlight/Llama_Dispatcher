import argparse
import asyncio
import hashlib
import json
import os
import re
import shlex
import signal
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import uvicorn
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from database_manager import MetricsDatabase

app = FastAPI(title="Llama Dispatcher Control API")

# Project paths: works both as src/dispatcher.py and directly in the project root.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "src" else Path.cwd()
SRC_DIR = PROJECT_ROOT / "src"

# Paths are defaults for legacy mode (without --instance).
# In main() they are redirected to the instance folder when --instance is specified.
DATA_DIR: Path = PROJECT_ROOT / "data"
PROFILES_DIR: Path = PROJECT_ROOT / "profiles"
ENSEMBLES_DIR: Path = PROJECT_ROOT / "ensembles"
# Model vendor defaults: always in the main repo, never instance-specific.
DEFAULTS_DIR: Path = PROJECT_ROOT / "defaults"


# ── Instance configuration ─────────────────────────────────────────────────────
def _resolve_instance(instance_name: str) -> tuple[str, Path]:
    """
    Reads instance.yaml from instances/<name>/ and returns (machine_guid, instance_dir).
    Creates directory and instance.yaml if not already present (first run).
    """
    instance_dir = PROJECT_ROOT / "instances" / instance_name
    config_file = instance_dir / "instance.yaml"

    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        machine_guid = data.get("machine_guid") or str(uuid.uuid4())
        nickname = data.get("nickname", instance_name)
        print(f"[INSTANCE] {nickname}  GUID={machine_guid}")
        return machine_guid, instance_dir

    # First run: create new instance
    machine_guid = str(uuid.uuid4())
    instance_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "profiles", "ensembles", "engines"):
        (instance_dir / sub).mkdir(exist_ok=True)
    config = {"nickname": instance_name, "machine_guid": machine_guid}
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"[INSTANCE] New instance '{instance_name}' created: {instance_dir}")
    print(f"[INSTANCE] GUID={machine_guid}  (saved in {config_file})")
    return machine_guid, instance_dir


class ServeRequest(BaseModel):
    ensemble: str | None = Field(None, description="Name of the ensemble YAML")
    profile: str | None = Field(None, description="Name of the profile YAML for classic single-model serve")
    overrides: dict = Field(default_factory=dict, description="Transient parameters for the engine")


# Stored/written canonically without leading dashes internally.
PARAM_MAPPING = {
    "c": "ctx-size",
    "ctx": "ctx-size",
    "context": "ctx-size",
    "b": "batch-size",
    "ub": "ubatch-size",
    "t": "threads",
    "ngl": "n-gpu-layers",
    "fa": "flash-attn",
    "ctk": "cache-type-k",
    "ctv": "cache-type-v",
    "ot": "override-tensor",
    "override_tensor": "override-tensor",
    "override-tensors": "override-tensor",
    "m": "model",
    "hf_repo": "hf-repo",
    "hf_file": "hf-file",
    "model_url": "model-url",
    "model_draft": "model-draft",
    "chat_template": "chat-template",
    "load_on_startup": "load-on-startup",
    "stop_timeout": "stop-timeout",
    "models_max": "models-max",
    "models_dir": "models-dir",
    "models_preset": "models-preset",
    "models_autoload": "models-autoload",
    "api_key": "api-key",
    # Sampling defaults / request defaults
    "temp": "temperature",
    "top_k": "top-k",
    "top_p": "top-p",
    "min_p": "min-p",
    "repeat_penalty": "repeat-penalty",
    "repeat_last_n": "repeat-last-n",
    "presence_penalty": "presence-penalty",
    "frequency_penalty": "frequency-penalty",
    "typical_p": "typical-p",
    "typ_p": "typical-p",
    "dynatemp_range": "dynatemp-range",
    "dynatemp_exp": "dynatemp-exp",
    "dynatemp_exponent": "dynatemp-exp",
    "mirostat_lr": "mirostat-lr",
    "mirostat_ent": "mirostat-ent",
    "dry_multiplier": "dry-multiplier",
    "dry_base": "dry-base",
    "dry_allowed_length": "dry-allowed-length",
    "dry_penalty_last_n": "dry-penalty-last-n",
    "dry_sequence_breaker": "dry-sequence-breaker",
    "sampler_seq": "sampler-seq",
    "sampling_seq": "sampling-seq",
}

# Convenience groups for YAML only. These keys do not exist in llama.cpp itself;
# their contents are merged flat into the model parameters before canonicalization.
MODEL_PARAM_GROUP_KEYS = {"sampling", "sampler", "generation", "defaults"}

# Parameters that the router itself receives, not the individual model instances.
ROUTER_PARAM_KEYS = {
    "host",
    "port",
    "models-max",
    "models-dir",
    "models-autoload",
    "no-models-autoload",
    "api-key",
    "timeout",
    "threads-http",
    "metrics",
    "props",
    "slots",
    "no-slots",
    "ui",
    "no-ui",
    "webui",
    "no-webui",
    "log-format",
    "verbose",
}

# Structural/dispatcher keys that never belong in llama.cpp presets.
DISPATCHER_ONLY_KEYS = {
    "bin-dir",
    "bin_dir",
    "binary",
    "server-bin",
    "server_bin",
    "preset-path",
    "preset_path",
    "models-preset",
    "models_preset",
    "extends",         # Default profile reference
    "default_profile", # Alternative spelling
}

# Parameters that are only forwarded via the proxy (not written to the llama.cpp INI).
PROXY_ONLY_KEYS: frozenset[str] = frozenset({
    "chat-template-kwargs",  # Canonical form of chat_template_kwargs
})

# Request-time sampling parameters for the proxy.
# These are injected from the profile/ensemble into every client request.
# Canonical form (hyphens); when injecting into JSON → underscores.
REQUEST_SAMPLING_KEYS: frozenset[str] = frozenset({
    "temperature", "top-p", "top-k", "min-p",
    "repeat-penalty", "presence-penalty", "frequency-penalty", "typical-p",
    "dynatemp-range", "dynatemp-exp",
    "mirostat-lr", "mirostat-ent",
    "dry-multiplier", "dry-base", "dry-allowed-length", "dry-penalty-last-n",
    "sampler-seq", "repeat-last-n",
})

SINGLE_DASH_EXCEPTIONS = {"pg", "cb", "ctk", "ctv", "lv"}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merged override recursively into base. Nested dicts are merged."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def canonical_key(key: str) -> str:
    """Normalizes YAML-/CLI keys to llama.cpp argument names without leading dashes."""
    clean = str(key).strip().lstrip("-").replace("_", "-")
    return PARAM_MAPPING.get(clean, PARAM_MAPPING.get(clean.replace("-", "_"), clean))


def flatten_model_param_groups(params: dict[str, Any]) -> dict[str, Any]:
    """
    Allows readable YAML groups like:

        sampling:
          temperature: 0.7
          top_p: 0.9

    llama.cpp expects flat argument names in the INI, however. Therefore these
    groups are unpacked here before canonicalization. On collision the
    explicitly flat key in the same dict wins.
    """
    flat: dict[str, Any] = {}
    for key, value in (params or {}).items():
        if key in MODEL_PARAM_GROUP_KEYS and isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def canonicalize_params(params: dict[str, Any]) -> dict[str, Any]:
    return {canonical_key(k): v for k, v in params.items() if v is not None}


def ini_scalar(value: Any, key: str | None = None) -> str:
    """Writes values as llama.cpp-INI expects them: simple, without Python representation."""
    if isinstance(value, bool):
        # llama.cpp documents -fa/--flash-attn as on|off|auto; boolean flags like jinja
        # stay true|false. This avoids exactly the kind of silent syntax errors
        # that are annoying with brand-new CLI options.
        if key in {"flash-attn", "reasoning"}:
            return "on" if value else "off"
        return "true" if value else "false"
    return str(value)


def quote_cmd(parts: list[str]) -> str:
    """Human-readable, copy-pasteable CLI string for DB/logs."""
    if os.name == "nt":
        import subprocess

        return subprocess.list2cmdline([str(p) for p in parts])
    return shlex.join([str(p) for p in parts])


class LlamaOrchestrator:
    def __init__(self, machine_id: str = "unknown"):
        self.current_process: asyncio.subprocess.Process | None = None
        self.is_running: bool = False
        # Instance mode (--instance): DATA_DIR = instances/<name>/data/ → metrics.db
        # Legacy mode (no --instance): DATA_DIR = data/ → metrics_v4.db (backwards compatibility)
        db_filename = "metrics.db" if "instances" in DATA_DIR.parts else "metrics_v4.db"
        self.db = MetricsDatabase(DATA_DIR / db_filename, SRC_DIR / "init_db.sql", machine_id=machine_id)
        self.fail_count: int = 0
        self.server_task: asyncio.Task | None = None
        self.api_port: int = 8001  # set by main(), used in startup log
        self._current_telemetry: dict = {}
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        # Proxy state: set on server start, cleared on stop
        self._active_run_id: str | None = None
        self._proxy_target_port: int | None = None
        self._active_model_aliases: list[str] = []
        # Sampling parameters per alias for proxy injection: {"workhorse": {"temperature": 1.0, ...}}
        self._proxy_sampling_params: dict[str, dict[str, Any]] = {}
        # Proxy-only alias remapping: {"creative": "workhorse"} → client calls "creative",
        # proxy injects its sampling params and rewrites model→"workhorse".
        # No separate llama.cpp entry → one model in VRAM, any number of aliases.
        self._proxy_alias_targets: dict[str, str] = {}
        # Dispatcher profile backing each public alias. Used for transparent request logging.
        self._proxy_profiles: dict[str, str] = {}

    def load_yaml(self, folder: str | Path, name: str) -> dict:
        base = Path(folder)
        path = base / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Configuration '{path}' not found.")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration '{path}' must contain a YAML object.")
        return data

    def load_profile(self, profile_name: str) -> dict:
        """
        Loads a profile and merges it with model and engine defaults.

        Profiles reference defaults via:
            defaults:
              model:  "gemma"    → defaults/gemma.yaml               (sampling, hardware-agnostic)
              engine: "vulkan"   → instances/<name>/engines/vulkan.yaml  (bin_dir, machine-specific)

        Merge order (lowest → highest priority):
          1. Model defaults   (defaults/<model>.yaml)
          2. Engine defaults  (instances/<name>/engines/<engine>.yaml  or engine-templates/ as fallback)
          3. Profile itself

        Backwards compatibility: old 'extends: "gemma"' is treated like
        'defaults: { model: "gemma" }' (no engine default).
        """
        profile = self.load_yaml(PROFILES_DIR, profile_name)

        # New syntax: defaults.model / defaults.engine
        defaults_cfg: dict[str, Any] = profile.get("defaults") or {}
        # Old syntax (deprecated): extends / default_profile -> mapped to defaults.model
        if not defaults_cfg:
            legacy = profile.get("extends") or profile.get("default_profile")
            if legacy:
                defaults_cfg = {"model": str(legacy).strip()}

        model_name  = defaults_cfg.get("model")
        engine_name = defaults_cfg.get("engine")

        base: dict[str, Any] = {}

        # 1. Load model defaults (defaults/<model>.yaml)
        if model_name:
            model_file = DEFAULTS_DIR / f"{model_name}.yaml"
            if model_file.exists():
                with open(model_file, "r", encoding="utf-8") as f:
                    base = yaml.safe_load(f) or {}
            else:
                print(f"[WARN] Model default '{model_name}' not found: {model_file}")

        # 2. Load engine defaults
        #    Search order: instances/<name>/engines/ → defaults/engine-templates/ (fallback)
        if engine_name:
            instance_engines = PROFILES_DIR.parent / "engines"
            template_engines = DEFAULTS_DIR / "engine-templates"
            engine_file: Path | None = None
            for search_dir in [instance_engines, template_engines]:
                candidate = search_dir / f"{engine_name}.yaml"
                if candidate.exists():
                    engine_file = candidate
                    break
            if engine_file:
                with open(engine_file, "r", encoding="utf-8") as f:
                    engine_defaults = yaml.safe_load(f) or {}
                base = _deep_merge(base, engine_defaults)
            else:
                print(f"[WARN] Engine config '{engine_name}' not found "
                      f"(searched in: {instance_engines}, {template_engines})")

        # 3. Merge profile (highest priority)
        merged = _deep_merge(base, profile) if base else dict(profile)

        # Remove dispatcher-internal keys (they don't go into llama.cpp INI)
        for k in ("defaults", "extends", "default_profile"):
            merged.pop(k, None)
        return merged

    async def get_llama_version(self, binary: Path) -> str:
        """Return concise version text reported by the effective llama.cpp binary."""
        try:
            proc = await asyncio.create_subprocess_exec(
                str(binary), "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            text = (stdout + b"\n" + stderr).decode("utf-8", errors="ignore")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                return "unknown"
            first = lines[0]
            match = re.search(r"commit\s+([a-f0-9]+)", text, re.IGNORECASE)
            if match and match.group(1).lower() not in first.lower():
                return f"{first} [commit {match.group(1)}]"
            return first
        except Exception:
            return "unknown"

    def _resolve_server_binary(self, engine: dict[str, Any]) -> str:
        engine = canonicalize_params(engine)
        bin_dir = Path(engine.get("bin-dir", engine.get("bin_dir", "./")))
        server_bin = engine.get("server-bin") or engine.get("binary")
        if not server_bin:
            server_bin = "llama-server.exe" if os.name == "nt" else "llama-server"
        return str(bin_dir / str(server_bin))

    def _router_cli_args(self, engine: dict[str, Any], preset_path: Path) -> list[str]:
        engine = canonicalize_params(engine)
        cli_args: list[str] = []

        def add_arg(name: str, value: Any):
            if value is None:
                return
            if isinstance(value, bool):
                if name.startswith("no-"):
                    if value:
                        cli_args.append(f"--{name}")
                else:
                    cli_args.append(f"--{name}" if value else f"--no-{name}")
                return
            cli_args.extend([f"--{name}", str(value)])

        for key in ("host", "port", "models-max", "models-dir", "api-key", "timeout", "threads-http"):
            if key in engine:
                add_arg(key, engine[key])

        # Autoload should remain active by default: the router then loads models on demand.
        if "models-autoload" in engine:
            add_arg("models-autoload", engine["models-autoload"])
        elif "no-models-autoload" in engine and engine["no-models-autoload"]:
            cli_args.append("--no-models-autoload")

        for flag in ("metrics", "props", "slots", "no-slots", "ui", "no-ui", "webui", "no-webui", "verbose"):
            if flag in engine:
                add_arg(flag, engine[flag])

        if "log-format" in engine:
            add_arg("log-format", engine["log-format"])

        cli_args.extend(["--models-preset", str(preset_path)])
        return cli_args

    def _model_section_params(self, profile: dict[str, Any], model_entry: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}

        def merge_source(source: dict[str, Any] | None):
            # Flattens convenience groups per source. This allows common.sampling,
            # serve.sampling and ensemble-specific sampling overrides to be cleanly
            # stacked on top of each other without replacing each other as a full dict value.
            merged.update(flatten_model_param_groups(source or {}))

        merge_source(profile.get("common", {}) or {})
        merge_source(profile.get("serve", {}) or {})
        merge_source(model_entry.get("params", {}) or {})
        merge_source(model_entry.get("overrides", {}) or {})

        # Allows short inline overrides in the ensemble entry:
        # - profile: normal_workhorse
        #   alias: workhorse
        #   c: 8192
        #   sampling:
        #     temperature: 0.62
        inline_overrides = {
            key: value
            for key, value in model_entry.items()
            if key not in {"profile", "alias", "params", "overrides"}
        }
        merge_source(inline_overrides)

        canonical = canonicalize_params(merged)
        cleaned: dict[str, Any] = {}
        for key, value in canonical.items():
            if key in ROUTER_PARAM_KEYS or key in DISPATCHER_ONLY_KEYS or key in PROXY_ONLY_KEYS:
                continue
            cleaned[key] = value

        # In an ensemble, loading should only happen on demand by default.
        cleaned.setdefault("load-on-startup", False)
        return cleaned

    def _write_models_preset_ini(self, preset_path: Path, global_params: dict[str, Any], models: dict[str, dict[str, Any]]):
        lines: list[str] = [
            "; Generated by dispatcher.py - do not edit by hand while the dispatcher is running.",
            "version = 1",
            "",
        ]

        if global_params:
            lines.append("[*]")
            for key, value in global_params.items():
                if value is None or key in ROUTER_PARAM_KEYS or key in DISPATCHER_ONLY_KEYS:
                    continue
                values = value if isinstance(value, list) else [value]
                for item in values:
                    lines.append(f"{key} = {ini_scalar(item, key)}")
            lines.append("")

        for alias, params in models.items():
            lines.append(f"[{alias}]")
            for key, value in params.items():
                values = value if isinstance(value, list) else [value]
                for item in values:
                    lines.append(f"{key} = {ini_scalar(item, key)}")
            lines.append("")

        preset_path.parent.mkdir(parents=True, exist_ok=True)
        preset_path.write_text("\n".join(lines), encoding="utf-8")

    def compile_serve_ensemble(self, ensemble_name: str, overrides: dict) -> tuple[str, dict, list]:
        """Compiles ensemble + profiles into an official llama.cpp router preset INI."""
        ensemble = self.load_yaml(ENSEMBLES_DIR, ensemble_name)

        # defaults.engine at ensemble level: provides bin_dir from instances/<name>/engines/<engine>.yaml
        # (analogous to defaults.engine in profiles, but here for the server start itself).
        # Search order: instances/<name>/engines/ → defaults/engine-templates/ (fallback)
        ensemble_defaults: dict[str, Any] = ensemble.get("defaults") or {}
        engine_default_name: str | None = (
            ensemble_defaults.get("engine") if isinstance(ensemble_defaults, dict) else None
        )

        engine = dict(ensemble.get("engine", {}) or {})

        if engine_default_name:
            instance_engines = ENSEMBLES_DIR.parent / "engines"
            template_engines = DEFAULTS_DIR / "engine-templates"
            for search_dir in [instance_engines, template_engines]:
                candidate = search_dir / f"{engine_default_name}.yaml"
                if candidate.exists():
                    with open(candidate, "r", encoding="utf-8") as f:
                        engine_template = yaml.safe_load(f) or {}
                    # Template as base; explicit engine: entries in the ensemble override it.
                    engine = {**engine_template, **engine}
                    break
            else:
                print(f"[WARN] Ensemble engine '{engine_default_name}' not found "
                      f"(searched in: {instance_engines}, {template_engines})")

        engine.update(overrides or {})
        engine = canonicalize_params(engine)

        binary = self._resolve_server_binary(engine)

        preset_name = engine.get("preset-path") or engine.get("preset_path") or f"{ensemble_name}_models.ini"
        preset_path = Path(preset_name)
        if not preset_path.is_absolute():
            preset_path = DATA_DIR / preset_path

        # "defaults:" is now reserved for dispatcher configuration (defaults.engine).
        # Model defaults for the INI come exclusively from "model_defaults:".
        global_params = canonicalize_params(
            flatten_model_param_groups(ensemble.get("model_defaults", {}) or {})
        )
        models: dict[str, dict[str, Any]] = {}       # real llama.cpp entries
        alias_targets: dict[str, str] = {}            # proxy-only: alias → llama.cpp alias

        for mod in ensemble.get("models", []) or []:
            if not isinstance(mod, dict) or "profile" not in mod:
                raise ValueError("Every entry in 'models' must contain at least 'profile'.")
            profile_name = mod["profile"]
            profile = self.load_profile(profile_name)
            alias = str(mod.get("alias") or profile_name)
            target = str(mod["target"]) if "target" in mod else None

            if alias in models or alias in alias_targets:
                raise ValueError(f"Duplicate model alias in ensemble '{ensemble_name}': {alias}")

            params = self._model_section_params(profile, mod)

            if target:
                # Proxy-only: no separate INI entry, requests are redirected to target.
                # Sampling params for this alias are still stored (for proxy injection).
                alias_targets[alias] = target
            else:
                has_model_source = any(k in params for k in ("model", "hf-repo", "model-url"))
                alias_looks_like_cache_id = "/" in alias and ":" in alias
                if not has_model_source and not alias_looks_like_cache_id:
                    raise ValueError(
                        f"Model '{alias}' from profile '{profile_name}' has no source. "
                        "Expected 'm/model', 'hf-repo' or 'model-url' in the profile or ensemble entry."
                    )
                models[alias] = params

        # Validation: every target must be a real model in the ensemble
        for a, t in alias_targets.items():
            if t not in models:
                raise ValueError(
                    f"Alias '{a}' has target='{t}', but '{t}' is not a (real) model "
                    f"in ensemble '{ensemble_name}'."
                )

        if not models:
            raise ValueError(f"Ensemble '{ensemble_name}' contains no real models (without target:).")

        self._write_models_preset_ini(preset_path, global_params, models)
        cli_args = self._router_cli_args(engine, preset_path)

        preset_content = preset_path.read_text(encoding="utf-8")

        # Proxy sampling parameters for ALL aliases (real + proxy-only).
        # REQUEST_SAMPLING_KEYS → converted to underscores for the JSON body.
        proxy_sampling: dict[str, dict[str, Any]] = {}
        proxy_profiles: dict[str, str] = {}
        for m in ensemble.get("models", []) or []:
            a = str(m.get("alias") or m.get("profile"))
            proxy_profiles[a] = str(m["profile"])
            # For real aliases: params from models dict. For proxy-only: recalculate.
            p = models.get(a) or self._model_section_params(
                self.load_profile(m["profile"]), m
            )
            sp: dict[str, Any] = {
                k.replace("-", "_"): v
                for k, v in p.items()
                if k in REQUEST_SAMPLING_KEYS and v is not None
            }
            ctk = m.get("chat_template_kwargs") or m.get("chat-template-kwargs")
            if ctk and isinstance(ctk, dict):
                sp["chat_template_kwargs"] = ctk
            if sp:
                proxy_sampling[a] = sp

        compiled = {
            "engine": engine,
            "preset_path": str(preset_path),
            "preset_content": preset_content,
            "preset_sha256": hashlib.sha256(preset_content.encode("utf-8")).hexdigest(),
            "model_defaults": global_params,
            "models": models,
            "alias_targets": alias_targets,
            "proxy_sampling": proxy_sampling,
            "proxy_profiles": proxy_profiles,
        }
        return binary, compiled, cli_args

    def _params_to_cli_args(self, params: dict[str, Any], mode: str = "serve") -> list[str]:
        """Translates canonicalized parameters into llama.cpp CLI arguments.

        Used for classic single-profile serve and still for bench/eval.
        The router/ensemble mode deliberately generates an INI instead.
        """
        cli_args: list[str] = []
        for key, value in params.items():
            if value is None or key in DISPATCHER_ONLY_KEYS:
                continue
            cli_key = key
            if mode == "bench":
                if key == "pp":
                    cli_key = "p"
                elif key == "tg":
                    cli_key = "n"
                elif key == "cache-type-k":
                    cli_key = "ctk"
                elif key == "cache-type-v":
                    cli_key = "ctv"

            prefix = "-" if len(cli_key) == 1 or cli_key in SINGLE_DASH_EXCEPTIONS else "--"

            if isinstance(value, bool):
                # llama.cpp expects a value for some tri-state/bool arguments,
                # for classic flags the presence of the argument is sufficient.
                if cli_key in {"flash-attn"}:
                    cli_args.extend([f"{prefix}{cli_key}", "on" if value else "off"])
                elif cli_key.startswith("no-"):
                    if value:
                        cli_args.append(f"{prefix}{cli_key}")
                elif value:
                    cli_args.append(f"{prefix}{cli_key}")
                else:
                    cli_args.append(f"--no-{cli_key}")
            else:
                for item in (value if isinstance(value, list) else [value]):
                    if mode == "bench" and cli_key == "pg" and isinstance(item, list):
                        pp_part, tg_part = item
                        if str(pp_part) == "MAX_CONTEXT":
                            pp_part = int(params.get("ctx-size", 8192)) - int(tg_part)
                        item = f"{pp_part},{tg_part}"
                    cli_args.extend([f"{prefix}{cli_key}", str(item)])
        return cli_args

    def compile_serve_profile(self, profile_name: str, overrides: dict) -> tuple[str, dict, list]:
        """Classic single-model serve without router INI.

        This is intentionally not a synthetic ensemble: for tests and direct
        single configurations exactly one llama-server process should start with
        parameters from profile.common + profile.serve + CLI overrides.
        """
        profile = self.load_profile(profile_name)

        merged: dict[str, Any] = {}
        merged.update(flatten_model_param_groups(profile.get("common", {}) or {}))
        merged.update(flatten_model_param_groups(profile.get("serve", {}) or {}))
        merged.update(flatten_model_param_groups(overrides or {}))
        canonical_params = canonicalize_params({k: v for k, v in merged.items() if v is not None})

        bin_dir = Path(profile.get("bin_dir") or profile.get("bin-dir") or canonical_params.pop("bin-dir", "./"))
        server_bin = profile.get("server_bin") or profile.get("server-bin") or profile.get("binary")
        if not server_bin:
            server_bin = "llama-server.exe" if os.name == "nt" else "llama-server"
        binary = str(bin_dir / str(server_bin))

        cli_params = {
            key: value
            for key, value in canonical_params.items()
            if key not in {"bin-dir", "server-bin", "binary"}
        }
        cli_args = self._params_to_cli_args(cli_params, mode="serve")
        compiled = {
            "profile": profile_name,
            "engine": {"mode": "single-profile"},
            "models": {profile_name: cli_params},
            "single_profile": True,
        }
        return binary, compiled, cli_args

    def compile_task_profile(self, profile_name: str, mode: str, overrides: dict) -> tuple[str, dict, list]:
        """For bench and eval: continues to use the existing profile logic in isolation."""
        config = self.load_profile(profile_name)
        merged = config.get("common", {}).copy()
        merged.update(config.get(mode, {}))
        merged.update(overrides)

        canonical_params = canonicalize_params({k: v for k, v in merged.items() if v is not None})
        cli_args = []
        bench_ignore = {"ctx-size", "override-kv", "cpu-moe"}

        for key, value in canonical_params.items():
            if mode == "bench" and key in bench_ignore:
                continue
            cli_key = key
            if mode == "bench":
                if key == "pp":
                    cli_key = "p"
                elif key == "tg":
                    cli_key = "n"
                elif key == "cache-type-k":
                    cli_key = "ctk"
                elif key == "cache-type-v":
                    cli_key = "ctv"

            prefix = "-" if len(cli_key) == 1 or cli_key in SINGLE_DASH_EXCEPTIONS else "--"

            if isinstance(value, bool):
                if cli_key in {"flash-attn"}:
                    cli_args.extend([f"{prefix}{cli_key}", "1" if value else "0"])
                elif value:
                    cli_args.append(f"{prefix}{cli_key}")
            else:
                for item in (value if isinstance(value, list) else [value]):
                    if mode == "bench" and cli_key == "pg" and isinstance(item, list):
                        pp_part, tg_part = item
                        if str(pp_part) == "MAX_CONTEXT":
                            pp_part = int(canonical_params.get("ctx-size", 8192)) - int(tg_part)
                        item = f"{pp_part},{tg_part}"
                    cli_args.extend([f"{prefix}{cli_key}", str(item)])

        binary = str(Path(config.get("bin_dir", "./")) / f"llama-{mode}.exe")
        if mode == "eval":
            binary = binary.replace("llama-eval", "llama-perplexity")
        return binary, canonical_params, cli_args

    def _parse_child_args(self, argv: list[str]) -> dict[str, Any]:
        """Parses llama.cpp-logged child server arguments into canonical long forms."""
        params: dict[str, Any] = {}
        i = 0
        while i < len(argv):
            token = argv[i]
            if not token.startswith("-"):
                i += 1
                continue
            key = canonical_key(token)
            value: Any = True
            if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                value = argv[i + 1]
                i += 2
            else:
                i += 1
            # Parameters that appear multiple times, e.g. override-tensor, are preserved.
            if key in params:
                if not isinstance(params[key], list):
                    params[key] = [params[key]]
                params[key].append(value)
            else:
                params[key] = value
        return params

    def _finalize_pending_spawn(self, run_id: str, state: dict[str, Any]) -> None:
        pending = state.get("pending_spawn")
        if not pending:
            return
        alias = pending["alias"]
        port = pending["port"]
        argv = pending.get("argv", [])
        effective_args = self._parse_child_args(argv)
        effective_cli = quote_cmd(argv) if argv else None
        declared = state.get("declared_models", {}).get(alias, {})
        runtime_id = self.db.insert_serve_model_instance(
            run_id=run_id,
            model_alias=alias,
            child_port=port,
            declared_params=declared,
            effective_args=effective_args,
            effective_cli_command=effective_cli,
        )
        state["runtime_by_port"][str(port)] = runtime_id
        state["alias_by_port"][str(port)] = alias
        state["runtime_by_alias"][alias] = runtime_id
        self.db.insert_lifecycle(run_id, alias, "load", 0.0, runtime_instance_id=runtime_id)
        state["pending_spawn"] = None

    def _runtime_for_port(self, state: dict[str, Any], port: str | None) -> int | None:
        if not port:
            return state.get("main_runtime_id")
        return state.get("runtime_by_port", {}).get(str(port))

    def _alias_for_port(self, state: dict[str, Any], port: str | None, fallback: str = "router_model") -> str:
        if not port:
            return state.get("main_alias", fallback)
        return state.get("alias_by_port", {}).get(str(port), fallback)

    async def _read_server_json_stream(
        self,
        stream: asyncio.StreamReader,
        run_id: str,
        compiled_params: dict[str, Any] | None = None,
        main_runtime_id: int | None = None,
        main_alias: str | None = None,
    ):
        """Reads llama.cpp logs and captures runtime instances plus request timings.

        Important: client request parameters such as temperature/top_p are not reliably
        output in the normal llama.cpp log. The dispatcher therefore only records
        observable engine/runtime parameters and timings, no client telemetry.
        CancelledError and KeyboardInterrupt are cleanly propagated so the
        calling loop can release the transport before the event loop ends.
        """
        state: dict[str, Any] = {
            "declared_models": (compiled_params or {}).get("models", {}),
            "pending_spawn": None,
            "runtime_by_port": {},
            "runtime_by_alias": {},
            "alias_by_port": {},
            "task_runtime": {},
            "task_telemetry": {},
            "main_runtime_id": main_runtime_id,
            "main_alias": main_alias,
        }

        while True:
            try:
                line = await stream.readline()
            except (asyncio.CancelledError, KeyboardInterrupt):
                self._finalize_pending_spawn(run_id, state)
                raise
            if not line:
                self._finalize_pending_spawn(run_id, state)
                break

            raw_line = line.decode("utf-8", errors="ignore").strip()
            clean_line = self.ansi_escape.sub("", raw_line)
            print(raw_line)

            pid_match = re.match(r"^\[(\d+)\]\s+(.*)$", clean_line)
            child_port = pid_match.group(1) if pid_match else None
            body = pid_match.group(2) if pid_match else clean_line

            # Router: child server is started with alias and port.
            spawn_match = re.search(r"spawning server instance with name=([^\s]+) on port (\d+)", clean_line)
            if spawn_match:
                self._finalize_pending_spawn(run_id, state)
                alias, port = spawn_match.group(1), int(spawn_match.group(2))
                state["pending_spawn"] = {"alias": alias, "port": port, "argv": []}
                state["alias_by_port"][str(port)] = alias
                continue

            # Afterwards llama.cpp logs the concrete child CLI line by line.
            if state.get("pending_spawn") and "spawning server instance with args:" in clean_line:
                continue

            arg_match = re.search(r"srv\s+load:\s+(.*)$", clean_line)
            if state.get("pending_spawn") and arg_match:
                arg = arg_match.group(1).strip()
                if arg and not arg.startswith("spawning server instance"):
                    state["pending_spawn"]["argv"].append(arg)
                    continue

            if state.get("pending_spawn"):
                self._finalize_pending_spawn(run_id, state)

            proxy_match = re.search(r"proxying request to model\s+([^\s]+)\s+on port\s+(\d+)", clean_line)
            if proxy_match:
                alias, port = proxy_match.group(1), proxy_match.group(2)
                state["alias_by_port"][port] = alias
                continue

            info_match = re.search(r"cmd_child_to_router:info:(\{.*\})", clean_line)
            if info_match and child_port:
                try:
                    meta = json.loads(info_match.group(1))
                except json.JSONDecodeError:
                    meta = {}
                runtime_id = self._runtime_for_port(state, child_port)
                if runtime_id:
                    self.db.update_serve_model_instance_meta(runtime_id, meta)
                alias = meta.get("id") or self._alias_for_port(state, child_port)
                state["alias_by_port"][child_port] = alias
                continue

            # Optional JSON log mode: deliberately kept defensive.
            try:
                log_data = json.loads(clean_line)
                if not isinstance(log_data, dict):
                    continue
                msg = log_data.get("message", "").lower()
                alias = log_data.get("model_alias", log_data.get("model", "router_model"))
                runtime_id = state["runtime_by_alias"].get(alias)
                if "load" in msg and "model" in msg:
                    dur = log_data.get("duration_ms", log_data.get("t_ms", 0.0))
                    self.db.insert_lifecycle(run_id, alias, "load", dur, runtime_instance_id=runtime_id)
                elif "evict" in msg or "unload" in msg:
                    self.db.insert_lifecycle(run_id, alias, "evict", 0.0, runtime_instance_id=runtime_id)

                if "timings" in log_data:
                    t = log_data["timings"]
                    self.db.insert_serve_telemetry(
                        run_id=run_id,
                        runtime_instance_id=runtime_id,
                        model_alias=alias,
                        child_port=None,
                        slot_id=None,
                        task_id=None,
                        p_tokens=t.get("prompt_n", 0),
                        g_tokens=t.get("predicted_n", 0),
                        i_speed=t.get("prompt_tps", 0.0),
                        g_speed=t.get("predicted_tps", 0.0),
                        duration=(t.get("predicted_ms", 0.0) + t.get("prompt_ms", 0.0)) / 1000.0,
                    )
                continue
            except json.JSONDecodeError:
                pass

            launch_match = re.search(r"launch_slot_:\s+id\s+(\d+)\s+\|\s+task\s+(-?\d+)\s+\|\s+processing task", body)
            if launch_match:
                slot_id, task_id = int(launch_match.group(1)), int(launch_match.group(2))
                runtime_id = self._runtime_for_port(state, child_port)
                alias = self._alias_for_port(state, child_port)
                state["task_runtime"][(child_port, task_id)] = {
                    "runtime_id": runtime_id,
                    "model_alias": alias,
                    "child_port": int(child_port) if child_port else None,
                    "slot_id": slot_id,
                    "task_id": task_id,
                }
                continue

            prompt_match = re.search(
                r"id\s+(\d+)\s+\|\s+task\s+(-?\d+)\s+\|\s+prompt eval time\s*=\s*([0-9.]+)\s*ms\s*/\s*([0-9]+)\s*tokens.*,\s*([0-9.]+)\s*tokens per second",
                body,
            )
            if prompt_match:
                slot_id, task_id = int(prompt_match.group(1)), int(prompt_match.group(2))
                key = (child_port, task_id)
                state["task_telemetry"].setdefault(key, {})
                state["task_telemetry"][key].update(
                    {
                        "slot_id": slot_id,
                        "p_ms": float(prompt_match.group(3)),
                        "p_tokens": int(prompt_match.group(4)),
                        "p_tps": float(prompt_match.group(5)),
                    }
                )
                continue

            eval_match = re.search(
                r"id\s+(\d+)\s+\|\s+task\s+(-?\d+)\s+\|\s+eval time\s*=\s*([0-9.]+)\s*ms\s*/\s*([0-9]+)\s*(?:runs|tokens).*,\s*([0-9.]+)\s*tokens per second",
                body,
            )
            if eval_match:
                slot_id, task_id = int(eval_match.group(1)), int(eval_match.group(2))
                key = (child_port, task_id)
                ctx = state["task_runtime"].get(key, {})
                tel = state["task_telemetry"].get(key, {})
                p_ms = tel.get("p_ms", 0.0)
                g_ms = float(eval_match.group(3))
                runtime_id = ctx.get("runtime_id") or self._runtime_for_port(state, child_port)
                model_alias = ctx.get("model_alias") or self._alias_for_port(state, child_port)
                self.db.insert_serve_telemetry(
                    run_id=run_id,
                    runtime_instance_id=runtime_id,
                    model_alias=model_alias,
                    child_port=ctx.get("child_port") or (int(child_port) if child_port else None),
                    slot_id=ctx.get("slot_id") or slot_id,
                    task_id=task_id,
                    p_tokens=tel.get("p_tokens", 0),
                    g_tokens=int(eval_match.group(4)),
                    i_speed=tel.get("p_tps", 0.0),
                    g_speed=float(eval_match.group(5)),
                    duration=(p_ms + g_ms) / 1000.0,
                )
                state["task_telemetry"].pop(key, None)
                continue

            # Individual child logs like "loading model 'C:\...gguf'" do not describe a new
            # router instance; the instance was already captured in the spawning block.

            unload_match = re.search(r"(?:unload|evict).*model\s+([^\s]+)", clean_line, re.IGNORECASE)
            if unload_match:
                alias = unload_match.group(1).strip("\'\"")
                runtime_id = state["runtime_by_alias"].get(alias)
                self.db.insert_lifecycle(run_id, alias, "evict", 0.0, runtime_instance_id=runtime_id)
                if runtime_id:
                    self.db.close_serve_model_instance(runtime_id, status="evicted")
                continue

    async def run_profile_server_loop(self, profile_name: str, overrides: dict):
        self.is_running = True
        while self.is_running:
            try:
                binary, compiled_params, cli_args = self.compile_serve_profile(profile_name, overrides)
                effective_binary = str(Path(binary).expanduser().resolve())
                llama_ver = await self.get_llama_version(Path(effective_binary))

                cmd_str = quote_cmd([effective_binary] + cli_args)
                startup_params = self._parse_child_args(cli_args)
                run_id = str(uuid.uuid4())
                model_params = compiled_params["models"][profile_name]

                # Set proxy state
                self._active_run_id = run_id
                self._proxy_target_port = (
                    int(model_params["port"]) if str(model_params.get("port", "")).isdigit() else None
                )
                self._active_model_aliases = [profile_name]
                sp = {k.replace("-", "_"): v for k, v in model_params.items()
                      if k in REQUEST_SAMPLING_KEYS and v is not None}
                self._proxy_sampling_params = {profile_name: sp} if sp else {}
                self._proxy_alias_targets = {}
                self._proxy_profiles = {profile_name: profile_name}
                if sp:
                    print(f"[PROXY] {profile_name}: " + "  ".join(f"{k}={v}" for k, v in sp.items()))

                self.db.insert_run(
                    run_id,
                    "serve",
                    profile_name,
                    llama_ver,
                    effective_binary,
                    cmd_str,
                    startup_params,
                    preset_path=None,
                    preset_content=None,
                    preset_sha256=None,
                )
                runtime_id = self.db.insert_serve_model_instance(
                    run_id=run_id,
                    model_alias=profile_name,
                    child_port=int(model_params["port"]) if str(model_params.get("port", "")).isdigit() else None,
                    declared_params=model_params,
                    effective_args=model_params,
                    effective_cli_command=cmd_str,
                    status="loaded",
                )
                self.db.insert_lifecycle(run_id, profile_name, "load", 0.0, runtime_instance_id=runtime_id)

                print(f"\n[ORCHESTRATOR] Booting Profile: {profile_name} | Run ID: {run_id}")
                print(f"[ORCHESTRATOR] Command: {cmd_str}")

                start_time = asyncio.get_event_loop().time()
                self.current_process = await asyncio.create_subprocess_exec(
                    effective_binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                )

                try:
                    await self._read_server_json_stream(
                        self.current_process.stdout,
                        run_id,
                        compiled_params,
                        main_runtime_id=runtime_id,
                        main_alias=profile_name,
                    )
                except (asyncio.CancelledError, KeyboardInterrupt):
                    self.is_running = False
                    self.db.close_serve_model_instance(runtime_id, status="unloaded")
                    self._active_run_id = None; self._proxy_target_port = None
                    raise
                await self.current_process.wait()
                self.db.close_serve_model_instance(runtime_id, status="unloaded" if not self.is_running else "crashed")
                self._active_run_id = None; self._proxy_target_port = None

                if not self.is_running:
                    break

                uptime = asyncio.get_event_loop().time() - start_time
                if uptime < 45.0:
                    print(f"\n[FATAL] Server crashed immediately on startup ({uptime:.1f}s). Aborting.")
                    self.is_running = False
                    os._exit(1)
                else:
                    self.fail_count = 0
                    print("\n[ORCHESTRATOR] Server terminated unexpectedly. Restarting in 5s...")
                    await asyncio.sleep(5)
            except (asyncio.CancelledError, KeyboardInterrupt):
                self.is_running = False
                raise
            except Exception as e:
                print(f"[ORCHESTRATOR ERROR] {e}")
                await asyncio.sleep(5)

    async def run_server_loop(self, ensemble_name: str, overrides: dict):
        self.is_running = True
        while self.is_running:
            try:
                binary, compiled_params, cli_args = self.compile_serve_ensemble(ensemble_name, overrides)
                effective_binary = str(Path(binary).expanduser().resolve())
                llama_ver = await self.get_llama_version(Path(effective_binary))

                cmd_str = quote_cmd([effective_binary] + cli_args)
                startup_params = self._parse_child_args(cli_args)
                run_id = str(uuid.uuid4())

                # Set proxy state
                self._active_run_id = run_id
                self._proxy_target_port = int(compiled_params["engine"].get("port", 8080))
                # All visible aliases for /v1/models: real + proxy-only
                self._active_model_aliases = (
                    list(compiled_params["models"].keys()) +
                    list(compiled_params.get("alias_targets", {}).keys())
                )
                self._proxy_sampling_params = compiled_params.get("proxy_sampling", {})
                self._proxy_alias_targets = compiled_params.get("alias_targets", {})
                self._proxy_profiles = compiled_params.get("proxy_profiles", {})

                # Startup log: full proxy configuration at a glance
                print(f"\n[PROXY] Dispatcher port → llama.cpp port: "
                      f"Clients:{self.api_port}  llama.cpp:{self._proxy_target_port}")
                print(f"[PROXY] Configured aliases:")
                for alias in self._active_model_aliases:
                    target = self._proxy_alias_targets.get(alias)
                    sp = self._proxy_sampling_params.get(alias, {})
                    kind = f"proxy-only → {target}" if target else "real (in VRAM)"
                    params_str = "  ".join(f"{k}={v}" for k, v in sp.items()) if sp else "(no overrides)"
                    print(f"[PROXY]   {alias:20s}  [{kind}]  {params_str}")
                print(f"[PROXY] Debug:   GET  http://localhost:{self.api_port}/debug/config")
                print(f"[PROXY] Preview: POST http://localhost:{self.api_port}/debug/preview")

                self.db.insert_run(
                    run_id,
                    "serve",
                    ensemble_name,
                    llama_ver,
                    effective_binary,
                    cmd_str,
                    startup_params,
                    preset_path=compiled_params.get("preset_path"),
                    preset_content=compiled_params.get("preset_content"),
                    preset_sha256=compiled_params.get("preset_sha256"),
                )
                print(f"\n[ORCHESTRATOR] Booting Ensemble: {ensemble_name} | Run ID: {run_id}")
                print(f"[ORCHESTRATOR] Preset: {compiled_params['preset_path']}")
                print(f"[ORCHESTRATOR] Command: {cmd_str}")

                start_time = asyncio.get_event_loop().time()
                self.current_process = await asyncio.create_subprocess_exec(
                    effective_binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                )

                try:
                    await self._read_server_json_stream(self.current_process.stdout, run_id, compiled_params)
                except (asyncio.CancelledError, KeyboardInterrupt):
                    self.is_running = False
                    self._active_run_id = None; self._proxy_target_port = None
                    self._proxy_alias_targets = {}
                    raise
                await self.current_process.wait()
                self._active_run_id = None; self._proxy_target_port = None
                self._proxy_alias_targets = {}

                if not self.is_running:
                    break

                uptime = asyncio.get_event_loop().time() - start_time
                if uptime < 15.0:
                    print(f"\n[FATAL] Server crashed immediately on startup ({uptime:.1f}s). Aborting.")
                    self.is_running = False
                    os._exit(1)
                else:
                    self.fail_count = 0
                    print("\n[ORCHESTRATOR] Server terminated unexpectedly. Restarting in 5s...")
                    await asyncio.sleep(5)
            except (asyncio.CancelledError, KeyboardInterrupt):
                self.is_running = False
                raise
            except Exception as e:
                print(f"[ORCHESTRATOR ERROR] {e}")
                if self.current_process and self.current_process.returncode is None:
                    self.current_process.terminate()
                    try:
                        await asyncio.wait_for(self.current_process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        self.current_process.kill()
                        await self.current_process.wait()
                self.current_process = None
                self._active_run_id = None
                self._proxy_target_port = None
                self._proxy_alias_targets = {}
                await asyncio.sleep(5)

    async def run_bench(self, profile_name: str, overrides: dict):
        binary, params, cli_args = self.compile_task_profile(profile_name, "bench", overrides)
        effective_binary = str(Path(binary).expanduser().resolve())
        llama_ver = await self.get_llama_version(Path(effective_binary))
        cmd_str = quote_cmd([effective_binary] + cli_args)
        startup_params = self._parse_child_args(cli_args)
        run_id = str(uuid.uuid4())

        self.db.insert_run(
            run_id, "bench", profile_name, llama_ver, effective_binary, cmd_str, startup_params
        )
        print(f"\n[ORCHESTRATOR] Starting Benchmark | Profile: {profile_name} | Run ID: {run_id}")
        print(f"[ORCHESTRATOR] Command: {cmd_str}\n")

        self.current_process = await asyncio.create_subprocess_exec(
            effective_binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )

        base_ctx = int(params.get("ctx-size", 0))
        try:
            while True:
                line = await self.current_process.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="ignore").strip()
                print(line_str)

                if line_str.startswith("|") and not line_str.startswith("| model"):
                    parts = [p.strip() for p in line_str.split("|") if p.strip()]
                    if len(parts) >= 8 and "±" in parts[-1]:
                        test_type = parts[-2]
                        speed_raw = parts[-1].strip()
                        speed, speed_error = (
                            (float(p.strip()) for p in speed_raw.split("±"))
                            if "±" in speed_raw
                            else (float(speed_raw), 0.0)
                        )
                        self.db.insert_bench(run_id, test_type, base_ctx, speed, speed_error)
        except (asyncio.CancelledError, KeyboardInterrupt):
            print("\n[ORCHESTRATOR] Bench cancelled, terminating child process...")
            raise
        finally:
            await self.current_process.wait()
            self.current_process = None

    async def run_eval(self, profile_name: str, dataset: str, overrides: dict):
        overrides["f"] = dataset
        binary, params, cli_args = self.compile_task_profile(profile_name, "eval", overrides)
        effective_binary = str(Path(binary).expanduser().resolve())
        llama_ver = await self.get_llama_version(Path(effective_binary))
        cmd_str = quote_cmd([effective_binary] + cli_args)
        startup_params = self._parse_child_args(cli_args)
        run_id = str(uuid.uuid4())

        self.db.insert_run(
            run_id, "eval", profile_name, llama_ver, effective_binary, cmd_str, startup_params
        )
        print(f"\n[ORCHESTRATOR] Starting Evaluation | Profile: {profile_name} | Run ID: {run_id}")
        print(f"[ORCHESTRATOR] Dataset: {dataset}")
        print(f"[ORCHESTRATOR] Command: {cmd_str}\n")

        start_time = asyncio.get_event_loop().time()
        self.current_process = await asyncio.create_subprocess_exec(
            effective_binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )

        final_perplexity, perplexity_error = 0.0, 0.0
        try:
            while True:
                line = await self.current_process.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="ignore").strip()
                print(line_str)

                match = re.search(r"Final estimate:\s*(?:PPL\s*=\s*)?([0-9.]+)\s*\+/-\s*([0-9.]+)", line_str)
                if match:
                    final_perplexity, perplexity_error = float(match.group(1)), float(match.group(2))
                elif re.search(r"Final estimate:.*?([0-9.]+)", line_str):
                    final_perplexity = float(re.search(r"Final estimate:.*?([0-9.]+)", line_str).group(1))
        except (asyncio.CancelledError, KeyboardInterrupt):
            print("\n[ORCHESTRATOR] Eval cancelled, terminating child process...")
            raise
        finally:
            rc = await self.current_process.wait()
            self.current_process = None
            if rc == 0 and final_perplexity > 0:
                self.db.insert_eval(
                    run_id, dataset, final_perplexity, perplexity_error, asyncio.get_event_loop().time() - start_time
                )


def _run_task_safe(coro, orc: "LlamaOrchestrator") -> None:
    """Runs a bench/eval coroutine and ensures that on interruption
    (Ctrl+C / KeyboardInterrupt) the child process is cleanly terminated and awaited
    BEFORE the event loop is closed. This prevents the
    RuntimeError("Event loop is closed") in the BaseSubprocessTransport destructor.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(coro)
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        print("\n[ORCHESTRATOR] Interrupt received, terminating child process...")
        task.cancel()
        # Safely terminate child process if still running.
        if orc.current_process is not None:
            try:
                orc.current_process.terminate()
            except ProcessLookupError:
                pass
        # Wait until task and child process are truly finished.
        try:
            loop.run_until_complete(asyncio.wait_for(task, timeout=15.0))
        except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
            pass
        if orc.current_process is not None:
            try:
                loop.run_until_complete(asyncio.wait_for(orc.current_process.wait(), timeout=10.0))
            except (asyncio.TimeoutError, Exception):
                try:
                    orc.current_process.kill()
                except Exception:
                    pass
        print("[ORCHESTRATOR] Done.")
    finally:
        # Clean up all still-running tasks, then close the loop.
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()


orchestrator: LlamaOrchestrator | None = None


# ── Proxy helper functions ─────────────────────────────────────────────────────

def _extract_response_stats(obj: Any, stats: dict[str, Any]) -> None:
    """Extracts token counts and finish_reason from a llama.cpp response object."""
    if not isinstance(obj, dict):
        return
    usage = obj.get("usage")
    if usage and isinstance(usage, dict):
        if usage.get("prompt_tokens") is not None:
            stats["prompt_tokens"] = int(usage["prompt_tokens"])
        if usage.get("completion_tokens") is not None:
            stats["completion_tokens"] = int(usage["completion_tokens"])
    choices = obj.get("choices")
    if choices and isinstance(choices, list) and choices:
        fr = choices[0].get("finish_reason")
        if fr:
            stats["finish_reason"] = str(fr)


def _extract_thinking(req_data: dict) -> int | None:
    """Reads enable_thinking from chat_template_kwargs. Returns 1, 0 or None."""
    ctk = req_data.get("chat_template_kwargs")
    if isinstance(ctk, dict) and "enable_thinking" in ctk:
        return 1 if ctk["enable_thinking"] else 0
    return None


_REQUEST_CONTENT_KEYS = {"messages", "prompt", "input"}


def _request_params_snapshot(req_data: dict[str, Any]) -> dict[str, Any]:
    """Return request control parameters without prompt or conversation content."""
    return {k: v for k, v in req_data.items() if k not in _REQUEST_CONTENT_KEYS}


def _parameter_changes(
    client_params: dict[str, Any],
    effective_params: dict[str, Any],
    client_model: str | None,
    target_model: str | None,
    resolved_profile: str | None,
) -> dict[str, Any]:
    """Describe Dispatcher transformations without claiming unknown config-layer provenance."""
    changes: dict[str, Any] = {}
    keys = set(client_params) | set(effective_params)
    for key in sorted(keys):
        client_value = client_params.get(key)
        effective_value = effective_params.get(key)
        if client_value == effective_value:
            continue
        source = "alias_target" if key == "model" and client_model != target_model else "dispatcher_policy"
        item: dict[str, Any] = {
            "client": client_value,
            "effective": effective_value,
            "source": source,
        }
        if source == "dispatcher_policy":
            item["configured_for"] = client_model
            item["resolved_profile"] = resolved_profile
        changes[key] = item
    return changes


# ── Proxy endpoints (/v1/) ────────────────────────────────────────────────────

@app.get("/v1/models")
async def api_models():
    """
    Returns a clean model list – only the configured aliases,
    no internal llama.cpp paths. Replaces the native /v1/models response.
    """
    assert orchestrator is not None
    aliases = orchestrator._active_model_aliases or []
    return JSONResponse({
        "object": "list",
        "data": [
            {"id": alias, "object": "model", "created": int(time.time()), "owned_by": "llama-dispatcher"}
            for alias in aliases
        ],
    })


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "DELETE", "PUT", "OPTIONS"])
async def proxy_to_llama(path: str, request: Request):
    """
    Transparent proxy to llama.cpp. Logs client parameters and response statistics
    (token counts, latency, TTFT, finish_reason, sampling values) in the database.

    Clients simply point to http://<host>:<api-port>/v1/ instead of directly to llama.cpp.
    """
    assert orchestrator is not None

    if not orchestrator.is_running or orchestrator._proxy_target_port is None:
        return JSONResponse(
            {"error": {"message": "No model active – waiting for server start.", "type": "server_error"}},
            status_code=503,
        )

    body_bytes = await request.body()
    req_data: dict[str, Any] = {}
    if body_bytes:
        try:
            req_data = json.loads(body_bytes)
        except json.JSONDecodeError:
            pass

    # Preserve the untouched client-side control parameters before any mutation.
    client_params = _request_params_snapshot(req_data)
    client_model = req_data.get("model")
    is_stream = bool(req_data.get("stream", False))

    # ── Parameter injection from profile ──────────────────────────────────────
    # Profile parameters always take precedence over client values (for REQUEST_SAMPLING_KEYS
    # and chat_template_kwargs). Everything else (model, messages, stream, max_tokens,
    # tools, etc.) passes through unchanged from the client.
    model_alias = req_data.get("model", "")
    profile_params = orchestrator._proxy_sampling_params.get(model_alias, {})
    injected: dict[str, Any] = {}

    if profile_params:
        modified_data = req_data.copy()
        for k, v in profile_params.items():
            if req_data.get(k) != v:
                injected[k] = v
            modified_data[k] = v
        body_bytes = json.dumps(modified_data, ensure_ascii=False).encode("utf-8")
        req_data = modified_data

    # ── Alias remapping ───────────────────────────────────────────────────────
    # Proxy-only aliases exist only in the dispatcher; llama.cpp only knows the real alias.
    # "creative" → sampling params injected (above) + model field rewritten to "workhorse".
    llama_alias = orchestrator._proxy_alias_targets.get(model_alias, model_alias)
    if llama_alias != model_alias:
        remap_data = req_data.copy()
        remap_data["model"] = llama_alias
        body_bytes = json.dumps(remap_data, ensure_ascii=False).encode("utf-8")
        req_data = remap_data

    resolved_profile = orchestrator._proxy_profiles.get(model_alias)
    target_model = req_data.get("model")
    alias_remapped = 1 if target_model != client_model else 0
    effective_params = _request_params_snapshot(req_data)
    parameter_changes = _parameter_changes(
        client_params, effective_params, client_model, target_model, resolved_profile
    )
    injected_json: str | None = json.dumps(injected, ensure_ascii=False, sort_keys=True) if injected else None

    # Host and content-length are set anew by httpx
    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length", "transfer-encoding"}
    }
    target_url = f"http://127.0.0.1:{orchestrator._proxy_target_port}/v1/{path}"
    start = time.monotonic()

    stats: dict[str, Any] = {
        "ttft": None, "prompt_tokens": None, "completion_tokens": None,
        "finish_reason": None, "status_code": 200,
    }

    async def _stream_and_log():
        first_chunk = True
        non_stream_buf = bytearray()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(None)) as client:
                async with client.stream(
                    request.method, target_url,
                    content=body_bytes, headers=forward_headers,
                ) as resp:
                    stats["status_code"] = resp.status_code
                    async for chunk in resp.aiter_bytes():
                        if first_chunk:
                            stats["ttft"] = time.monotonic() - start
                            first_chunk = False
                        if is_stream:
                            # SSE-Zeilen nach usage/finish_reason durchsuchen
                            for line in chunk.decode("utf-8", errors="ignore").splitlines():
                                if line.startswith("data: "):
                                    payload = line[6:].strip()
                                    if payload == "[DONE]":
                                        continue
                                    try:
                                        _extract_response_stats(json.loads(payload), stats)
                                    except (json.JSONDecodeError, ValueError):
                                        pass
                        else:
                            non_stream_buf.extend(chunk)
                        yield chunk
        finally:
            # Non-streaming: parse complete response
            if non_stream_buf:
                try:
                    _extract_response_stats(
                        json.loads(non_stream_buf.decode("utf-8", errors="ignore")), stats
                    )
                except (json.JSONDecodeError, ValueError):
                    pass
            # Always log – even on client disconnect (finally always runs)
            try:
                orchestrator.db.insert_proxy_request(
                    run_id=orchestrator._active_run_id,
                    endpoint=path,
                    model_requested=target_model,
                    client_model=client_model,
                    resolved_profile=resolved_profile,
                    target_model=target_model,
                    alias_remapped=alias_remapped,
                    stream=1 if is_stream else 0,
                    req_temperature=req_data.get("temperature"),
                    req_top_p=req_data.get("top_p"),
                    req_top_k=req_data.get("top_k"),
                    req_min_p=req_data.get("min_p"),
                    req_max_tokens=req_data.get("max_tokens"),
                    req_enable_thinking=_extract_thinking(req_data),
                    effective_repeat_penalty=req_data.get("repeat_penalty"),
                    client_params=client_params,
                    effective_params=effective_params,
                    parameter_changes=parameter_changes,
                    prompt_tokens=stats.get("prompt_tokens"),
                    completion_tokens=stats.get("completion_tokens"),
                    finish_reason=stats.get("finish_reason"),
                    duration=time.monotonic() - start,
                    ttft=stats.get("ttft"),
                    status_code=stats.get("status_code", 200),
                    injected_params=injected_json,
                )
            except Exception as log_err:
                print(f"[PROXY] Logging error: {log_err}")

    media_type = "text/event-stream" if is_stream else "application/json"
    return StreamingResponse(_stream_and_log(), media_type=media_type)


# ── Debug endpoints ────────────────────────────────────────────────────────────

@app.get("/debug/config")
async def debug_config():
    """
    Shows the current proxy configuration:
    - Which aliases clients see
    - Which parameters are injected per alias
    - Which aliases are proxy-only (with target remapping)
    - On which port llama.cpp is listening
    """
    assert orchestrator is not None
    aliases_info = []
    for alias in orchestrator._active_model_aliases:
        target = orchestrator._proxy_alias_targets.get(alias)
        sp = orchestrator._proxy_sampling_params.get(alias, {})
        aliases_info.append({
            "alias": alias,
            "type": "proxy-only" if target else "real",
            "target": target,
            "injected_params": sp,
        })
    return JSONResponse({
        "status": "running" if orchestrator.is_running else "idle",
        "llama_port": orchestrator._proxy_target_port,
        "aliases": aliases_info,
    })


@app.post("/debug/preview")
async def debug_preview(request: Request):
    """
    Simulates the proxy transformation of a request WITHOUT forwarding it.

    Send the same JSON body that Open WebUI would send to /v1/chat/completions.
    The response shows what the proxy would do with it:
    - which parameters are injected
    - how the model field is rewritten
    - the complete body that would be sent to llama.cpp

    Example (curl):
      curl -s http://localhost:8001/debug/preview \\
        -H "Content-Type: application/json" \\
        -d '{"model":"agent","messages":[{"role":"user","content":"Hello"}],"temperature":0.9}'
    """
    assert orchestrator is not None
    body_bytes = await request.body()
    try:
        req_data: dict[str, Any] = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    model_alias = req_data.get("model", "")
    profile_params = orchestrator._proxy_sampling_params.get(model_alias, {})
    injected: dict[str, Any] = {}
    forwarded = req_data.copy()

    # Sampling-injection (identical to real proxy logic)
    if profile_params:
        for k, v in profile_params.items():
            if req_data.get(k) != v:
                injected[k] = {"from_profile": v, "client_sent": req_data.get(k)}
            forwarded[k] = v

    # Alias-remapping
    llama_alias = orchestrator._proxy_alias_targets.get(model_alias, model_alias)
    alias_rewritten = llama_alias != model_alias
    if alias_rewritten:
        forwarded["model"] = llama_alias

    return JSONResponse({
        "original_model": model_alias,
        "forwarded_model": llama_alias,
        "alias_rewritten": alias_rewritten,
        "injected_params": injected,
        "overridden_by_client": {
            k: req_data[k] for k in profile_params
            if k in req_data and req_data[k] != profile_params[k]
               and k not in ("chat_template_kwargs",)
        },
        "forwarded_body": forwarded,
        "note": "This is a simulation – no request was sent to llama.cpp.",
    })


@app.post("/switch")
async def api_switch_ensemble(request: ServeRequest):
    assert orchestrator is not None, "Orchestrator not initialized"
    if bool(request.ensemble) == bool(request.profile):
        return {"status": "error", "message": "Please specify exactly one of 'ensemble' or 'profile'."}

    if orchestrator.current_process:
        orchestrator.is_running = False
        orchestrator.current_process.terminate()
        await orchestrator.current_process.wait()

    orchestrator.is_running = True
    if request.profile:
        orchestrator.server_task = asyncio.create_task(
            orchestrator.run_profile_server_loop(request.profile, request.overrides)
        )
        return {"status": "success", "message": f"Switched to profile {request.profile}"}

    orchestrator.server_task = asyncio.create_task(orchestrator.run_server_loop(request.ensemble, request.overrides))
    return {"status": "success", "message": f"Switched to ensemble {request.ensemble}"}


@app.post("/stop")
async def api_stop():
    assert orchestrator is not None, "Orchestrator not initialized"
    if orchestrator.current_process and orchestrator.is_running:
        orchestrator.is_running = False
        orchestrator.current_process.terminate()
        await orchestrator.current_process.wait()
        return {"status": "success", "message": "Server stopped, VRAM released."}
    return {"status": "idle"}


def parse_cli_overrides(unknown_args: list) -> dict:
    overrides, i = {}, 0
    while i < len(unknown_args):
        arg = unknown_args[i]
        if arg.startswith("-"):
            key = canonical_key(arg)
            if i + 1 < len(unknown_args) and not unknown_args[i + 1].startswith("-"):
                val: Any = unknown_args[i + 1]
                if val.lower() in {"true", "false"}:
                    val = val.lower() == "true"
                else:
                    try:
                        val = int(val)
                    except ValueError:
                        try:
                            val = float(val)
                        except ValueError:
                            pass
                overrides[key] = val
                i += 2
            else:
                overrides[key] = True
                i += 1
        else:
            i += 1
    return overrides


def main():
    global orchestrator, DATA_DIR, PROFILES_DIR, ENSEMBLES_DIR

    parser = argparse.ArgumentParser(description="Llama Orchestrator (Compiler & Dispatcher)")
    parser.add_argument("mode", choices=["serve", "bench", "eval"])
    parser.add_argument("--ensemble", help="Name of the YAML in /ensembles (for 'serve' in router mode)")
    parser.add_argument("--profile", help="Name of the YAML in /profiles (for 'serve' single profile, 'bench' and 'eval')")
    parser.add_argument("--dataset", default="data/wikitext-2-raw.txt")
    parser.add_argument(
        "--api-port", type=int, default=None,
        help="Port for the dispatcher REST API (default: dispatcher.port from the ensemble, otherwise 8001)",
    )
    parser.add_argument(
        "--instance",
        default=None,
        metavar="NAME",
        help=(
            "Instance name (folder under instances/, e.g. 'Laptop' or 'Speedy'). "
            "Sets paths to instances/<NAME>/profiles|ensembles|data/ "
            "and reads the machine_guid from instances/<NAME>/instance.yaml."
        ),
    )
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Only compile ensemble/profile to llama.cpp INI and display the start command.",
    )

    args, unknown = parser.parse_known_args()
    overrides = parse_cli_overrides(unknown)

    # ── Resolve instance and set global paths ─────────────────────────────────
    machine_id = "unknown"
    if args.instance:
        machine_id, instance_dir = _resolve_instance(args.instance)
        DATA_DIR      = instance_dir / "data"
        PROFILES_DIR  = instance_dir / "profiles"
        ENSEMBLES_DIR = instance_dir / "ensembles"
        for d in (DATA_DIR, PROFILES_DIR, ENSEMBLES_DIR):
            d.mkdir(parents=True, exist_ok=True)
    else:
        # Legacy mode: original directory structure
        for d in (DATA_DIR, PROFILES_DIR, ENSEMBLES_DIR):
            d.mkdir(parents=True, exist_ok=True)

    # Create orchestrator only now so that the paths are set
    orchestrator = LlamaOrchestrator(machine_id=machine_id)

    # api_port: CLI argument takes precedence; fallback to dispatcher.port in ensemble YAML; then 8001.
    api_port: int = args.api_port or 8001
    if args.api_port is None and args.ensemble:
        _ensemble_file = ENSEMBLES_DIR / f"{args.ensemble}.yaml"
        if _ensemble_file.exists():
            with open(_ensemble_file, "r", encoding="utf-8") as _f:
                _ensemble_raw = yaml.safe_load(_f) or {}
            _dispatcher_cfg = _ensemble_raw.get("dispatcher") or {}
            api_port = int(_dispatcher_cfg.get("port") or _dispatcher_cfg.get("api_port") or 8001)

    orchestrator.api_port = api_port  # for startup log

    if args.mode == "serve":
        if bool(args.ensemble) == bool(args.profile):
            sys.exit("[ERROR] 'serve' requires exactly one of --ensemble or --profile")

        if args.compile_only:
            if args.ensemble:
                binary, compiled_params, cli_args = orchestrator.compile_serve_ensemble(args.ensemble, overrides)
                print(f"[OK] Preset written: {compiled_params['preset_path']}")
            else:
                binary, compiled_params, cli_args = orchestrator.compile_serve_profile(args.profile, overrides)
                print(f"[OK] Profile compiled: {args.profile}")
            print(quote_cmd([binary] + cli_args))
            return

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            if args.ensemble:
                orchestrator.server_task = asyncio.create_task(orchestrator.run_server_loop(args.ensemble, overrides))
            else:
                orchestrator.server_task = asyncio.create_task(orchestrator.run_profile_server_loop(args.profile, overrides))
            yield
            # Clean shutdown: terminate and await process first, then cancel task.
            # This prevents the RuntimeError in the BaseSubprocessTransport destructor
            # that occurs when the event loop is closed before the transport is released.
            orchestrator.is_running = False
            if orchestrator.current_process:
                try:
                    orchestrator.current_process.terminate()
                    await asyncio.wait_for(orchestrator.current_process.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    orchestrator.current_process.kill()
                    await orchestrator.current_process.wait()
                except ProcessLookupError:
                    pass
            if orchestrator.server_task and not orchestrator.server_task.done():
                orchestrator.server_task.cancel()
                try:
                    await orchestrator.server_task
                except (asyncio.CancelledError, Exception):
                    pass

        app.router.lifespan_context = lifespan

        print(f"[INFO] Starting API Web-Interface on http://localhost:{api_port}")
        uvicorn.run(app, host="0.0.0.0", port=api_port)

    elif args.mode == "bench":
        if not args.profile:
            sys.exit("[ERROR] 'bench' requires the argument --profile")
        assert orchestrator is not None
        _run_task_safe(orchestrator.run_bench(args.profile, overrides), orchestrator)

    elif args.mode == "eval":
        if not args.profile:
            sys.exit("[ERROR] 'eval' requires the argument --profile")
        assert orchestrator is not None
        _run_task_safe(orchestrator.run_eval(args.profile, args.dataset, overrides), orchestrator)


if __name__ == "__main__":
    main()
