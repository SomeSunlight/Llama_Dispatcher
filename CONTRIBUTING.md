# Contributing to the Llama Dispatcher

This project follows strict principles regarding dependencies, configuration architecture, proxy behavior, database integrity, and observable runtime transparency.

## 1. Environment & Dependencies

- **Strict `uv` Usage:** We do not use `pip`, `conda`, or `poetry` directly. All dependencies are managed exclusively via `uv add <package>`.
- **Isolation:** Tests and executions are performed using `uv run`.

## 2. Instance Separation

The main code repository (`src/`, `defaults/`, documentation) is public. Machine-specific configurations under `instances/` are **excluded in the main `.gitignore`** and are managed as **separate private repos**.

Nothing under `instances/` must be included in the public repo – it contains model paths, machine paths, and private operational data. The `instances/` repo has its own `.gitignore` that excludes `*/data/*.db` and `*/data/*.ini` (runtime artifacts).

## 3. Separation of Concerns – Where things belong

The configuration cascade has clear boundaries of responsibility:

| Level | Location | Responsibility |
|---|---|---|
| Model Defaults | `defaults/<model>.yaml` | Hardware-agnostic sampling (once for all machines) |
| Engine Defaults | `instances/<name>/engines/<engine>.yaml` | Binary path, GPU flags (machine-specific) |
| Profile | `instances/<name>/profiles/` | Model path, context, quantization, operational modes |
| Ensemble | `instances/<name>/ensembles/` | Which models, proxy aliases, sampling overrides |

**Never** place engine flags in profiles, model paths in engine files, or duplicate sampling defaults. Every piece of information exists exactly once in the correct location.

## 4. Parameter Canonicalization

- New llama.cpp parameters must be added to `PARAM_MAPPING` in `dispatcher.py`.
- Shorthands (`c`, `ngl`, `ctk`, `ctv`, `ot`) and spelling variants (`top_p`, `top-p`) are internally mapped to canonical long forms without leading dashes.
- JSON fields in the database store parameters in canonical long form without leading dashes.

Important mappings:

```
c          → ctx-size
ngl        → n-gpu-layers
ctk        → cache-type-k
ctv        → cache-type-v
ot         → override-tensor   (not override-kv – that is GGUF metadata)
top_p      → top-p
repeat_penalty → repeat-penalty
```

## 5. Proxy Architecture – Core Principles

The Dispatcher is a **full OpenAI-compatible Proxy**. This is a deliberate architectural decision with clear rules:

**Proxy values always overwrite client values.** If `temperature: 0.3` is configured in the ensemble, llama.cpp receives `0.3` – regardless of what the client sends. This is the purpose of centralized configuration.

**`target:` Aliases** exist only in the proxy, not in the llama.cpp-INI. A `target:` refers to a real alias. The proxy injects the sampling parameters of the proxy-only alias and rewrites the `model:` field. This allows multiple "personalities" to share the same model in VRAM without loading it twice.

**`chat_template_kwargs`** is a Proxy-Only key: It is not written to the llama.cpp-INI, but is injected by the proxy into every request. This allows `enable_thinking` to be controlled centrally for all clients.

**No magic rewrites without configuration.** All transformations are based on explicit YAML configuration in the ensemble. The code only describes what the configuration mandates.

## 6. Profiles and Ensembles

**Profiles** are model- and hardware-near templates for an operational mode. They can be started directly (`serve --profile <name>`). This is the recommended way for testing and fine-tuning before a profile is included in an ensemble.

**Ensembles** define the proxy operation: which real models are in the INI, which aliases the proxy makes visible to the outside, and which parameters are injected per alias. `model_defaults:` in the ensemble (the `[*]` section of the INI) is optional and only makes sense for parameters that should truly apply to all real models – not as a replacement for `defaults/<model>.yaml`.

## 7. Engine Templates

Engine templates under `defaults/engine-templates/` are templates for copying. They are **not used directly by the Dispatcher**. Instance-specific engines under `instances/<name>/engines/` use `common:` and `serve:` sections that are embedded into the profile via deep merge.

Search order: `instances/<name>/engines/` → `defaults/engine-templates/` (only as a fallback if no instance engine is present).

## 8. Database Integrity

The current DB is `instances/<name>/data/metrics.db`. There is no migration from older versions; the schema is built fresh via `src/init_db.sql`.

**Timestamps:** Timezone-aware, format `YYYY-MM-DD HH:MM:SS+HH:MM`. Directly readable, sortable, and UTC-correct.

`execution_runs` is the historical run header and is not modified after being written.

For schema evolution:
- No destructive updates to existing measurement data.
- Use `PRAGMA user_version`.
- Map migrations in a controlled manner in `database_manager.py`.

## 9. Runtime Instances are Mandatory

- An `execution_run` → the main process.
- A `serve_model_instance` → per effectively loaded model.
- `metrics_serve` refers to **both** (historical wrapper + specific model origin).

Even in Single Profile Mode, exactly one runtime instance must be recorded. This makes evaluations homogeneous between single and ensemble modes.

## 10. Proxy Requests are Logged

The proxy logs **every** forwarded request in `proxy_requests`:
- Endpoint, requested model, stream flag
- Injected parameters (as JSON)
- Token counts (Prompt + Completion)
- Latency, TTFT, status code, finish_reason
- `req_enable_thinking` (from `chat_template_kwargs`)

This is the only place where client request parameters are observed – because the Dispatcher acts as a proxy in between. llama.cpp itself only sees the already transformed request.

## 11. FastAPI and Asynchronicity

- External payloads for FastAPI endpoints must be verified via Pydantic models or explicit validation.
- No blocking calls (`time.sleep`, `subprocess.run`) in the orchestrator.
- Start subprocesses asynchronously and read logs asynchronously.

## 12. Metrics and Error Bars

- `metrics_bench.speed_error` is mandatory.
- `metrics_eval.perplexity_error` is mandatory, where available.
- No measurement without an error value if repetitions are available.

## 13. Development Style

- Prefer small, understandable changes.
- Strictly separate observed, declared, and unknown facts.
- Configuration describes intent; code implements it – never the other way around.
- Make new features testable first with `--compile-only` or `/debug/preview`.
