# Llama Dispatcher — Local Context Source
<!-- ctx:node id="e3e6391b-6eb7-4b2a-ba1d-f969a65bbf08" name="Llama Dispatcher" version="0.1.0-draft" -->

## Local Overview

<!-- contextcanon-placement-overview:start -->
<!-- cc:placement-overview id="ONB-40902CFCE27F" -->
- Llama Dispatcher is an asynchronous orchestrator and OpenAI-compatible proxy for llama.cpp.
<!-- contextcanon-placement-overview:end -->

## Sources

<!-- contextcanon-placement-sources:start -->
- [ContextCanon Foundation](contextcanon.yaml) — `0.2.0-draft`
  Why: Reuse the same proven workflow as for context-canon itself, which is a similar LLM-assisted project.
  <!-- ctx:source id="4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001" version="0.2.0-draft" normalized-digest="62a1bc6b9fffa838fbdf2b434f9fd2057de38fb6017734115ae2fb3ed56c100e" package-digest="7da87dcee0e716db35b62935f9980d27dd06986af93e61d4d28eb59783a58b8c" -->
<!-- contextcanon-placement-sources:end -->

## Local Rules

<!-- contextcanon-placement-rules:start -->
### Onboarding placement

- **Keep configuration in its owning layer:** Maintain each configuration fact once in the layer that owns it; do not put engine flags in profiles, model paths in engine files, or duplicate model sampling defaults. Shared instance configuration must not duplicate operating-system-specific runtime paths; launchers should supply machine-local binary and model roots explicitly, with environment variables only as documented optional fallbacks. Backend-specific process environment such as GPU-selection variables belongs in the engine configuration and is applied by Dispatcher when it launches llama.cpp rather than being required in the caller's shell.
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
