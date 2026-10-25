# GitHub — Official Context

> [!CAUTION]
> **GENERATED FILE — DO NOT EDIT.**
> This is the compact official entry for this Context Node.
> Together with `CONTEXT/` it forms the human/agent-facing Official Context Package.
>
> Edit [CONTEXT.src.md](CONTEXT.src.md) instead.

**Node:** GitHub  
**Context version:** `0.1.8-draft`

**Resulting imported Contexts:**

- **Development Workflow** — `0.3.7-draft` — direct Parent Context — [inspect accepted carrier](../development-workflow/CONTEXT.md)

## Local Overview

Concrete provider for projects that use ordinary GitHub infrastructure to implement the Development Workflow. The inherited workflow keeps the familiar Issue, branch, Pull Request, review, checks and merge lifecycle; this Node makes those terms mean the corresponding objects in the project's GitHub repository.

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

## Local Rules

### Development infrastructure

#### `GH-001` — Use GitHub development objects

Manage workflow Issues, Pull Requests, reviews, checks/CI status, and merge state in the project's GitHub repository. Branches and commits remain ordinary Git objects; when a capable local harness is available, edit and test the local working tree directly rather than treating GitHub file APIs as a substitute filesystem.

## Topics from Development Workflow

### Executing a development block

When planning, resuming, checkpointing, reviewing, testing, finalizing, merging, or closing the accepted baseline for a coherent development block:

**Required**

- [`CONTEXT/references/ne68be75ed7bf392/docs/change-workflow.md`](CONTEXT/references/ne68be75ed7bf392/docs/change-workflow.md)

### Implementing executable version identity

When adding or changing `--version`, package version lookup, or Git checkout provenance for an executable Python tool:

**Required**

- [`CONTEXT/references/ne68be75ed7bf392/docs/version-provenance-python.md`](CONTEXT/references/ne68be75ed7bf392/docs/version-provenance-python.md)
