# Dispatcher Code — Official Context

> [!CAUTION]
> **GENERATED FILE — DO NOT EDIT.**
> This is the compact official entry for this Context Node.
> Together with `CONTEXT/` it forms the human/agent-facing Official Context Package.
>
> Edit [CONTEXT.src.md](CONTEXT.src.md) instead.

**Node:** Dispatcher Code  
**Context version:** `0.1.0-draft`

**Parent Context Node:** [Llama Dispatcher](.context/sources/ec8ca549a9905b2361cef49ad86774c4889381725f7815044ea4a82a361bfc6e/CONTEXT.md) — `0.1.0-draft`  
**Accepted Parent package:** `ec8ca549a9905b2361cef49ad86774c4889381725f7815044ea4a82a361bfc6e`

**Resulting imported Contexts:**

- **ContextCanon Foundation** — `0.2.0-draft` — via Parent Context Node **Llama Dispatcher** — Why: Reuse the same proven workflow as for context-canon itself, which is a similar LLM-assisted project. — [inspect accepted carrier](.context/sources/ec8ca549a9905b2361cef49ad86774c4889381725f7815044ea4a82a361bfc6e/CONTEXT.md)
- **Llama Dispatcher** — `0.1.0-draft` — direct Parent Context Node — [inspect accepted carrier](.context/sources/ec8ca549a9905b2361cef49ad86774c4889381725f7815044ea4a82a361bfc6e/CONTEXT.md)

## Local Overview

<!-- contextcanon-placement-overview:start -->
<!-- cc:placement-overview id="ONB-9434DC39E0AE" -->
- Dispatcher code compiles profiles and ensembles into llama.cpp parameters, starts llama.cpp, and collects metrics.

<!-- cc:placement-overview id="ONB-52671788E89A" -->
- The Dispatcher proxy exposes configured model aliases to clients, enforces centrally configured request parameters, and forwards effective requests to llama.cpp.

<!-- cc:placement-overview id="ONB-3AA7204F1FD7" -->
- A proxy-only alias can target a real llama.cpp alias, rewrite the request model, and apply its own policy while sharing the same loaded model in VRAM.

<!-- cc:placement-overview id="ONB-19C8A7718A41" -->
- chat_template_kwargs is injected by the proxy into requests and is not written to the llama.cpp INI.

<!-- cc:placement-overview id="ONB-73A34A2AD35A" -->
- Proxy handling distinguishes the client model alias, the resolved backing profile, and the effective target model sent to llama.cpp.

<!-- cc:placement-overview id="ONB-1F0733D8FD42" -->
- Ensemble mode starts llama.cpp with the Dispatcher proxy; single-profile mode starts llama.cpp directly from one profile without router INI or proxy aliasing.

<!-- cc:placement-overview id="ONB-5E681FFCD08F" -->
- An execution_run represents the main process.

<!-- cc:placement-overview id="ONB-C4C94C6CDECA" -->
- A serve_model_instance represents one effectively loaded model.

<!-- cc:placement-overview id="ONB-3EA477E1491E" -->
- metrics_serve refers to both the historical execution run and the specific loaded-model origin.

<!-- cc:placement-overview id="ONB-1DCD56E83A83" -->
- The Dispatcher proxy is the observation point for original client request parameters; llama.cpp sees the already transformed request.
<!-- contextcanon-placement-overview:end -->

## Local State

<!-- contextcanon-placement-state:start -->
<!-- cc:placement-state id="ONB-CCF62CBAA356" -->
- The current runtime keeps compiled alias policy but not a full provenance tree for each value; it can identify dispatcher_policy plus alias/profile context, not the exact originating configuration layer.

<!-- cc:placement-state id="ONB-C4C1FD4D00BE" -->
- The Dispatcher proxy defaults to port 8001.

<!-- cc:placement-state id="ONB-C2F8E48BE5EA" -->
- The internal llama.cpp server defaults to port 8081.

<!-- cc:placement-state id="ONB-9F3DE4C4C5D0" -->
- The Dispatcher proxy currently provides no browser web UI.

<!-- cc:placement-unresolved id="ONB-5D4DB3C8503C" -->
- Open question: Are existing metrics databases upgraded additively, or is there no migration from older versions and the schema is built fresh?

<!-- cc:placement-unresolved id="ONB-0C719E0D5E75" -->
- Open question: What is the canonical proxy request telemetry table name: metrics_proxy_requests or proxy_requests?
<!-- contextcanon-placement-state:end -->

## How to use this context

Apply all Rules below to every task in this Node.

For the current task, evaluate each Topic condition. When one matches, read every **Required** target before continuing; read **Optional** targets only when useful.

## Rules from ContextCanon Foundation

### Canonical context

#### `CC-001` — One official package

The compiled Official Context Package is the single canonical context for a Node: it applies to the Node itself and is the package meaning published to child Nodes.

#### `CC-002` — Edit source, not generated output

Human context changes are authored in `CONTEXT.src.md`; generated context views, package contents, machine state, and harness adapters are not edited directly.

### Machine state

#### `CC-003` — Keep compiler bookkeeping out of the normal workflow

Framework bookkeeping belongs under `.context/` and should not be required reading for normal human or agent work.

### Composition

#### `CC-004` — No implicit Source precedence

Context Sources are composed without implicit precedence; conflicts are resolved explicitly through local changes rather than Source order.

#### `CC-013` — Parents are unordered

A Node may compose several semantic Parents. Parent order has no precedence; non-orthogonal conflicts must be resolved explicitly.

### Identity

#### `CC-005` — Stable identity

Every addressable context element has a stable ID independent of its title, wording, file location, and presentation.

#### `CC-006` — Publish IDs that children may reference

Published official contexts expose stable IDs for Rules and other elements that child Nodes may reference.

### Progressive disclosure

#### `CC-007` — Keep entry context small

Keep the official entry context compact and use Topics to load deeper context only when needed; Topic targets distinguish Required from Optional material.

### Project state

#### `CC-008` — State stays local

`STATE.md` describes the current local project situation and is never inherited as governance by child Nodes.

### Harness independence

#### `CC-009` — Canonical context is model- and harness-neutral

Project code and canonical project context must not depend on a particular LLM or agent harness; harness-specific files are thin generated adapters at the edge.

### Repository conventions

#### `CC-012` — Align Node roots with governed files

Prefer Node roots that contain the files they primarily govern; keep the existing directory structure when it already fits.

#### `CC-010` — Keep familiar repository documents useful

Keep `README.md`, `CONTRIBUTING.md`, and `CHANGELOG.md` present when they are useful to the repository even when ContextCanon is present.

### Documentation style

#### `CC-011` — Write for intelligent readers

Write technical documentation in precise, plain prose for intelligent readers; introduce unfamiliar concepts before using specialized terms and avoid unexplained internal shorthand, inflated marketing language, and unnecessary jargon.

## Rules from Llama Dispatcher

### Onboarding placement

#### `ONB-B97F676A25A3` — Keep configuration in its owning layer

Maintain each configuration fact once in the layer that owns it; do not put engine flags in profiles, model paths in engine files, or duplicate model sampling defaults.

#### `ONB-D855038AE157` — Configuration precedence

Configuration is deep-merged in this order: model defaults, instance engine defaults, profile, ensemble model entry; ad-hoc llama.cpp CLI overrides have highest priority.

#### `ONB-BEC5C7AA7DF9` — Use uv for project dependency and execution workflows

Manage dependencies with uv rather than direct pip, conda, or poetry commands, and run tests or project executions through uv run.

#### `ONB-B08B43994998` — Separate observed, declared, and unknown facts

Strictly separate observed, declared, and unknown facts.

#### `ONB-1C62845C8746` — Configuration states intent

Configuration describes intent; code implements it, never the other way around.

#### `ONB-55B57FDB7635` — Prefer small understandable changes

Prefer small, understandable changes.

## Local Rules

### Onboarding placement

#### `ONB-CF84E4C6F53C` — Canonicalize parameter names

Normalize parameter keys by removing leading dashes, replacing underscores with dashes, and mapping known shorthands or aliases to canonical long forms without leading dashes.

#### `ONB-984989C18F45` — Register new llama.cpp parameters

Add new llama.cpp parameters to PARAM_MAPPING in dispatcher.py when shorthand or spelling canonicalization is required.

#### `ONB-A289C8E1C079` — Dispatcher policy overrides managed client values

For parameters configured by the selected alias, Dispatcher policy overwrites client values; request parameters not managed by that alias pass through unchanged.

#### `ONB-011D1E449CE4` — Replace chat_template_kwargs as one policy value

When chat_template_kwargs is configured for an alias, replace the client object with the configured object rather than recursively merging it.

#### `ONB-42B7C96FD895` — Preserve and log request transformation

Preserve client intent before transformation and log the request resolution and effective values after policy enforcement and optional target remapping.

#### `ONB-31FE7C306176` — Do not duplicate prompt content in proxy telemetry

Exclude messages, prompt, and input from proxy parameter snapshots while retaining request control parameters.

#### `ONB-0683CD8DD4E6` — Clients must use the Dispatcher proxy

In ensemble operation, clients must connect to the Dispatcher proxy rather than directly to the internal llama.cpp server.

#### `ONB-E8D9548EEF1A` — Execution runs are immutable historical headers

Do not modify an execution_runs record after it has been written.

#### `ONB-A55465DE0A77` — Record a runtime model instance in every mode

Record exactly one serve_model_instance even in Single Profile Mode.

#### `ONB-4C56740CAE0C` — Validate FastAPI payloads

Validate external FastAPI endpoint payloads with Pydantic models or explicit validation.

#### `ONB-D8F736F7E29E` — Keep orchestration non-blocking

Do not use blocking calls such as time.sleep or subprocess.run in the orchestrator; start subprocesses and consume their logs asynchronously.

#### `ONB-7C2D6BDA8E2A` — Benchmark speed error is mandatory

metrics_bench.speed_error is mandatory.

#### `ONB-1E18D00C3698` — Perplexity error is mandatory when available

metrics_eval.perplexity_error is mandatory where available.

#### `ONB-21DD5242E6FD` — Repeated measurements require an error value

Do not record a measurement without an error value when repetitions are available.

#### `ONB-F1D506B24D9F` — Make new behavior previewable before full operation

Make new features testable first with --compile-only or /debug/preview where applicable.

#### `ONB-67CE0D860DA2` — Future schema evolution safeguards

For schema evolution, avoid destructive updates to existing measurement data, use PRAGMA user_version, and map migrations in a controlled manner in database_manager.py.

#### `ONB-1BE2684D2D39` — Store canonical DB keys and OpenAI JSON keys

Store parameter names in canonical dashed form in the database, but write OpenAI-compatible request JSON keys with underscores when forwarding to llama.cpp.

## Topics from ContextCanon Foundation

### Context authoring

When editing ContextCanon source, IDs, generated views, package resources, or Topics:

**Required**

- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/official-context.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/official-context.md)
- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/source-format.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/source-format.md)
- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/topics.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/topics.md)

### Context composition

When adding Sources or changing inherited Rules:

**Required**

- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/composition.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/composition.md)

### Harness adapters

When adding or changing a harness-specific entry file:

**Required**

- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/harnesses.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/harnesses.md)

## Local Topics

### Dispatcher operating reference

When operating or troubleshooting Dispatcher serve/bench/eval commands, debug endpoints, CLI overrides, database views, or detailed parameter naming, consult the README operating reference.

**Required**

- [`CONTEXT/references/5a5bf4f7-2cdd-4c35-90bb-4195d9759e5a/README.md`](CONTEXT/references/5a5bf4f7-2cdd-4c35-90bb-4195d9759e5a/README.md)
