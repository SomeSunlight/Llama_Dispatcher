# Topics

A Topic answers a practical question:

> When this kind of work is being done, what additional context should be read?

`CONTEXT.md` should stay small. It contains the Rules that are broadly relevant and a concise list of Topics. Each Topic describes when it matters and points to the deeper information needed for that work.

## Required and Optional information

A Topic contains two load intentions:

- **Required** — must be read when the Topic applies.
- **Optional** — useful for deeper understanding, troubleshooting, history, or unusual cases.

The source syntax also distinguishes target kind explicitly:

```markdown
### Logging

When changing logging, diagnostics, structured events, rotation, or troubleshooting:

Required:
- Resource: `docs/logging-contract.md`

Optional:
- Resource: `docs/logging-history.md`
```

A Gateway can navigate to another Node without composing it:

```markdown
Required:
- Context Node: `nodes/internal/framework-development`
```

The distinction matters. A model should not guess whether a target is mandatory, and the compiler should not guess whether a filesystem path means package material or another Node.

## Progressive disclosure can repeat

A required document should again put the most important information first. It may then point to more detailed material.

The result resembles a well-designed website: the first page gives orientation, important next steps are explicit, and deeper information remains one link away instead of being placed on the first page.

## Topics are also context integration

At first, a Topic may simply connect a task with a Markdown document. The mechanism is more general than that.

A Topic is a structured way to integrate additional information into the working context when it becomes relevant. Over time this may include:

- architecture and design documents,
- glossaries and domain terminology,
- coding patterns and example code,
- CSV files, schemas, tables, and other structured data,
- PDFs, images, and diagrams,
- skills and executable workflows,
- test fixtures and examples,
- operational experience, known pitfalls, and troubleshooting knowledge.

This is one of ContextCanon's larger opportunities: the same transparent mechanism can bring many kinds of project knowledge into an agent's context without making all of it permanently resident in the prompt.

## Source location and published location

Authors should keep information where it naturally belongs. A security document may remain `SECURITY.md`; architecture documentation may remain under `docs/`; a glossary may live beside the domain model.

When ContextCanon builds an Official Context Package, Resource targets are seeds for materialization under `CONTEXT/`. If a materialized Markdown file links to another local file, that target is recursively included so the package remains internally navigable. External links remain external.

The generated `CONTEXT.md` links to the package-local seed resources; deeper links continue from there. A generated `CONTEXT/README.md` explains the package directory itself when materialized resources exist, including why `references/` contains copies and where those copies originated.

## What decides that a Topic applies?

The compiler preserves Topic definitions deterministically. A harness or agent may decide that a natural-language task matches a Topic, because that decision can require semantic interpretation.

Once a Topic applies, however, Required versus Optional and Resource versus Context Node are explicit. The harness should not invent its own meaning for those targets.

## Current limitation

The compiler composes inherited Rules but keeps Topic navigation local to the consuming Node. Topic inheritance across Source package boundaries is deliberately deferred until external package location and materialization behavior is exercised end to end.
