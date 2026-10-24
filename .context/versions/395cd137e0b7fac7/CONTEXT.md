# Defaults — Official Context

> [!CAUTION]
> **GENERATED FILE — DO NOT EDIT.**
> This is the compact official entry for this Context Node.
>
> Edit [CONTEXT.src.md](CONTEXT.src.md) instead.

**Node:** Defaults  
**Context version:** `0.1.1-draft`

**Resulting imported Contexts:**

- **Llama Dispatcher** — `0.1.2-draft` — direct Parent Context — [inspect accepted carrier](../.context/versions/da37dc0cdf22a251/CONTEXT.md)

## Local Overview

<!-- contextcanon-placement-overview:start -->
- Model defaults under defaults/<model>.yaml own hardware-agnostic sampling defaults.
  <!-- cc:placement-overview id="ONB-C8CEAC1C48B7" -->

- defaults/engine-templates/ contains copy/fallback templates; the Dispatcher does not use those templates directly when an instance-specific engine exists.
  <!-- cc:placement-overview id="ONB-2BE347492067" -->
<!-- contextcanon-placement-overview:end -->

## How to use this context

Apply all Rules below to every task in this Node.

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
