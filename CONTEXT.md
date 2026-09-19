# Llama Dispatcher — Official Context

> [!CAUTION]
> **GENERATED FILE — DO NOT EDIT.**
> This is the compact official entry for this Context Node.
> Together with `CONTEXT/` it forms the human/agent-facing Official Context Package.
>
> Edit [CONTEXT.src.md](CONTEXT.src.md) instead.

**Node:** Llama Dispatcher  
**Context version:** `0.1.1-draft`

**Resulting imported Contexts:**

- **ContextCanon Foundation** — `0.2.0-draft` — direct Source — Why: Reuse the same proven workflow as for context-canon itself, which is a similar LLM-assisted project. — [inspect accepted carrier](.context/sources/7da87dcee0e716db35b62935f9980d27dd06986af93e61d4d28eb59783a58b8c/CONTEXT.md)

## Local Overview

<!-- contextcanon-placement-overview:start -->
<!-- cc:placement-overview id="ONB-40902CFCE27F" -->
- Llama Dispatcher is an asynchronous orchestrator and OpenAI-compatible proxy for llama.cpp.
<!-- contextcanon-placement-overview:end -->

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

## Local Rules

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
