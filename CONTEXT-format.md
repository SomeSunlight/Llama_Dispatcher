<!-- contextcanon:generated-source-format -->
# Editing CONTEXT.src.md

`CONTEXT.src.md` is the editable local source for one Context Node. ContextCanon compiles it and its accepted imports into `CONTEXT.md` and, when needed, the deeper `CONTEXT/` package. Read `CONTEXT.md` to work; edit `CONTEXT.src.md` to change what applies here.

Some headings and lines have a strict machine meaning. Each section's `contextcanon:format` comment gives its expected form. Those comments and the source introduction are authoring help only: they never become Rules, Topic conditions, Overview, State or Plan in the generated context.

## Normal editing and automatic migration

1. Write or edit the local source. Use the Rule/Topic examples below; omit IDs for genuinely new Rules, Topics and Resource targets.
2. Run `contextcanon build --all .` at the intended repository/project root (or `contextcanon build .` for one Node).
3. Run `contextcanon check --all .`.

Build installs/refreshes these format comments and this local guide, puts Context Imports first, makes legacy import relationship defaults explicit, and moves historical State/Plan placement markers after the entry they identify. It allocates missing Rule/Topic/Resource IDs once and retains them on later builds. Existing identity and exact accepted package pins are preserved. Check is read-only.

Build does not invent a Rule's statement, a Topic's condition, an import's identity, or the meaning of malformed text. Fix syntax errors using the file/line, expected example and guide named in the error. A source migration is validated before writing. Moving help does not accept newer upstream packages; Parent/Reference updates and propagation still require their normal review.

## Node header

```markdown
# My Project
<!-- ctx:node id="existing-node-id" name="My Project" version="0.1.0" -->
```

Keep existing Node identity. Onboarding assigns it to a new Node; ordinary build does not guess a missing or corrupt Node identity. The metadata follows the title. Do not copy a different project's ID to create a new project. Node versions describe publications; build may apply the usual minimum patch bump when published package bytes change.

## Context Imports

This is the first section so Parents and References are immediately visible.

```markdown
## Context Imports

- [Development Workflow](../workflow/) — `1.2.0` — `relationship=parent`
  <!-- ctx:source id="the-provider-node-id" version="1.2.0" -->
- [Historical Material](../history/) — `1.0.0` — `relationship=reference`
  Why: Background for interpreting old payloads.
  <!-- ctx:source id="the-history-node-id" version="1.0.0" -->
```

Parent Rules apply here and Parent Topics/Resources compose transitively. Reference Rules do not apply; its informational Topics/Resources stay local. Directory nesting creates neither relationship. Import order is not precedence.

Use `contextcanon source list` to inspect identities, `contextcanon source adopt` to adopt an exact local package, and `contextcanon source update "Name"` to review an update. Existing immutable imports also pin `normalized-digest` and `package-digest` together. Preserve the complete metadata (including transport fields when present); it is not a place to invent provider IDs or hashes. Legacy Sources/missing relationship markers mean Parent and build makes that existing meaning explicit.

## Local Overview, Local State and Local Plan

These sections contain ordinary Markdown. Overview gives short orientation, State records the current local situation, and Plan records intended work. They stay local to this Node.

```markdown
## Local State

- The migration is in progress.
  <!-- cc:placement-state id="existing-placement-id" -->
```

An onboarding placement marker identifies the preceding item; preserve it. New ordinary local prose needs no invented placement ID. All identity/provenance comments follow the content they identify.

## Add a Local Rule

```markdown
## Local Rules

### Security

- **Keep secrets out of Git:** Credentials must stay outside version control.
  Why: Version control is not a secret store.
```

Use the literal `- **Title:** Statement` form and an indented, non-empty `Why:`. The statement and rationale each occupy one line. Build adds a trailing `ctx:rule` identity to a new Rule. Keep that ID when editing or moving an existing Rule. A malformed or duplicated existing ID is an error, not permission to replace its identity.

You can also use `contextcanon author rule . --group Security --title "Keep secrets out of Git" --statement "Credentials must stay outside version control." --why "Version control is not a secret store."` to add an identified Rule immediately.

## Add a Local Topic and Resources

```markdown
## Local Topics

### Payload migration

When comparing legacy and current payload shapes:

Required:
- Resource: `samples/current.jsonc`
  Why: Version 6 - valid current example.
- Resource: `samples/legacy.json`
  Why: Obsolete payload retained for migration comparisons.

Optional:
- Context Node: `../architecture`
```

A Topic needs a `###` title, non-empty condition and at least one target under literal `Required:` or `Optional:`. Resource and Context Node paths must be enclosed in backticks. Resource files must exist and be valid package material. Relative paths refer to this Node; spaces in file names are allowed.

Build adds a `ctx:topic` ID at the end of a new Topic and a `ctx:resource` ID after each new Resource entry. Several uses of the same Resource in one Node share its stable Resource ID; each use can have its own optional `Why:`. Keep existing IDs when editing or moving files.

Resource `Why:` is optional, indented, non-empty and one line. The Resource ID comment may appear immediately before or after Why. Words such as VALID or OBSOLETE are explanations: they never validate a payload or change Required/Optional. These trailing forms are invalid:

```markdown
- Resource: samples/current.jsonc (Version 6 - VALID)
- Resource: `samples/current.jsonc` (Version 6 - VALID)
```

Move that explanation to an indented Why line. `Why:` currently belongs to Resource targets, not Context Node navigation targets.

You can also use `contextcanon author topic . --title "Payload migration" --condition "When comparing payload shapes:" --required-resource samples/current.jsonc` to add an identified Topic immediately.

## Changes to inherited Rules

```markdown
## Changes

### Remove

- `Company Security / SEC-014` — Legacy audit header
  Why: This project uses the replacement audit protocol.
  <!-- ctx:change op="remove" source-id="the-origin-node-id" rule-id="SEC-014" -->

### Override

- `Python Development / PY-007` — Supported Python version
  New rule: Production code must support Python 3.12 or newer.
  Why: This project has standardized on that runtime.
  <!-- ctx:change op="override" source-id="the-origin-node-id" rule-id="PY-007" -->
```

Changes bind the actual inherited origin Node ID plus Rule ID. ContextCanon cannot guess those identities; inspect the accepted Parent. Remove needs Why; Override also needs New rule. Metadata follows the complete entry. Changing presentation order never resolves a conflict between Parents.

## What is maintained automatically?

Build refreshes only marked authoring help/layout and allocates missing IDs for valid new entries. Existing authored meaning, IDs, import kind, version/pins and managed onboarding ownership remain intact. Frozen accepted packages are never rewritten. This guide is a compiler-owned aid beside the source, not exported knowledge. Do not edit it; put your project's knowledge in natural Resources and refer to them through Topics.
