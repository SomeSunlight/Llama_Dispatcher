# Dispatcher Code — Official Context

> [!CAUTION]
> **GENERATED FILE — DO NOT EDIT.**
> This is the compact official entry for this Context Node.
> Together with `CONTEXT/` it forms the human/agent-facing Official Context Package.
>
> Edit [CONTEXT.src.md](CONTEXT.src.md) instead.

**Node:** Dispatcher Code  
**Context version:** `0.1.2-draft`

**Resulting imported Contexts:**

- **Development Workflow** — `0.3.7-draft` — via Parent Context **Llama Dispatcher** — [inspect accepted carrier](../.context/versions/bf00e68a8ca381fd/CONTEXT.md)
- **GitHub** — `0.1.8-draft` — via Parent Context **Llama Dispatcher** — [inspect accepted carrier](../.context/versions/bf00e68a8ca381fd/CONTEXT.md)
- **Llama Dispatcher** — `0.1.3-draft` — direct Parent Context — [inspect accepted carrier](../.context/versions/bf00e68a8ca381fd/CONTEXT.md)

## Local Overview

<!-- contextcanon-placement-overview:start -->
- Dispatcher code compiles profiles and ensembles into llama.cpp parameters, starts llama.cpp, and collects metrics.
  <!-- cc:placement-overview id="ONB-9434DC39E0AE" -->

- The Dispatcher proxy exposes configured model aliases to clients, enforces centrally configured request parameters, and forwards effective requests to llama.cpp.
  <!-- cc:placement-overview id="ONB-52671788E89A" -->

- A proxy-only alias can target a real llama.cpp alias, rewrite the request model, and apply its own policy while sharing the same loaded model in VRAM.
  <!-- cc:placement-overview id="ONB-3AA7204F1FD7" -->

- chat_template_kwargs is injected by the proxy into requests and is not written to the llama.cpp INI.
  <!-- cc:placement-overview id="ONB-19C8A7718A41" -->

- Proxy handling distinguishes the client model alias, the resolved backing profile, and the effective target model sent to llama.cpp.
  <!-- cc:placement-overview id="ONB-73A34A2AD35A" -->

- Ensemble mode starts llama.cpp with the Dispatcher proxy; single-profile mode starts llama.cpp directly from one profile without router INI or proxy aliasing.
  <!-- cc:placement-overview id="ONB-1F0733D8FD42" -->

- An execution_run represents the main process.
  <!-- cc:placement-overview id="ONB-5E681FFCD08F" -->

- A serve_model_instance represents one effectively loaded model.
  <!-- cc:placement-overview id="ONB-C4C94C6CDECA" -->

- metrics_serve refers to both the historical execution run and the specific loaded-model origin.
  <!-- cc:placement-overview id="ONB-3EA477E1491E" -->

- The Dispatcher proxy is the observation point for original client request parameters; llama.cpp sees the already transformed request.
  <!-- cc:placement-overview id="ONB-1DCD56E83A83" -->
<!-- contextcanon-placement-overview:end -->

## Local State

<!-- contextcanon-placement-state:start -->
- The current runtime keeps compiled alias policy but not a full provenance tree for each value; it can identify dispatcher_policy plus alias/profile context, not the exact originating configuration layer.
  <!-- cc:placement-state id="ONB-CCF62CBAA356" -->

- The Dispatcher proxy defaults to port 8001.
  <!-- cc:placement-state id="ONB-C4C1FD4D00BE" -->

- The internal llama.cpp server defaults to port 8081.
  <!-- cc:placement-state id="ONB-C2F8E48BE5EA" -->

- The Dispatcher proxy currently provides no browser web UI.
  <!-- cc:placement-state id="ONB-9F3DE4C4C5D0" -->

- Open question: Are existing metrics databases upgraded additively, or is there no migration from older versions and the schema is built fresh?
  <!-- cc:placement-unresolved id="ONB-5D4DB3C8503C" -->

- Open question: What is the canonical proxy request telemetry table name: metrics_proxy_requests or proxy_requests?
  <!-- cc:placement-unresolved id="ONB-0C719E0D5E75" -->
<!-- contextcanon-placement-state:end -->

## How to use this context

Apply all Rules below to every task in this Node.

For the current task, evaluate each Topic condition. When one matches, read every **Required** target before continuing; read **Optional** targets only when useful.

## Rules from Development Workflow

### Recoverable planning

#### `CCW-010` — Back every change with an Issue

Before implementation, framework-context, or substantial documentation changes, ensure an Issue records why the change exists; it may be brief.

#### `CCW-001` — Plan a coherent change block before editing

Before starting a new coherent development block, record a short purpose and checklist in the project's durable planning surface; use `PLAN.md` when the project follows this workflow convention.

#### `CCW-002` — Checkpoint completed plan items immediately

When a listed step is actually complete, mark its `PLAN.md` checkbox `[x]` immediately rather than reconstructing completion at the end of a long session.

#### `CCW-003` — Keep recovery-critical knowledge in the repository

Put decisions, active constraints, accepted state, and next steps needed to resume work in repository documentation such as `PLAN.md`, `STATE.md`, or the project's equivalent rather than relying on chat history or model memory.

#### `CCW-007` — Resume recent explicit continuation without re-proving unchanged state

When the project owner resumes work after a short conversational interruption, explicitly says to continue, and reports no intervening repository changes, continue from the last established branch/PR state unless a repository operation gives evidence that it changed. Do not spend a new work cycle re-checking already established repository facts merely to prove that nothing happened.

### Transparent machine semantics

#### `CCW-012` — Mark machine-significant Markdown explicitly

When Markdown is also parsed, compiled, extracted, or otherwise given machine-significant meaning, every field or wording whose value affects machine semantics must live in an explicitly marked machine structure rather than being inferred from ordinary presentation prose. Keep that machine significance recognizable in rendered and review surfaces; rendering may style or summarize the control structure, but must not make the machine/human boundary indistinguishable.

#### `CCW-015` — Render repository-local Markdown links URL-safely

When writing Markdown links to repository-local files or directories, keep the real filesystem path as the semantic source of truth but percent-encode the Markdown link destination as a URI path instead of embedding raw spaces or Markdown/URL-sensitive path characters.

### Proportional verification

#### `CCW-004` — Batch related edits before expensive final verification

For one coherent correction block, make the related authoring/code changes and run proportionate focused checks first; do not repeat the project's most expensive generated-output, integration, packaging, or full verification cycle after every micro-edit.

#### `CCW-009` — Use owner-approved Fast Track blocks without weakening the final gate

When the project owner explicitly approves a coherent implementation scope and says intermediate product review is unnecessary, mark the Fast Track as active in the durable PLAN with its scope and exit condition, keep recovery checkpoints and focused verification inside bounded work blocks, and defer repeated PR-description polish, full CI, generated-output regeneration, and other review ceremony until the coherent review candidate. When the Fast Track ends, record that closure before returning to ordinary review cadence.

#### `CCW-005` — Require exact-head green verification at the merge gate, not the first review gate

A coherent development block may be presented for project-owner review while understood and disclosed CI failures or generated drift remain. After explicit project-owner approval and before merging, require the exact current head to pass the project's complete merge-gate verification, including zero generated drift when generated canonical output is part of the project contract.

#### `CCW-013` — Prefer editable installs for repeated owner testing

When actively testing an installable Python tool from a development checkout, prefer one editable install (`uv tool install --editable .`) and pull subsequent revisions with Git rather than reinstalling each version, when the environment supports it.

#### `CCW-014` — Expose development provenance without micro-bumping releases

When an executable tool is tested from a changing Git checkout, keep its release version stable until a real release/version boundary, but make runtime version output identify the current VCS state with the branch/ref when available, commit identity, and dirty state. Treat the commit identity as authoritative and the branch/ref as human orientation; release artifacts without checkout metadata still report the canonical release version.

### Human review gate

#### `CCW-011` — Expand change scope explicitly

Applicable Context constrains a task; it does not silently expand its writable scope.

#### `CCW-006` — Do not merge without explicit project-owner approval

Keep a review PR or equivalent change set open until the project owner explicitly approves the reviewed result.

### Accepted baseline

#### `CCW-008` — Close the post-merge baseline checkpoint before new development

After a reviewed change is successfully merged into the accepted branch, reconcile the durable repository state that records the accepted baseline before starting the next coherent development block. Record the merge outcome in `PLAN.md`, update `STATE.md` or equivalent current-state documentation, and refresh README/CHANGELOG or review-status wording made stale by the merge when applicable.

## Rules from GitHub

### Development infrastructure

#### `GH-001` — Use GitHub development objects

Manage workflow Issues, Pull Requests, reviews, checks/CI status, and merge state in the project's GitHub repository. Branches and commits remain ordinary Git objects; when a capable local harness is available, edit and test the local working tree directly rather than treating GitHub file APIs as a substitute filesystem.

## Rules from Llama Dispatcher

### Onboarding placement

#### `ONB-B97F676A25A3` — Keep configuration in its owning layer

Maintain each configuration fact once in the layer that owns it; do not put engine flags in profiles, model paths in engine files, or duplicate model sampling defaults. Shared instance configuration must not duplicate operating-system-specific runtime paths; launchers should supply machine-local binary and model roots explicitly, with environment variables only as documented optional fallbacks. Backend-specific process environment such as GPU-selection variables belongs in the engine configuration and is applied by Dispatcher when it launches llama.cpp rather than being required in the caller's shell. Instance repositories under `instances/<name>/` are user-owned independent Git repositories: Dispatcher core ignores their contents and must not register or manage them as Git submodules.

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

## Topics from Development Workflow

### Executing a development block

When planning, resuming, checkpointing, reviewing, testing, finalizing, merging, or closing the accepted baseline for a coherent development block:

**Required**

- [`CONTEXT/references/ne68be75ed7bf392/docs/change-workflow.md`](CONTEXT/references/ne68be75ed7bf392/docs/change-workflow.md)

### Implementing executable version identity

When adding or changing `--version`, package version lookup, or Git checkout provenance for an executable Python tool:

**Required**

- [`CONTEXT/references/ne68be75ed7bf392/docs/version-provenance-python.md`](CONTEXT/references/ne68be75ed7bf392/docs/version-provenance-python.md)

## Local Topics

### Dispatcher operating reference

When operating or troubleshooting Dispatcher serve/bench/eval commands, debug endpoints, CLI overrides, database views, or detailed parameter naming, consult the README operating reference.

**Required**

- [`CONTEXT/references/n7a3bd8b0815855d/README.md`](CONTEXT/references/n7a3bd8b0815855d/README.md)
