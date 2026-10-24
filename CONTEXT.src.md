# Llama Dispatcher — Local Context Source
<!-- ctx:node id="e3e6391b-6eb7-4b2a-ba1d-f969a65bbf08" name="Llama Dispatcher" version="0.1.2-draft" -->

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

<!-- contextcanon-placement-sources:start -->
<!-- contextcanon-placement-sources:end -->

## Local Overview

<!-- contextcanon:format Local Overview
Format: Ordinary Markdown orientation, local to this Node. Any existing placement identity follows its paragraph/item; do not change it.
Details: CONTEXT-format.md
-->

<!-- contextcanon-placement-overview:start -->
- Llama Dispatcher is an asynchronous orchestrator and OpenAI-compatible proxy for llama.cpp.
  <!-- cc:placement-overview id="ONB-40902CFCE27F" -->
<!-- contextcanon-placement-overview:end -->

## Local Rules

<!-- contextcanon:format Local Rules
Format: ### Group, then - **Title:** Statement, then indented Why: Rationale. build adds a missing ctx:rule ID after the entry; preserve existing IDs.
Details: CONTEXT-format.md
-->

<!-- contextcanon-placement-rules:start -->
### Onboarding placement

- **Keep configuration in its owning layer:** Maintain each configuration fact once in the layer that owns it; do not put engine flags in profiles, model paths in engine files, or duplicate model sampling defaults. Shared instance configuration must not duplicate operating-system-specific runtime paths; launchers should supply machine-local binary and model roots explicitly, with environment variables only as documented optional fallbacks. Backend-specific process environment such as GPU-selection variables belongs in the engine configuration and is applied by Dispatcher when it launches llama.cpp rather than being required in the caller's shell. Instance repositories under `instances/<name>/` are user-owned independent Git repositories: Dispatcher core ignores their contents and must not register or manage them as Git submodules.
  Why: Clear ownership prevents conflicting configuration, repeated maintenance, and hidden ambient startup state.
  <!-- ctx:rule id="ONB-B97F676A25A3" -->

- **Configuration precedence:** Configuration is deep-merged in this order: model defaults, instance engine defaults, profile, ensemble model entry; ad-hoc llama.cpp CLI overrides have highest priority.
  Why: A deterministic precedence order makes the effective llama.cpp configuration predictable.
  <!-- ctx:rule id="ONB-D855038AE157" -->

- **Use uv for project dependency and execution workflows:** Manage dependencies with uv rather than direct pip, conda, or poetry commands, and run tests or project executions through uv run.
  Why: The project uses one dependency and execution workflow to keep environments consistent.
  <!-- ctx:rule id="ONB-BEC5C7AA7DF9" -->

- **Separate observed, declared, and unknown facts:** Strictly separate observed, declared, and unknown facts.
  Why: Implementation and documentation should not turn assumptions into asserted project facts.
  <!-- ctx:rule id="ONB-B08B43994998" -->

- **Configuration states intent:** Configuration describes intent; code implements it, never the other way around.
  Why: Runtime transformation should follow explicit configuration instead of hidden code-side policy.
  <!-- ctx:rule id="ONB-1C62845C8746" -->

- **Prefer small understandable changes:** Prefer small, understandable changes.
  Why: Small coherent changes are easier to review, test, and reason about.
  <!-- ctx:rule id="ONB-55B57FDB7635" -->
<!-- contextcanon-placement-rules:end -->
