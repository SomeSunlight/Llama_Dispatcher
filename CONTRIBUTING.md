# Contributing to the Llama Dispatcher

This project follows strict principles regarding dependencies, configuration architecture, proxy behavior, database integrity, and observable runtime transparency.

## 1. Environment & Dependencies

- Use `uv` for dependency management and `uv run` for tests or project execution. The canonical development rule is maintained in [Project Context](CONTEXT.md).

## 2. Instance Separation

Machine-specific configuration under `instances/` is private and versioned separately from the public Dispatcher repository. The canonical repository boundary and runtime-artifact exclusions are maintained in [Project Context](CONTEXT.md).

## 3. Separation of Concerns – Where things belong

Configuration is intentionally split between shared model defaults and machine-specific engine, profile, and ensemble files. Put a setting in the layer that owns it; the canonical responsibility matrix and anti-duplication rule are maintained in [Project Context](CONTEXT.md).

## 4. Parameter Canonicalization

Parameter keys are canonicalized by the Dispatcher, new shorthand/alias mappings belong in `PARAM_MAPPING`, and database parameter fields use the same canonical long names without leading dashes. Canonical rules are maintained in [Project Context](CONTEXT.md).
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

The Dispatcher is the client-facing OpenAI-compatible proxy: configured alias policy is authoritative, proxy-only aliases may target a loaded model, and proxy-only request values can be injected centrally. The canonical proxy invariants are maintained in [Project Context](CONTEXT.md).

## 6. Profiles and Ensembles

- **Profiles** are directly runnable model/hardware operating templates.
- **Ensembles** define proxy operation across models and aliases.
- **Engine templates** under `defaults/engine-templates/` are copy/fallback templates, not the normal instance-specific engine configuration.

Canonical responsibilities and the ensemble-defaults constraint are maintained in [Project Context](CONTEXT.md).

## 8. Database Integrity

The current DB is `instances/<name>/data/metrics.db`. There is no migration from older versions; the schema is built fresh via `src/init_db.sql`.

**Timestamps:** Timezone-aware, format `YYYY-MM-DD HH:MM:SS+HH:MM`. Directly readable, sortable, and UTC-correct.

`execution_runs` is the historical run header and is not modified after being written.

For future schema evolution, preserve measurement data and use explicit versioned migration handling. The canonical safeguards are maintained in [Project Context](CONTEXT.md).
## 9. Runtime Instances are Mandatory

The runtime telemetry model distinguishes the process run, each effectively loaded model, and measurements that link both. Even Single Profile Mode records one model instance. Canonical semantics are maintained in [Project Context](CONTEXT.md).

## 10. Proxy Requests are Logged

The proxy logs **every** forwarded request in `proxy_requests`:
- Endpoint, requested model, stream flag
- Injected parameters (as JSON)
- Token counts (Prompt + Completion)
- Latency, TTFT, status code, finish_reason
- `req_enable_thinking` (from `chat_template_kwargs`)

This is the only place where client request parameters are observed – because the Dispatcher acts as a proxy in between. llama.cpp itself only sees the already transformed request.

## 11. FastAPI and Asynchronicity

- Validate external FastAPI payloads.
- Keep orchestration and subprocess/log handling asynchronous.

Canonical implementation rules are maintained in [Project Context](CONTEXT.md).

## 12. Metrics and Error Bars

Measurements must report uncertainty when repetitions make an error value available. The required benchmark/eval error fields are maintained in [Project Context](CONTEXT.md).

## 13. Development Style

- Keep changes small and understandable.
- Separate observed, declared, and unknown facts.
- Let configuration state intent and code implement it.
- Make new behavior inspectable with `--compile-only` or `/debug/preview` where applicable.

Canonical development rules are maintained in [Project Context](CONTEXT.md).
