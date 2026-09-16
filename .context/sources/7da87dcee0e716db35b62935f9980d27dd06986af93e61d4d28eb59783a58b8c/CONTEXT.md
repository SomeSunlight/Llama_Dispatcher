# ContextCanon Foundation — Official Context

> [!CAUTION]
> **GENERATED FILE — DO NOT EDIT.**
> This is the compact official entry for this Context Node.
> Together with `CONTEXT/` it forms the human/agent-facing Official Context Package.
>
> Edit [CONTEXT.src.md](CONTEXT.src.md) instead.

**Node:** ContextCanon Foundation  
**Context version:** `0.2.0-draft`

## How to use this context

Apply all Rules below to every task in this Node.

For the current task, evaluate each Topic condition. When one matches, read every **Required** target before continuing; read **Optional** targets only when useful.

## Local Rules

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

## Local Topics

### Context authoring

When editing ContextCanon source, IDs, generated views, package resources, or Topics:

**Required**

- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/source-format.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/source-format.md)
- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/official-context.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/official-context.md)
- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/topics.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/topics.md)

### Context composition

When adding Sources or changing inherited Rules:

**Required**

- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/composition.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/composition.md)

### Harness adapters

When adding or changing a harness-specific entry file:

**Required**

- [`CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/harnesses.md`](CONTEXT/references/4ca9d92c-59f2-4b1f-b7b3-0e2ff91fd001/nodes/library/foundation/docs/harnesses.md)
