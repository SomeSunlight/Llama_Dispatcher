# Dispatcher Code — Local Context Source
<!-- ctx:node id="5a5bf4f7-2cdd-4c35-90bb-4195d9759e5a" name="Dispatcher Code" version="0.1.1-draft" -->

<!-- contextcanon:format Node
Format: Node metadata follows the # title: ctx:node id="..." name="..." version="...". Preserve existing identity.
Details: CONTEXT-format.md
-->

<!-- contextcanon:source-help:intro:start -->
Edit this local Context source; ContextCanon generates CONTEXT.md from it.
Some sections use a strict syntax. The comments below show the expected format.
New Rules, Topics and Resources receive IDs automatically during build; preserve existing IDs.
See [the source format guide](CONTEXT-format.md) for examples and editing instructions.
<!-- contextcanon:source-help:intro:end -->

## Context Imports

<!-- contextcanon:format Context Imports
Format: - [Name](location) — `version` — `relationship=parent|reference`; optional indented Why:, then ctx:source metadata. Preserve exact pins; use source list/adopt/update for package identity.
Details: CONTEXT-format.md
-->

<!-- contextcanon-placement-parent:start -->
- [Llama Dispatcher](..) — `0.1.2-draft` — `relationship=parent`
  <!-- ctx:source id="e3e6391b-6eb7-4b2a-ba1d-f969a65bbf08" version="0.1.2-draft" normalized-digest="ef5444bb73d49f4914fe680cedc8ad0679da599ed4c7ef68ca910be9969620fa" package-digest="21c98f31b5b1bb1c552f6a1c1a1cdeb853ad2f899ddb37db6e66b0aa678bcb4f" -->
<!-- contextcanon-placement-parent:end -->

## Local Overview

<!-- contextcanon:format Local Overview
Format: Ordinary Markdown orientation, local to this Node. Any existing placement identity follows its paragraph/item; do not change it.
Details: CONTEXT-format.md
-->

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

<!-- contextcanon:format Local State
Format: Ordinary Markdown describing the current local situation. Any existing placement identity follows its paragraph/item; preserve it.
Details: CONTEXT-format.md
-->

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

## Local Rules

<!-- contextcanon:format Local Rules
Format: ### Group, then - **Title:** Statement, then indented Why: Rationale. build adds a missing ctx:rule ID after the entry; preserve existing IDs.
Details: CONTEXT-format.md
-->

<!-- contextcanon-placement-rules:start -->
### Onboarding placement

- **Canonicalize parameter names:** Normalize parameter keys by removing leading dashes, replacing underscores with dashes, and mapping known shorthands or aliases to canonical long forms without leading dashes.
  Why: One canonical representation prevents silent mismatches across defaults, profiles, ensembles, CLI input, and telemetry.
  <!-- ctx:rule id="ONB-CF84E4C6F53C" -->

- **Register new llama.cpp parameters:** Add new llama.cpp parameters to PARAM_MAPPING in dispatcher.py when shorthand or spelling canonicalization is required.
  Why: The mapping is the explicit source for translating accepted aliases into canonical parameter names.
  <!-- ctx:rule id="ONB-984989C18F45" -->

- **Dispatcher policy overrides managed client values:** For parameters configured by the selected alias, Dispatcher policy overwrites client values; request parameters not managed by that alias pass through unchanged.
  Why: Central configuration must be authoritative without blocking unrelated OpenAI-compatible or future llama.cpp request fields.
  <!-- ctx:rule id="ONB-A289C8E1C079" -->

- **Replace chat_template_kwargs as one policy value:** When chat_template_kwargs is configured for an alias, replace the client object with the configured object rather than recursively merging it.
  Why: The runtime treats chat_template_kwargs as one Dispatcher policy value.
  <!-- ctx:rule id="ONB-011D1E449CE4" -->

- **Preserve and log request transformation:** Preserve client intent before transformation and log the request resolution and effective values after policy enforcement and optional target remapping.
  Why: Telemetry must show both what the client requested and what llama.cpp actually received.
  <!-- ctx:rule id="ONB-42B7C96FD895" -->

- **Do not duplicate prompt content in proxy telemetry:** Exclude messages, prompt, and input from proxy parameter snapshots while retaining request control parameters.
  Why: Telemetry should capture request controls without duplicating conversation or prompt content.
  <!-- ctx:rule id="ONB-31FE7C306176" -->

- **Clients must use the Dispatcher proxy:** In ensemble operation, clients must connect to the Dispatcher proxy rather than directly to the internal llama.cpp server.
  Why: Direct llama.cpp access bypasses virtual aliases, Dispatcher parameter injection, alias remapping, and proxy telemetry.
  <!-- ctx:rule id="ONB-0683CD8DD4E6" -->

- **Execution runs are immutable historical headers:** Do not modify an execution_runs record after it has been written.
  Why: execution_runs is the historical run header.
  <!-- ctx:rule id="ONB-E8D9548EEF1A" -->

- **Record a runtime model instance in every mode:** Record exactly one serve_model_instance even in Single Profile Mode.
  Why: Evaluations remain homogeneous between single-profile and ensemble modes.
  <!-- ctx:rule id="ONB-A55465DE0A77" -->

- **Validate FastAPI payloads:** Validate external FastAPI endpoint payloads with Pydantic models or explicit validation.
  Why: External request data must be checked before it enters orchestration logic.
  <!-- ctx:rule id="ONB-4C56740CAE0C" -->

- **Keep orchestration non-blocking:** Do not use blocking calls such as time.sleep or subprocess.run in the orchestrator; start subprocesses and consume their logs asynchronously.
  Why: Blocking calls would stall the asynchronous service.
  <!-- ctx:rule id="ONB-D8F736F7E29E" -->

- **Benchmark speed error is mandatory:** metrics_bench.speed_error is mandatory.
  Why: Benchmark measurements should carry their uncertainty.
  <!-- ctx:rule id="ONB-7C2D6BDA8E2A" -->

- **Perplexity error is mandatory when available:** metrics_eval.perplexity_error is mandatory where available.
  Why: Evaluation measurements should carry their uncertainty when it can be computed.
  <!-- ctx:rule id="ONB-1E18D00C3698" -->

- **Repeated measurements require an error value:** Do not record a measurement without an error value when repetitions are available.
  Why: Repeated measurements provide the information needed to report uncertainty.
  <!-- ctx:rule id="ONB-21DD5242E6FD" -->

- **Make new behavior previewable before full operation:** Make new features testable first with --compile-only or /debug/preview where applicable.
  Why: Configuration and request transformations should be inspectable before a full runtime path is exercised.
  <!-- ctx:rule id="ONB-F1D506B24D9F" -->

- **Future schema evolution safeguards:** For schema evolution, avoid destructive updates to existing measurement data, use PRAGMA user_version, and map migrations in a controlled manner in database_manager.py.
  Why: Measurement history must remain trustworthy across future schema changes.
  <!-- ctx:rule id="ONB-67CE0D860DA2" -->

- **Store canonical DB keys and OpenAI JSON keys:** Store parameter names in canonical dashed form in the database, but write OpenAI-compatible request JSON keys with underscores when forwarding to llama.cpp.
  Why: Internal canonicalization and the external OpenAI-compatible API use different naming conventions.
  <!-- ctx:rule id="ONB-1BE2684D2D39" -->
<!-- contextcanon-placement-rules:end -->

## Local Topics

<!-- contextcanon:format Local Topics
Format: ### Title, condition text, Required: and/or Optional:, then - Resource: `path` or - Context Node: `node-path`. Resource may have indented Why:. build adds missing Topic/Resource IDs after their entries; preserve existing IDs.
Details: CONTEXT-format.md
-->

<!-- contextcanon-placement-topics:start -->
### Dispatcher operating reference

When operating or troubleshooting Dispatcher serve/bench/eval commands, debug endpoints, CLI overrides, database views, or detailed parameter naming, consult the README operating reference.

Required:
- Resource: `../README.md`
  <!-- ctx:resource id="RESOURCE-170CDF801AB6" -->

<!-- ctx:topic id="ONB-5CDAC841D567" -->
<!-- contextcanon-placement-topics:end -->
