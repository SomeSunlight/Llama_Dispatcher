# Source Format

`CONTEXT.src.md` is the human-editable source of truth for one Context Node. The compiler never needs to reconstruct authored information from generated `CONTEXT.md`, `.context/context.yaml`, or `.context/package.json`.

The format is deliberately constrained Markdown: readable without special tooling, but structured enough for deterministic parsing. Canonical local sections are named `Local Overview`, `Local State`, `Local Plan`, `Local Rules`, and `Local Topics`; `Local` means authored in this Node, not an implicit override. The relationship heading is `Parent Context Node`. Compiler 0.5 continues to accept the older `Overview`/`State`/`Plan`/`Rules`/`Topics`/`Parent` headings as migration aliases, but a source must not contain both forms for the same section.

## Node header

A source normally begins with a human-readable Markdown H1 followed by explicitly machine-marked Node metadata:

```markdown
# Example Project
<!-- ctx:node id="<stable-node-id>" name="Example Project" version="0.1.0" -->
```

The `ctx:node` comment is authoritative for machine-significant Node metadata. `id`, `name`, and `version` are required. The Markdown H1 is ordinary human presentation: ContextCanon does not derive Node identity or the canonical Node name from its wording, and changing only the H1 does not change canonical semantics. A project may keep the descriptive `— Local Context Source` suffix as presentation if useful; it is not syntax.

This is a general authoring boundary: machine-significant ContextCanon fields are carried in visibly marked `ctx:*` metadata or other explicitly specified control structures, not hidden in presentation wording that merely looks like ordinary Markdown.

The stable ID is independent of the Node's directory path or display name. A root Node may additionally declare generated harness adapters, for example `adapters="agents,goose"`.

## Local Overview

`## Local Overview` is an optional short orientation block for the Node itself: what this place is, why it exists, and what background helps a human or agent understand it before applying Rules or following Topics.

```markdown
## Local Overview

This service owns customer-facing notification delivery. It exists separately from the billing service because delivery retries, provider failover, and message templates have their own operational lifecycle.
```

Overview text is copied into the generated `CONTEXT.md` near the top of the compact entry. It is **local presentation and orientation**, not inherited governance: using a Node as a Source does not copy its Overview into a child Node.

Changing only an Overview therefore changes the exact published package bytes and `package_digest`, but does not change `normalized_digest`. Rules, Changes, Sources, and Topics remain the semantic composition boundary.

Keep an Overview compact. It is always-read entry context, so deeper explanations belong behind Topics rather than turning the Overview into another preload document. In particular, use Topics for material that needs to be packaged as deeper Resources instead of relying on repository-local links from an Overview.

## Parent Context Node

A Context Node may have zero, one, or several semantic Parents. Parents are explicit accepted relationships; filesystem nesting creates none. Parent order has no precedence.

Each Parent is an exact immutable package pin:

```markdown
## Parent Context Node

- [Project Context](../) — `0.1.0`
  <!-- ctx:parent id="<stable-parent-node-id>" version="0.1.0" normalized-digest="<sha256>" package-digest="<sha256>" -->
```

The visible label must match the canonical Node name of the accepted Parent package; the link target records where a newer Parent candidate may later be discovered. Stable ID/version/digests remain the technical identity. `contextcanon check` reports a stale or accidentally edited Parent label. Ordinary `contextcanon build` never dereferences the locator. Build loads only the accepted Parent artifact from the Child's local `.context/sources/<package-digest>/` store and verifies Node ID, version, both digests and package files.

Parent and ordinary Sources are intentionally different roles. Parent expresses the human-accepted semantic hierarchy; Sources express independent reusable composition. Both feed the same immutable package-composition engine, so inherited Rules, Topics and Resources use the same deterministic conflict rules without creating a second inheritance implementation.

Changing a Parent's live files does not silently change the Child. Each Parent advances only through explicit review and acceptance.

## Sources

`## Sources` lists accepted Context Nodes. The visible link label must match the canonical Node name of the accepted Source package, while the link target is its provenance/update location. The adjacent compiler-managed comment preserves stable identity and accepted version. Stable ID/version/digests define technical identity; `contextcanon check` reports a stale or accidentally edited visible Source label.

### Local development Source

An unpinned Source is resolved as a local node-root path inside the same repository:

```markdown
## Sources

- [ContextCanon Foundation](../foundation/) — `0.1.0`
  <!-- ctx:source id="<stable-node-id>" version="0.1.0" -->
```

This remains the simple development/dogfood case.

### Accepted immutable Source

An accepted external Source additionally pins both canonical semantics and exact published package bytes:

```markdown
## Sources

- [Python Development](https://example.org/context-nodes.git) — `1.2.0`
  <!-- ctx:source id="<stable-node-id>" version="1.2.0" normalized-digest="<sha256>" package-digest="<sha256>" -->
```

`normalized-digest` and `package-digest` are an all-or-nothing pair. Each is lowercase SHA-256 hexadecimal.

For a pinned Source, the visible link is provenance/update location rather than something ordinary `contextcanon build` dereferences. Build loads only the accepted immutable artifact from the consumer Node's `.context/sources/<package-digest>/` store and verifies Node ID, version, both digests, and package files.

This keeps normal builds offline and prevents a Source repository update from silently changing a consumer.

### Central Source discovery configuration

Operational Source discovery belongs in one repository-visible `contextcanon.yaml`, not duplicated across consuming Nodes. A pinned Source declaration keeps only accepted immutable identity (version plus both digests); its visible link may point to the central configuration. Existing inline `transport`/`ref`/`node-path` metadata remains readable as a compatibility fallback.

The v1 YAML configuration separates reusable Source identity from repository discovery:

```yaml
schema: contextcanon/config/v1
repositories:
  context-canon:
    kind: git
    location: https://github.com/SomeSunlight/context-canon.git
    ref: main
sources:
  c4c94726-3cc7-4df6-b779-72bbf9c06f40:
    repository: context-canon
    path: nodes/library/development-workflow
```

The same Source can be made completely local/offline by changing the repository once:

```yaml
repositories:
  context-canon:
    kind: local
    location: ../context-canon
```

Local paths may be relative to the consuming project root or absolute. They require no network access. Accepted package pins remain unchanged until explicit review/accept; changing discovery configuration never silently changes effective Context. The YAML file is deliberately the project-level operational configuration surface so later non-semantic ContextCanon settings can be added under a future schema version instead of inventing one file per setting.

`contextcanon source list` shows the canonical name from each accepted Source package, stable IDs and the resolved discovery configuration. If a consumer carries a stale visible label, the list warns about it while name-based commands still accept the canonical package name; `contextcanon check` reports that mismatch until the source is repaired or a successful acceptance normalizes the label. `contextcanon source update "Development Workflow"` performs fetch + exact diff + explicit acceptance as one guided flow. `--ref <branch|tag|commit>` is a one-off Git candidate override and never rewrites the central configuration or accepted pin.

When that guided `source update` starts from a legacy inline Git Source and no central mapping exists yet, ContextCanon records the equivalent durable discovery mapping in `contextcanon.yaml` after the legacy fetch succeeds. An exact 40-character legacy commit pin becomes default-branch discovery rather than a permanently frozen central ref, preserving the old "discover something newer" behavior; a one-off `--ref` is never persisted. This migration changes discovery configuration only, not the accepted immutable package pin. The legacy inline metadata remains readable as a compatibility fallback while the central mapping takes precedence.

After an ancestor Source is accepted, `contextcanon parent propagate --all` walks semantic Parent edges top-down, shows each exact diff, and asks before accepting that edge. `--yes` is available for an already-reviewed scripted run. This removes UUID/path archaeology without turning Parent updates into live inheritance.

### Legacy inline Git update transport

A pinned Source may additionally describe how candidate updates are retrieved when no central Source mapping exists:

```markdown
- [Python Development](https://example.org/context-nodes.git) — `1.2.0`
  <!-- ctx:source id="<stable-node-id>" version="1.2.0" normalized-digest="<sha256>" package-digest="<sha256>" transport="git" ref="main" node-path="nodes/library/python-development" -->
```

`transport`, `ref`, and `node-path` are an all-or-nothing set. Compiler 0.4 supports `transport="git"`.

`ref` names the branch/tag/ref from which `contextcanon source fetch` retrieves a candidate. It is deliberately **not** the accepted identity; the accepted state remains pinned by version plus both digests.

`node-path` locates the Source Node inside the retrieved repository snapshot. Use `.` for a repository-root Node. It is location only and may not be absolute, contain `..`, or use backslashes.

Transport metadata is only for candidate discovery. Normal `build` never uses it.

Source order is not precedence. See [Context composition](composition.md) for immutable package storage and the fetch/review/accept workflow.

## Local Rules

`## Local Rules` contains the Node's local Rules. The explicit label keeps authored-here Rules visually distinct from generated `Rules from …` sections; it does not mean those Rules override inherited identities. `###` headings group related Rules. Every Rule has a short visible title, a statement, rationale, and compiler-managed stable ID.

```markdown
### Security

- **Never commit secrets:** Credentials and secret values must stay outside version control.
  Why: Version control is not a secret store.
  <!-- ctx:rule id="SEC-001" -->
```

The title is part of the human presentation, not identity. Descendants address the stable ID.

## Changes

`## Changes` contains explicit local operations on inherited ordinary Rules.

Compiler 0.4 supports **Remove** and **Override**. Both operations bind the inherited Rule's stable identity: origin Node ID plus Rule ID. Visible Source names and Rule titles help humans but do not define identity.

### Remove

```markdown
## Changes

### Remove

- `Company Security / SEC-014` — Require legacy audit header
  Why: This project uses the replacement audit protocol instead.
  <!-- ctx:change op="remove" source-id="<stable-source-node-id>" rule-id="SEC-014" -->
```

A Remove deletes that inherited Rule from this Node's official Rule set. Descendants inherit the already-removed result.

If the targeted identity is not inherited, compilation fails with a dangling-Change diagnostic. Remove cannot silently become a no-op.

### Override

```markdown
## Changes

### Override

- `Python Development / PY-007` — Supported Python version
  New rule: Production code must support Python 3.12 or newer.
  Why: This project has standardized on the 3.12 runtime baseline.
  <!-- ctx:change op="override" source-id="<stable-source-node-id>" rule-id="PY-007" -->
```

An Override preserves the inherited Rule's identity, title, group, and origin, but replaces its effective statement for this Node. The compiler records the overriding Node and rationale as provenance. Descendants inherit that overridden meaning unless they explicitly change it again.

Only the statement is currently overridable. Renaming or regrouping an inherited Rule is deliberately not disguised as an Override.

A Node may define at most one local Change for a given inherited Rule identity.

Protected Rules and authorized exceptions are a later semantic layer. They will constrain which Changes are legal rather than changing the basic identity model.

## Local Topics

A Topic states when deeper context applies and explicitly types every target.

```markdown
## Local Topics

### Logging

When changing logging, diagnostics, or structured events:

Required:
- Resource: `docs/logging-contract.md`

Optional:
- Resource: `docs/logging-history.md`
```

A Topic can also navigate to another Context Node without composing it:

```markdown
Required:
- Context Node: `nodes/internal/framework-development`
```

`Resource` targets are materialized into the generated `CONTEXT/` package. Compiled Resource targets use an origin-Node namespace under `CONTEXT/references/`, so effective Topics can cross Source package boundaries without unrelated repositories colliding on paths. `Context Node` targets remain navigation rather than Source composition; compiled packages carry the stable target Node identity so inherited navigation remains meaningful even when the original repository-relative link is unavailable.

Topics compose transitively through accepted Sources just like effective Rules. A consuming Node renders inherited and local Topics together, while State/Plan/Overview remain local-only. Resource bytes from multiple Source paths are deduplicated only when the same origin-qualified package path has identical content; different bytes at that stable path are a structural conflict rather than Source-order precedence.

Every Topic ends with a compiler-managed stable ID:

```markdown
<!-- ctx:topic id="LOGGING" -->
```

## Normal authoring after onboarding

After a project has adopted ContextCanon, ordinary work does not repeat migration onboarding. The canonical source remains `CONTEXT.src.md` plus the Node's natural Resource files.

For existing text, edit `CONTEXT.src.md` directly. For a **new Rule or Topic**, prefer the deterministic authoring commands so ContextCanon allocates the hidden stable identity once instead of making the author invent a `ctx:rule` or `ctx:topic` comment:

```text
contextcanon author rule . --group Security --title "Keep secrets out of Git" --statement "Credentials and secret values must stay outside version control." --why "Version control is not a secret store."

contextcanon author topic . --title Logging --condition "When changing logging or diagnostics:" --required-resource docs/logging-contract.md
```

The commands write ordinary source syntax; they do **not** create another authoring database and they do not hide publication behind a write. The resulting `CONTEXT.src.md` is immediately readable and editable by hand. ContextCanon merely allocates the stable `RULE-...` or `TOPIC-...` identity and validates that the edited Node still parses.

The minimal daily loop is intentionally boring:

```text
read CONTEXT.md for the effective working context
→ edit CONTEXT.src.md and/or natural Resource files
→ use contextcanon author rule/topic when creating a new identified element
→ contextcanon build <node-or-repository>
→ contextcanon check <node-or-repository>
→ when a reusable Source has a candidate update, review it before explicit acceptance
```

Use `--all` with `build`/`check` when repository-wide generated state should be refreshed or verified. Source candidate discovery/review/acceptance remains a separate explicit workflow; normal authoring and normal builds never silently pull newer Source meaning.

## Compiler-managed authoring help

Raw Markdown may contain compiler-managed HTML comment blocks with copyable examples. These blocks are authoring help only; they do not carry critical human meaning and disappear from rendered Markdown.

A useful Change template is:

```markdown
### Override

- `Source name / RULE-ID` — Current rule title
  New rule: Replacement statement.
  Why: Why this Node differs.
  <!-- ctx:change op="override" source-id="<stable-source-node-id>" rule-id="RULE-ID" -->
```

## Current compiler contract

The executable compiler may intentionally support a narrower language than later specification layers. Unsupported syntax must fail clearly rather than be inferred. Implementation-specific module details belong to the implementation's own development documentation; this Foundation document describes the reusable authoring contract rather than one repository's internal module status.

### Version advancement

A Context Node version is the human-facing release identity for one published package generation. Different package bytes for the same stable Node ID must not silently reuse the same version.

When a prior generated package exists and `contextcanon build` detects changed package identity while `ctx:node version` is still unchanged, a SemVer-shaped version (`X.Y.Z`, optionally with a suffix such as `-draft`) receives the minimum automatic patch bump. For example, `0.2.0-draft` becomes `0.2.1-draft`. ContextCanon reports that this is only the mechanical minimum and asks the owner to consider a higher minor or major version when the semantic or compatibility significance warrants it. A version already advanced deliberately by the human is preserved.

ContextCanon does not infer whether a change is breaking or feature-level. Versions that cannot be safely patch-bumped are left for explicit human editing, with an actionable error. Consumers also reject Source candidates whose package identity changed while the provider reused the currently accepted version; the consumer must not repair the provider's release identity.
