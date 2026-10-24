# Official Context

The **Official Context** is the complete compiled context published by a node and used by that node itself.

It answers one question:

> What context officially applies here?

A child node may compose exactly that same published semantic result. There is no separate hidden governance for the parent and a different governance exported to descendants.

## Concrete package layout

Every node has a generated `CONTEXT.md` entry. Deeper package material exists only when the node actually needs it:

```text
CONTEXT.md              compact official entry; always present
CONTEXT/                optional deeper compiled/package-local material
├── README.md           generated orientation for this package directory
├── references/
├── topics/
├── glossaries/         future
├── examples/           future
├── skills/             future
└── ...
```

A tiny node with no materialized resources may legitimately have no `CONTEXT/` directory at all. When `CONTEXT/` exists, its `README.md` is compiler-generated package orientation: it explains that the directory is generated, where to start, and why materialized `references/` are package copies rather than another authoring surface.

`.context/` is different. It contains compiler bookkeeping, accepted Source/Parent snapshots, provenance, hashes, package metadata, and other machine state. Humans normally do not browse it directly, but the compact composition summary at the top of `CONTEXT.md` links to the exact accepted local carrier packages when provenance needs inspection.

## Effective composition must be visible

When a Node composes Parent Context Nodes or reusable Sources, `CONTEXT.md` names the direct Parents and lists the resulting effective imported Context Nodes with their accepted versions. Transitive imports are flattened from authenticated immutable package metadata, so a deep Node can explain why a rule applies without dereferencing live ancestors or the network. Each list item links to the exact direct accepted carrier package (or the local development Source) that supplied that context. Unrelated sibling Nodes never appear merely because they share filesystem ancestry.

The list is deliberately compact provenance, not a second rule surface: the actual effective Rules and Topics remain grouped below by origin. Exact low-level machine state and digests remain available in `.context/context.yaml` and package manifests.

## Why not put everything in `CONTEXT.md`?

Because completeness and prompt size are different concerns.

`CONTEXT.md` should contain the small amount of context that is broadly useful plus a precise Topic map. When a Topic applies, Required material is loaded from the package or another explicitly named target. Optional material remains available if more depth is useful.

This lets a package be complete without forcing every document, glossary, example, and historical note into every LLM turn.

## Local Overview: what is this place?

A Node may begin its compact entry with a short `Local Overview`. It answers the orientation questions that are neither Rules nor conditional deep context: what this Node represents, why it exists, and what background helps a human or agent understand the surrounding problem.

A Local Overview is deliberately **not inherited governance**. Child Nodes do not receive a Source's introductory prose merely because they compose its Rules. The Overview remains part of the exact published `CONTEXT.md`, so changing it changes the package bytes and `package_digest`, but not the Node's normalized semantic digest.

This distinction lets a Node explain itself without pretending every explanatory sentence is a Rule. The Overview should remain short; deeper explanation belongs behind Topics.

## Small gateways matter

A valid Context Node can be very small. ContextCanon Gateway at this repository root has no Sources and no Rules, but it is no longer empty orientation: its Overview briefly explains why ContextCanon exists, while two Topics route relevant work deeper.

- onboarding an existing project loads the user-facing onboarding guide as a Required Resource;
- ContextCanon framework-development work navigates to the deeper Framework Development Node.

The Gateway therefore has a small `CONTEXT/` directory for the onboarding guide, but that guide is not loaded for unrelated work.

This is not a special bootstrap mode. It is an ordinary Context Node demonstrating two complementary ideas at once: enough always-read orientation to understand where you are, and progressive disclosure for everything that does not belong in every task.

## Natural source locations, self-contained published package

Authors should not reorganize a repository merely to satisfy ContextCanon. Existing material may remain in natural locations such as `SECURITY.md`, `docs/architecture.md`, `schemas/domain.csv`, or `examples/client.py`.

During compilation, ContextCanon materializes resources that belong inside a published package under `CONTEXT/references/` while preserving their repository-relative directory structure. Local Markdown links are followed recursively into the materialization closure, so links between copied resources continue to resolve from the same relative layout. External links remain external.

The generated copy is intentional package content, not another maintenance surface. This lets an immutable package remain useful after it has been separated from the original authoring repository.

## What belongs in `CONTEXT.md`?

The entry should prioritize a concise Local Overview when orientation is useful, broadly required Rules, Topics with clear conditions, explicit Required and Optional targets, and stable visible IDs for published elements that descendants may reference.

It should expose only the small composition audit needed to understand what applies — imported Node names, accepted versions, relation/provenance, and local carrier links — rather than provenance event logs, dependency internals, or every resource in the package. Nor should an Overview become a hidden preload document: if material matters only for a recognizable task, it belongs behind a Topic.

## Generated output

`CONTEXT.md` and, when present, `CONTEXT/` are generated and should not be edited directly. Human changes belong in `CONTEXT.src.md` and in referenced source material.


## Node-directory README doorplate

A Context Node directory may have a project-owned `README.md`; ContextCanon never overwrites or adopts it. When no README exists, generated output may add a tiny marker-owned `README.md` doorplate so GitHub and filesystem browsers explain the special files immediately. It links to `CONTEXT.md` as Official Context, `CONTEXT.src.md` as local authoring truth, and the ContextCanon project documentation. It deliberately contains no duplicate project Rules, State, or other canonical meaning. If a project later replaces the generated doorplate with its own README (removing the ownership marker), ContextCanon stops managing that path.
