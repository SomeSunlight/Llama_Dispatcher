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

# Projektpfade: funktioniert sowohl als src/dispatcher.py als auch direkt im Projektroot.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "src" else Path.cwd()
SRC_DIR = PROJECT_ROOT / "src"

# Pfade sind Defaults für Legacy-Modus (ohne --instance).
# In main() werden sie bei Angabe von --instance auf den Instanz-Ordner umgebogen.
DATA_DIR: Path = PROJECT_ROOT / "data"
PROFILES_DIR: Path = PROJECT_ROOT / "profiles"
ENSEMBLES_DIR: Path = PROJECT_ROOT / "ensembles"
# Modell-Hersteller-Defaults: immer im Haupt-Repo, nie instanzspezifisch.
DEFAULTS_DIR: Path = PROJECT_ROOT / "defaults"


# ── Instanz-Konfiguration ──────────────────────────────────────────────────────

def _resolve_instance(instance_name: str) -> tuple[str, Path]:
    """
    Liest instance.yaml aus instances/<name>/ und gibt (machine_guid, instance_dir) zurück.
    Legt Verzeichnis und instance.yaml an, falls noch nicht vorhanden (Erststart).
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

    # Erststart: neue Instanz anlegen
    machine_guid = str(uuid.uuid4())
    instance_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "profiles", "ensembles", "engines"):
        (instance_dir / sub).mkdir(exist_ok=True)
    config = {"nickname": instance_name, "machine_guid": machine_guid}
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"[INSTANCE] Neue Instanz '{instance_name}' erstellt: {instance_dir}")
    print(f"[INSTANCE] GUID={machine_guid}  (in {config_file} gespeichert)")
    return machine_guid, instance_dir


class ServeRequest(BaseModel):
    ensemble: str | None = Field(None, description="Name des Ensemble-YAMLs")
    profile: str | None = Field(None, description="Name des Profil-YAMLs für klassischen Einzelmodell-Serve")
    overrides: dict = Field(default_factory=dict, description="Flüchtige Parameter für die Engine")


# Intern wird kanonisch ohne führende Dashes gespeichert/geschrieben.
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

# Nur Convenience-Gruppen für YAML. Diese Schlüssel existieren nicht in llama.cpp selbst;
# ihr Inhalt wird vor der Kanonisierung flach in die Modellparameter gemerged.
MODEL_PARAM_GROUP_KEYS = {"sampling", "sampler", "generation", "defaults"}

# Parameter, die der Router selbst bekommt, nicht die einzelnen Modellinstanzen.
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

# Struktur-/Dispatcher-Schlüssel, die nie in llama.cpp-Presets gehören.
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
    "extends",         # Default-Profil-Referenz
    "default_profile", # Alternative Schreibweise
}

# Parameter, die nur über den Proxy weitergegeben werden (nicht in die llama.cpp INI).
PROXY_ONLY_KEYS: frozenset[str] = frozenset({
    "chat-template-kwargs",  # Kanonische Form von chat_template_kwargs
})

# Request-Zeit Sampling-Parameter für den Proxy.
# Diese werden aus dem Profil/Ensemble in jeden Client-Request injiziert.
# Kanonische Form (Bindestriche); beim Injizieren ins JSON → Unterstriche.
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
    """Merged override rekursiv in base. Verschachtelte Dicts werden zusammengeführt."""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def canonical_key(key: str) -> str:
    """Normalisiert YAML-/CLI-Schlüssel auf llama.cpp-Argumentnamen ohne führende Dashes."""
    clean = str(key).strip().lstrip("-").replace("_", "-")
    return PARAM_MAPPING.get(clean, PARAM_MAPPING.get(clean.replace("-", "_"), clean))


def flatten_model_param_groups(params: dict[str, Any]) -> dict[str, Any]:
    """
    Erlaubt lesbare YAML-Gruppen wie:

        sampling:
          temperature: 0.7
          top_p: 0.9

    llama.cpp erwartet in der INI aber flache Argumentnamen. Deshalb werden diese
    Gruppen hier vor der Kanonisierung ausgepackt. Bei Kollisionen gewinnt der
    explizit flache Schlüssel im gleichen Dict.
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
    """Schreibt Werte so, wie llama.cpp-INI sie erwartet: schlicht, ohne Python-Repräsentation."""
    if isinstance(value, bool):
        # llama.cpp dokumentiert -fa/--flash-attn als on|off|auto; boolsche Flags wie jinja
        # bleiben true|false. Das vermeidet genau die Sorte stiller Syntaxfehler,
        # die bei brandneuen CLI-Optionen lästig sind.
        if key in {"flash-attn", "reasoning"}:
            return "on" if value else "off"
        return "true" if value else "false"
    return str(value)


def quote_cmd(parts: list[str]) -> str:
    """Lesbarer, kopierbarer CLI-String für DB/Logs."""
    if os.name == "nt":
        import subprocess

        return subprocess.list2cmdline([str(p) for p in parts])
    return shlex.join([str(p) for p in parts])


class LlamaOrchestrator:
    def __init__(self, machine_id: str = "unknown"):
        self.current_process: asyncio.subprocess.Process | None = None
        self.is_running: bool = False
        # Instanz-Modus (--instance): DATA_DIR = instances/<name>/data/ → metrics.db
        # Legacy-Modus (kein --instance): DATA_DIR = data/ → metrics_v4.db (Abwärtskompatibilität)
        db_filename = "metrics.db" if "instances" in DATA_DIR.parts else "metrics_v4.db"
        self.db = MetricsDatabase(DATA_DIR / db_filename, SRC_DIR / "init_db.sql", machine_id=machine_id)
        self.fail_count: int = 0
        self.server_task: asyncio.Task | None = None
        self.api_port: int = 8001  # wird von main() gesetzt, für Startup-Log
        self._current_telemetry: dict = {}
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        # Proxy-State: wird beim Server-Start gesetzt, beim Stop gecleart
        self._active_run_id: str | None = None
        self._proxy_target_port: int | None = None
        self._active_model_aliases: list[str] = []
        # Sampling-Parameter pro Alias für Proxy-Injektion: {"workhorse": {"temperature": 1.0, ...}}
        self._proxy_sampling_params: dict[str, dict[str, Any]] = {}
        # Proxy-only Alias-Remapping: {"creative": "workhorse"} → Client ruft "creative" auf,
        # Proxy injiziert dessen Sampling-Params und schreibt model→"workhorse" um.
        # Kein eigener llama.cpp-Eintrag → ein Modell im VRAM, beliebig viele Aliase.
        self._proxy_alias_targets: dict[str, str] = {}

    def load_yaml(self, folder: str | Path, name: str) -> dict:
        base = Path(folder)
        path = base / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Konfiguration '{path}' nicht gefunden.")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Konfiguration '{path}' muss ein YAML-Objekt enthalten.")
        return data

    def load_profile(self, profile_name: str) -> dict:
        """
        Lädt ein Profil und merged es mit Model- und Engine-Defaults.

        Profile referenzieren Defaults über:
            defaults:
              model:  "gemma"    → defaults/gemma.yaml               (sampling, hardware-agnostisch)
              engine: "vulkan"   → instances/<name>/engines/vulkan.yaml  (bin_dir, maschinenspezifisch)

        Merge-Reihenfolge (niedrigste → höchste Priorität):
          1. Model-Defaults   (defaults/<model>.yaml)
          2. Engine-Defaults  (instances/<name>/engines/<engine>.yaml  oder engine-templates/ als Fallback)
          3. Profil selbst

        Rückwärtskompatibilität: altes 'extends: "gemma"' wird wie
        'defaults: { model: "gemma" }' behandelt (kein Engine-Default).
        """
        profile = self.load_yaml(PROFILES_DIR, profile_name)

        # Neue Syntax: defaults.model / defaults.engine
        defaults_cfg: dict[str, Any] = profile.get("defaults") or {}
        # Alte Syntax (deprecated): extends / default_profile → wird zu defaults.model gemappt
        if not defaults_cfg:
            legacy = profile.get("extends") or profile.get("default_profile")
            if legacy:
                defaults_cfg = {"model": str(legacy).strip()}

        model_name  = defaults_cfg.get("model")
        engine_name = defaults_cfg.get("engine")

        base: dict[str, Any] = {}

        # 1. Model-Defaults laden (defaults/<model>.yaml)
        if model_name:
            model_file = DEFAULTS_DIR / f"{model_name}.yaml"
            if model_file.exists():
                with open(model_file, "r", encoding="utf-8") as f:
                    base = yaml.safe_load(f) or {}
            else:
                print(f"[WARN] Modell-Default '{model_name}' nicht gefunden: {model_file}")

        # 2. Engine-Defaults laden
        #    Suchreihenfolge: instances/<name>/engines/ → defaults/engine-templates/ (Fallback)
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
                print(f"[WARN] Engine-Konfig '{engine_name}' nicht gefunden "
                      f"(gesucht in: {instance_engines}, {template_engines})")

        # 3. Profil merged (höchste Priorität)
        merged = _deep_merge(base, profile) if base else dict(profile)

        # Dispatcher-interne Schlüssel entfernen (fliessen nicht in llama.cpp-INI)
        for k in ("defaults", "extends", "default_profile"):
            merged.pop(k, None)
        return merged

    async def get_llama_version(self, binary: Path) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                str(binary), "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            text = stdout.decode("utf-8", errors="ignore")
            match = re.search(r"commit\s+([a-f0-9]+)", text)
            return match.group(1) if match else (text.strip().splitlines()[0] if text.strip() else "unknown")
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

        # Autoload soll standardmässig aktiv bleiben: dann lädt der Router auf Request nach.
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
            # Flacht Convenience-Gruppen pro Quelle ab. Dadurch können common.sampling,
            # serve.sampling und Ensemble-spezifische sampling-Overrides sauber
            # übereinandergelegt werden, ohne sich als kompletter Dict-Wert zu ersetzen.
            merged.update(flatten_model_param_groups(source or {}))

        merge_source(profile.get("common", {}) or {})
        merge_source(profile.get("serve", {}) or {})
        merge_source(model_entry.get("params", {}) or {})
        merge_source(model_entry.get("overrides", {}) or {})

        # Erlaubt kurze direkte Overrides im Ensemble-Eintrag:
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

        # In einem Ensemble soll standardmässig erst bei Bedarf geladen werden.
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
        """Kompiliert Ensemble + Profile in eine offizielle llama.cpp Router-Preset-INI."""
        ensemble = self.load_yaml(ENSEMBLES_DIR, ensemble_name)

        # defaults.engine auf Ensemble-Ebene: liefert bin_dir aus instances/<name>/engines/<engine>.yaml
        # (analog zu defaults.engine in Profilen, aber hier für den Server-Start selbst).
        # Suchreihenfolge: instances/<name>/engines/ → defaults/engine-templates/ (Fallback)
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
                    # Template als Basis; explizite engine:-Einträge im Ensemble überschreiben.
                    engine = {**engine_template, **engine}
                    break
            else:
                print(f"[WARN] Ensemble-Engine '{engine_default_name}' nicht gefunden "
                      f"(gesucht in: {instance_engines}, {template_engines})")

        engine.update(overrides or {})
        engine = canonicalize_params(engine)

        binary = self._resolve_server_binary(engine)

        preset_name = engine.get("preset-path") or engine.get("preset_path") or f"{ensemble_name}_models.ini"
        preset_path = Path(preset_name)
        if not preset_path.is_absolute():
            preset_path = DATA_DIR / preset_path

        # "defaults:" ist jetzt für Dispatcher-Konfiguration reserviert (defaults.engine).
        # Modell-Defaults für die INI kommen ausschliesslich aus "model_defaults:".
        global_params = canonicalize_params(
            flatten_model_param_groups(ensemble.get("model_defaults", {}) or {})
        )
        models: dict[str, dict[str, Any]] = {}       # echte llama.cpp-Einträge
        alias_targets: dict[str, str] = {}            # proxy-only: alias → llama.cpp-alias

        for mod in ensemble.get("models", []) or []:
            if not isinstance(mod, dict) or "profile" not in mod:
                raise ValueError("Jeder Eintrag in 'models' muss mindestens 'profile' enthalten.")

            profile_name = mod["profile"]
            profile = self.load_profile(profile_name)
            alias = str(mod.get("alias") or profile_name)
            target = str(mod["target"]) if "target" in mod else None

            if alias in models or alias in alias_targets:
                raise ValueError(f"Doppelter Modell-Alias im Ensemble '{ensemble_name}': {alias}")

            params = self._model_section_params(profile, mod)

            if target:
                # Proxy-only: kein eigener INI-Eintrag, Anfragen werden auf target umgeleitet.
                # Sampling-Params für diesen Alias werden trotzdem gespeichert (für Proxy-Injektion).
                alias_targets[alias] = target
            else:
                has_model_source = any(k in params for k in ("model", "hf-repo", "model-url"))
                alias_looks_like_cache_id = "/" in alias and ":" in alias
                if not has_model_source and not alias_looks_like_cache_id:
                    raise ValueError(
                        f"Modell '{alias}' aus Profil '{profile_name}' hat keine Quelle. "
                        "Erwarte 'm/model', 'hf-repo' oder 'model-url' im Profil bzw. Ensemble-Eintrag."
                    )
                models[alias] = params

        # Validierung: jeder target muss ein echtes Modell im Ensemble sein
        for a, t in alias_targets.items():
            if t not in models:
                raise ValueError(
                    f"Alias '{a}' hat target='{t}', aber '{t}' ist kein (echtes) Modell "
                    f"im Ensemble '{ensemble_name}'."
                )

        if not models:
            raise ValueError(f"Ensemble '{ensemble_name}' enthält keine echten Modelle (ohne target:).")

        self._write_models_preset_ini(preset_path, global_params, models)
        cli_args = self._router_cli_args(engine, preset_path)

        preset_content = preset_path.read_text(encoding="utf-8")

        # Proxy-Sampling-Parameter für ALLE Aliase (echte + proxy-only).
        # REQUEST_SAMPLING_KEYS → konvertiert zu Unterstrichen für den JSON-Body.
        proxy_sampling: dict[str, dict[str, Any]] = {}
        for m in ensemble.get("models", []) or []:
            a = str(m.get("alias") or m.get("profile"))
            # Für echte Aliase: params aus models-dict. Für proxy-only: nochmal berechnen.
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
        }
        return binary, compiled, cli_args

    def _params_to_cli_args(self, params: dict[str, Any], mode: str = "serve") -> list[str]:
        """Übersetzt kanonisierte Parameter in llama.cpp CLI-Argumente.

        Wird für den klassischen Einzelprofil-Serve und weiterhin für Bench/Eval
        verwendet. Der Router-/Ensemble-Modus erzeugt dagegen bewusst eine INI.
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
                # llama.cpp erwartet bei einigen Tri-State/Bool-Argumenten einen Wert,
                # bei klassischen Flags genügt die Präsenz des Arguments.
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
        """Klassischer Einzelmodell-Serve ohne Router-INI.

        Das ist absichtlich kein synthetisches Ensemble: Für Tests und direkte
        Einzelkonfigurationen soll wieder genau ein llama-server-Prozess mit den
        Parametern aus profile.common + profile.serve + CLI-Overrides starten.
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
        """Für Bench und Eval: Nutzt die bisherige Profil-Logik isoliert weiter."""
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
        """Parst die von llama.cpp geloggten Child-Server-Argumente in kanonische Langformen."""
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
            # Mehrfach vorkommende Parameter, z. B. override-tensor, bleiben erhalten.
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
        """Liest llama.cpp-Logs und erfasst Runtime-Instanzen plus Request-Timings.

        Wichtig: Client-Request-Parameter wie temperature/top_p werden im normalen
        llama.cpp-Log nicht zuverlässig ausgegeben. Der Dispatcher protokolliert daher
        nur beobachtbare Engine-/Runtime-Parameter und Timings, keine Client-Telemetrie.
        CancelledError und KeyboardInterrupt werden sauber weitergereicht, damit der
        aufrufende Loop den Transport freigeben kann, bevor die Event-Loop endet.
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

            # Router: Child-Server wird mit Alias und Port gestartet.
            spawn_match = re.search(r"spawning server instance with name=([^\s]+) on port (\d+)", clean_line)
            if spawn_match:
                self._finalize_pending_spawn(run_id, state)
                alias, port = spawn_match.group(1), int(spawn_match.group(2))
                state["pending_spawn"] = {"alias": alias, "port": port, "argv": []}
                state["alias_by_port"][str(port)] = alias
                continue

            # Danach loggt llama.cpp die konkrete Child-CLI zeilenweise.
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

            # Optionaler JSON-Log-Modus: bleibt bewusst defensiv.
            try:
                log_data = json.loads(clean_line)
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

            # Einzelne Child-Logs wie "loading model 'C:\...gguf'" beschreiben keine neue
            # Router-Instanz; die Instanz wurde bereits beim spawning-Block erfasst.

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
                llama_ver = await self.get_llama_version(Path(binary))

                cmd_str = quote_cmd([binary] + cli_args)
                run_id = str(uuid.uuid4())
                model_params = compiled_params["models"][profile_name]

                # Proxy-State setzen
                self._active_run_id = run_id
                self._proxy_target_port = (
                    int(model_params["port"]) if str(model_params.get("port", "")).isdigit() else None
                )
                self._active_model_aliases = [profile_name]
                sp = {k.replace("-", "_"): v for k, v in model_params.items()
                      if k in REQUEST_SAMPLING_KEYS and v is not None}
                self._proxy_sampling_params = {profile_name: sp} if sp else {}
                if sp:
                    print(f"[PROXY] {profile_name}: " + "  ".join(f"{k}={v}" for k, v in sp.items()))

                self.db.insert_run(
                    run_id,
                    "serve",
                    profile_name,
                    llama_ver,
                    cmd_str,
                    model_params,
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
                    binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
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
                    print(f"\n[FATAL] Server ist direkt beim Start abgestürzt ({uptime:.1f}s). Breche ab.")
                    self.is_running = False
                    os._exit(1)
                else:
                    self.fail_count = 0
                    print("\n[ORCHESTRATOR] Server unerwartet beendet. Neustart in 5s...")
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
                llama_ver = await self.get_llama_version(Path(binary))

                cmd_str = quote_cmd([binary] + cli_args)
                run_id = str(uuid.uuid4())

                # Proxy-State setzen
                self._active_run_id = run_id
                self._proxy_target_port = int(compiled_params["engine"].get("port", 8080))
                # Alle sichtbaren Aliase für /v1/models: echte + proxy-only
                self._active_model_aliases = (
                    list(compiled_params["models"].keys()) +
                    list(compiled_params.get("alias_targets", {}).keys())
                )
                self._proxy_sampling_params = compiled_params.get("proxy_sampling", {})
                self._proxy_alias_targets = compiled_params.get("alias_targets", {})

                # Startup-Log: vollständige Proxy-Konfiguration auf einen Blick
                print(f"\n[PROXY] Dispatcher-Port → llama.cpp-Port: "
                      f"Clients:{self.api_port}  llama.cpp:{self._proxy_target_port}")
                print(f"[PROXY] Konfigurierte Aliase:")
                for alias in self._active_model_aliases:
                    target = self._proxy_alias_targets.get(alias)
                    sp = self._proxy_sampling_params.get(alias, {})
                    kind = f"proxy-only → {target}" if target else "echt (im VRAM)"
                    params_str = "  ".join(f"{k}={v}" for k, v in sp.items()) if sp else "(keine Overrides)"
                    print(f"[PROXY]   {alias:20s}  [{kind}]  {params_str}")
                print(f"[PROXY] Debug:   GET  http://localhost:{self.api_port}/debug/config")
                print(f"[PROXY] Preview: POST http://localhost:{self.api_port}/debug/preview")

                self.db.insert_run(
                    run_id,
                    "serve",
                    ensemble_name,
                    llama_ver,
                    cmd_str,
                    compiled_params.get("engine", {}),
                    preset_path=compiled_params.get("preset_path"),
                    preset_content=compiled_params.get("preset_content"),
                    preset_sha256=compiled_params.get("preset_sha256"),
                )
                print(f"\n[ORCHESTRATOR] Booting Ensemble: {ensemble_name} | Run ID: {run_id}")
                print(f"[ORCHESTRATOR] Preset: {compiled_params['preset_path']}")
                print(f"[ORCHESTRATOR] Command: {cmd_str}")

                start_time = asyncio.get_event_loop().time()
                self.current_process = await asyncio.create_subprocess_exec(
                    binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
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
                    print(f"\n[FATAL] Server ist direkt beim Start abgestürzt ({uptime:.1f}s). Breche ab.")
                    self.is_running = False
                    os._exit(1)
                else:
                    self.fail_count = 0
                    print("\n[ORCHESTRATOR] Server unerwartet beendet. Neustart in 5s...")
                    await asyncio.sleep(5)
            except (asyncio.CancelledError, KeyboardInterrupt):
                self.is_running = False
                raise
            except Exception as e:
                print(f"[ORCHESTRATOR ERROR] {e}")
                await asyncio.sleep(5)

    async def run_bench(self, profile_name: str, overrides: dict):
        binary, params, cli_args = self.compile_task_profile(profile_name, "bench", overrides)
        llama_ver = await self.get_llama_version(Path(binary))
        cmd_str = quote_cmd([binary] + cli_args)
        run_id = str(uuid.uuid4())

        self.db.insert_run(run_id, "bench", profile_name, llama_ver, cmd_str, params)
        print(f"\n[ORCHESTRATOR] Starting Benchmark | Profile: {profile_name} | Run ID: {run_id}")
        print(f"[ORCHESTRATOR] Command: {cmd_str}\n")

        self.current_process = await asyncio.create_subprocess_exec(
            binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
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
            print("\n[ORCHESTRATOR] Bench abgebrochen, beende Child-Prozess...")
            raise
        finally:
            await self.current_process.wait()
            self.current_process = None

    async def run_eval(self, profile_name: str, dataset: str, overrides: dict):
        overrides["f"] = dataset
        binary, params, cli_args = self.compile_task_profile(profile_name, "eval", overrides)
        llama_ver = await self.get_llama_version(Path(binary))
        cmd_str = quote_cmd([binary] + cli_args)
        run_id = str(uuid.uuid4())

        self.db.insert_run(run_id, "eval", profile_name, llama_ver, cmd_str, params)
        print(f"\n[ORCHESTRATOR] Starting Evaluation | Profile: {profile_name} | Run ID: {run_id}")
        print(f"[ORCHESTRATOR] Dataset: {dataset}")
        print(f"[ORCHESTRATOR] Command: {cmd_str}\n")

        start_time = asyncio.get_event_loop().time()
        self.current_process = await asyncio.create_subprocess_exec(
            binary, *cli_args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
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
            print("\n[ORCHESTRATOR] Eval abgebrochen, beende Child-Prozess...")
            raise
        finally:
            rc = await self.current_process.wait()
            self.current_process = None
            if rc == 0 and final_perplexity > 0:
                self.db.insert_eval(
                    run_id, dataset, final_perplexity, perplexity_error, asyncio.get_event_loop().time() - start_time
                )


def _run_task_safe(coro, orc: "LlamaOrchestrator") -> None:
    """Führt eine Bench/Eval-Coroutine aus und stellt sicher, dass beim Unterbrechen
    (Ctrl+C / KeyboardInterrupt) der Child-Prozess sauber beendet und auf ihn gewartet
    wird, BEVOR die Event-Loop geschlossen wird.  Das verhindert den
    RuntimeError("Event loop is closed") im BaseSubprocessTransport-Destruktor.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(coro)
    try:
        loop.run_until_complete(task)
    except KeyboardInterrupt:
        print("\n[ORCHESTRATOR] Unterbrechung empfangen, beende Child-Prozess...")
        task.cancel()
        # Child-Prozess sicher terminieren, falls er noch läuft.
        if orc.current_process is not None:
            try:
                orc.current_process.terminate()
            except ProcessLookupError:
                pass
        # Warten bis Task und Child-Prozess wirklich fertig sind.
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
        print("[ORCHESTRATOR] Beendet.")
    finally:
        # Alle noch laufenden Tasks sauber abräumen, dann erst Loop schließen.
        try:
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:
            pass
        loop.close()


orchestrator: LlamaOrchestrator | None = None


# ── Proxy-Hilfsfunktionen ──────────────────────────────────────────────────────

def _extract_response_stats(obj: Any, stats: dict[str, Any]) -> None:
    """Extrahiert Token-Counts und finish_reason aus einem llama.cpp-Antwort-Objekt."""
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
    """Liest enable_thinking aus chat_template_kwargs. Gibt 1, 0 oder None zurück."""
    ctk = req_data.get("chat_template_kwargs")
    if isinstance(ctk, dict) and "enable_thinking" in ctk:
        return 1 if ctk["enable_thinking"] else 0
    return None


# ── Proxy-Endpoints (/v1/) ─────────────────────────────────────────────────────

@app.get("/v1/models")
async def api_models():
    """
    Gibt eine saubere Modell-Liste zurück – nur die konfigurierten Aliase,
    keine internen llama.cpp-Pfade. Ersetzt die native /v1/models-Antwort.
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
    Transparenter Proxy zu llama.cpp. Loggt Client-Parameter und Response-Statistiken
    (Token-Counts, Latenz, TTFT, finish_reason, Sampling-Werte) in der Datenbank.

    Clients zeigen einfach auf http://<host>:<api-port>/v1/ statt direkt auf llama.cpp.
    """
    assert orchestrator is not None

    if not orchestrator.is_running or orchestrator._proxy_target_port is None:
        return JSONResponse(
            {"error": {"message": "Kein Modell aktiv – warte auf Server-Start.", "type": "server_error"}},
            status_code=503,
        )

    body_bytes = await request.body()
    req_data: dict[str, Any] = {}
    if body_bytes:
        try:
            req_data = json.loads(body_bytes)
        except json.JSONDecodeError:
            pass

    is_stream = bool(req_data.get("stream", False))

    # ── Parameter-Injektion aus Profil ────────────────────────────────────────
    # Profil-Parameter haben immer Vorrang vor Client-Werten (für REQUEST_SAMPLING_KEYS
    # und chat_template_kwargs). Alles andere (model, messages, stream, max_tokens,
    # tools usw.) kommt unverändert vom Client.
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

    # ── Alias-Remapping ───────────────────────────────────────────────────────
    # Proxy-only Aliase existieren nur im Dispatcher; llama.cpp kennt nur den echten Alias.
    # "creative" → Sampling-Params injiziert (oben) + model-Feld auf "workhorse" umschreiben.
    llama_alias = orchestrator._proxy_alias_targets.get(model_alias, model_alias)
    if llama_alias != model_alias:
        remap_data = req_data.copy()
        remap_data["model"] = llama_alias
        body_bytes = json.dumps(remap_data, ensure_ascii=False).encode("utf-8")
        req_data = remap_data

    injected_json: str | None = json.dumps(injected) if injected else None

    # Host und content-length werden von httpx neu gesetzt
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
            # Nicht-Streaming: vollständige Antwort parsen
            if non_stream_buf:
                try:
                    _extract_response_stats(
                        json.loads(non_stream_buf.decode("utf-8", errors="ignore")), stats
                    )
                except (json.JSONDecodeError, ValueError):
                    pass
            # Immer loggen – auch bei Client-Disconnect (finally läuft immer)
            try:
                orchestrator.db.insert_proxy_request(
                    run_id=orchestrator._active_run_id,
                    endpoint=path,
                    model_requested=req_data.get("model"),
                    stream=1 if is_stream else 0,
                    req_temperature=req_data.get("temperature"),
                    req_top_p=req_data.get("top_p"),
                    req_top_k=req_data.get("top_k"),
                    req_min_p=req_data.get("min_p"),
                    req_max_tokens=req_data.get("max_tokens"),
                    req_enable_thinking=_extract_thinking(req_data),
                    prompt_tokens=stats.get("prompt_tokens"),
                    completion_tokens=stats.get("completion_tokens"),
                    finish_reason=stats.get("finish_reason"),
                    duration=time.monotonic() - start,
                    ttft=stats.get("ttft"),
                    status_code=stats.get("status_code", 200),
                    injected_params=injected_json,
                )
            except Exception as log_err:
                print(f"[PROXY] Logging-Fehler: {log_err}")

    media_type = "text/event-stream" if is_stream else "application/json"
    return StreamingResponse(_stream_and_log(), media_type=media_type)


# ── Debug-Endpoints ────────────────────────────────────────────────────────────

@app.get("/debug/config")
async def debug_config():
    """
    Zeigt die aktuelle Proxy-Konfiguration:
    - Welche Aliase Clients sehen
    - Welche Parameter pro Alias injiziert werden
    - Welche Aliase proxy-only sind (mit target-Remapping)
    - Auf welchen Port llama.cpp lauscht
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
    Simuliert die Proxy-Transformation eines Requests OHNE ihn weiterzuleiten.

    Schick denselben JSON-Body, den Open WebUI an /v1/chat/completions senden würde.
    Zurückgegeben wird was der Proxy daraus machen würde:
    - welche Parameter injiziert werden
    - wie das model-Feld umgeschrieben wird
    - der vollständige Body der an llama.cpp gehen würde

    Beispiel (curl):
      curl -s http://localhost:8001/debug/preview \\
        -H "Content-Type: application/json" \\
        -d '{"model":"agent","messages":[{"role":"user","content":"Hallo"}],"temperature":0.9}'
    """
    assert orchestrator is not None
    body_bytes = await request.body()
    try:
        req_data: dict[str, Any] = json.loads(body_bytes) if body_bytes else {}
    except json.JSONDecodeError:
        return JSONResponse({"error": "Ungültiger JSON-Body"}, status_code=400)

    model_alias = req_data.get("model", "")
    profile_params = orchestrator._proxy_sampling_params.get(model_alias, {})
    injected: dict[str, Any] = {}
    forwarded = req_data.copy()

    # Sampling-Injektion (identisch zur echten Proxy-Logik)
    if profile_params:
        for k, v in profile_params.items():
            if req_data.get(k) != v:
                injected[k] = {"from_profile": v, "client_sent": req_data.get(k)}
            forwarded[k] = v

    # Alias-Remapping
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
        "note": "Dies ist eine Simulation – kein Request wurde an llama.cpp gesendet.",
    })


@app.post("/switch")
async def api_switch_ensemble(request: ServeRequest):
    assert orchestrator is not None, "Orchestrator nicht initialisiert"
    if bool(request.ensemble) == bool(request.profile):
        return {"status": "error", "message": "Bitte genau eines von 'ensemble' oder 'profile' angeben."}

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
    assert orchestrator is not None, "Orchestrator nicht initialisiert"
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
    parser.add_argument("--ensemble", help="Name der YAML in /ensembles (für 'serve' im Router-Modus)")
    parser.add_argument("--profile", help="Name der YAML in /profiles (für 'serve' Einzelprofil, 'bench' und 'eval')")
    parser.add_argument("--dataset", default="data/wikitext-2-raw.txt")
    parser.add_argument(
        "--api-port", type=int, default=None,
        help="Port für die Dispatcher REST API (Default: dispatcher.port aus dem Ensemble, sonst 8001)",
    )
    parser.add_argument(
        "--instance",
        default=None,
        metavar="NAME",
        help=(
            "Instanzname (Ordner unter instances/, z. B. 'Laptop' oder 'Speedy'). "
            "Setzt Pfade auf instances/<NAME>/profiles|ensembles|data/ "
            "und liest die machine_guid aus instances/<NAME>/instance.yaml."
        ),
    )
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Nur Ensemble/Profile zu llama.cpp-INI kompilieren und den Startbefehl anzeigen.",
    )

    args, unknown = parser.parse_known_args()
    overrides = parse_cli_overrides(unknown)

    # ── Instanz auflösen und globale Pfade setzen ─────────────────────────────
    machine_id = "unknown"
    if args.instance:
        machine_id, instance_dir = _resolve_instance(args.instance)
        DATA_DIR      = instance_dir / "data"
        PROFILES_DIR  = instance_dir / "profiles"
        ENSEMBLES_DIR = instance_dir / "ensembles"
        for d in (DATA_DIR, PROFILES_DIR, ENSEMBLES_DIR):
            d.mkdir(parents=True, exist_ok=True)
    else:
        # Legacy-Modus: ursprüngliche Verzeichnisstruktur
        for d in (DATA_DIR, PROFILES_DIR, ENSEMBLES_DIR):
            d.mkdir(parents=True, exist_ok=True)

    # Orchestrator erst jetzt erstellen, damit die Pfade gesetzt sind
    orchestrator = LlamaOrchestrator(machine_id=machine_id)

    # api_port: CLI-Argument hat Vorrang; Fallback auf dispatcher.port im Ensemble-YAML; dann 8001.
    api_port: int = args.api_port or 8001
    if args.api_port is None and args.ensemble:
        _ensemble_file = ENSEMBLES_DIR / f"{args.ensemble}.yaml"
        if _ensemble_file.exists():
            with open(_ensemble_file, "r", encoding="utf-8") as _f:
                _ensemble_raw = yaml.safe_load(_f) or {}
            _dispatcher_cfg = _ensemble_raw.get("dispatcher") or {}
            api_port = int(_dispatcher_cfg.get("port") or _dispatcher_cfg.get("api_port") or 8001)

    orchestrator.api_port = api_port  # für Startup-Log im run_server_loop

    if args.mode == "serve":
        if bool(args.ensemble) == bool(args.profile):
            sys.exit("[FEHLER] 'serve' benötigt genau eines von --ensemble oder --profile")

        if args.compile_only:
            if args.ensemble:
                binary, compiled_params, cli_args = orchestrator.compile_serve_ensemble(args.ensemble, overrides)
                print(f"[OK] Preset geschrieben: {compiled_params['preset_path']}")
            else:
                binary, compiled_params, cli_args = orchestrator.compile_serve_profile(args.profile, overrides)
                print(f"[OK] Profil kompiliert: {args.profile}")
            print(quote_cmd([binary] + cli_args))
            return

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            if args.ensemble:
                orchestrator.server_task = asyncio.create_task(orchestrator.run_server_loop(args.ensemble, overrides))
            else:
                orchestrator.server_task = asyncio.create_task(orchestrator.run_profile_server_loop(args.profile, overrides))
            yield
            # Sauberer Shutdown: erst Prozess beenden und warten, dann Task canceln.
            # Das verhindert die RuntimeError-Exception im BaseSubprocessTransport-Destruktor,
            # die auftritt wenn die Event-Loop geschlossen wird bevor der Transport freigegeben wurde.
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
            sys.exit("[FEHLER] 'bench' benötigt das Argument --profile")
        assert orchestrator is not None
        _run_task_safe(orchestrator.run_bench(args.profile, overrides), orchestrator)

    elif args.mode == "eval":
        if not args.profile:
            sys.exit("[FEHLER] 'eval' benötigt das Argument --profile")
        assert orchestrator is not None
        _run_task_safe(orchestrator.run_eval(args.profile, args.dataset, overrides), orchestrator)


if __name__ == "__main__":
    main()
