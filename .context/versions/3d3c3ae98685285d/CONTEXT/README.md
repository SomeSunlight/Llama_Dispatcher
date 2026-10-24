# Generated Context package resources

> [!CAUTION]
> **GENERATED DIRECTORY — DO NOT EDIT THESE FILES.**
> Start with [`../CONTEXT.md`](../CONTEXT.md), the compact Official Context entry for this Node.

This `CONTEXT/` directory exists because the Node has deeper Topic resources that should be available **without loading them into every task**.

## Why `references/` may look like duplicate documentation

`references/` contains exact materialized copies of effective Topic resources. The first path component after `CONTEXT/references/` is the stable origin Node identity (or a deterministic hash when that identity is not path-safe); the remaining path preserves repository-relative source location. This namespace lets inherited Topic resources from independent packages coexist without Source-order precedence.

For example:

```text
nodes/internal/framework-development/docs/architecture.md
        ↓ deterministic materialization
CONTEXT/references/<origin-node-id>/nodes/internal/framework-development/docs/architecture.md
```

The first path is the authored source. The second path is generated package content and is **not another maintenance surface**.

The copy is intentional: it makes the Official Context Package self-contained, so the package can later be published or consumed without needing the original authoring repository layout. In a standalone package the original source path may no longer exist; the materialized copy is what preserves the reviewed resource bytes.

When an exact Markdown Resource links back to its owning Node's generated `CONTEXT.md`, ContextCanon materializes a tiny generated bridge at that linked location instead of copying whatever generated output happened to be on disk. The bridge points to this package's top-level Official Context. This keeps the Resource's exact bytes and link shape usable without making package identity depend on a previous build.

`contextcanon build` refreshes generated package files. `contextcanon check` reports drift when committed generated output no longer matches the authored source and compiler.
