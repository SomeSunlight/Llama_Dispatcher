# Context Composition

A Child Context Node does not have to copy everything it needs into one file. It can **combine several contexts** and add only what is special locally.

```text
Parent Context(s) ───────┐
Reusable Source(s) ──────┼──> effective Context of this Child
Local Delta ─────────────┘
```

That is the practical benefit of composition: project-wide context can come from a Parent, independent reusable concerns such as a Development Workflow or security baseline can be imported as Sources, and the Child keeps only its own local differences.

The important architectural warning follows immediately: **several imported contexts can contain non-orthogonal or contradictory guidance.** ContextCanon never treats import order as hidden precedence. Structural conflicts that can be proven deterministically are errors; semantic contradictions between otherwise unrelated statements must be resolved explicitly. See [Semantic conflicts](#semantic-conflicts) and [Local changes](#local-changes) for the deeper rules rather than duplicating that theory here.

Filesystem nesting creates none of these relationships. Parent and Source relationships are explicit.

## Parent and Source in one minute

A **Source** is independent reusable Context accepted by this Node. It may be used by otherwise unrelated projects or subsystems.

A **Parent** is accepted higher-level Context that a Child specializes. A Node may have several semantic Parents when several independent higher-level contexts genuinely apply.

Both relationships use exact accepted snapshots, so imported Context does not change underneath the Child. The Child keeps living with its last accepted snapshot while a Parent or Source can evolve independently. A newer snapshot becomes a review object first.

This is similar to notes from a lecture: the lecture may be revised later, while the student's existing notes remain as they were. Keeping the previous accepted snapshot lets ContextCanon show the exact change instead of asking the user to reconstruct it from memory.

## Reviewing a Parent change

A Parent update is not blind inheritance. For each changed Parent → Child edge, the human review should ask:

1. Does the changed guidance still apply to this Child?
2. Is it compatible with the Child's other imported Contexts?
3. Is the upstream change itself correct, complete, and well-scoped when seen from this Child?

If not, fix the reusable Parent/Source when the upstream guidance is wrong or too broad; use an explicit justified Override/Remove when the upstream rule is valid generally but intentionally differs here; or add a narrower local Rule when the real problem is missing scope or precision.

The normal guided command is:

```text
contextcanon propagate
```

It reviews downstream Parent edges top-down from the current Context Node. `contextcanon propagate --all` broadens the **review scope** to every semantic Parent graph in the repository; it does not mean blanket acceptance. Interactive propagation still asks before every changed edge. The explicit Parent-oriented commands remain available for one relationship:

```text
contextcanon parent review [<parent-node-id>] --node <child-node>
contextcanon parent accept [<parent-node-id>] --node <child-node>
```

The deterministic layer prepares an exact candidate, diff, and structural validation. Semantic applicability and correctness remain human decisions.

## Semantic Parent

A Node may have several Parents. Every relationship is explicit, and Parent order has no precedence. Repository directories remain locations only.

Parents should normally represent orthogonal context. The compiler catches structural conflicts for the same stable identity; broader natural-language contradictions remain a human review responsibility for now.

Parents and Sources are composed through the same `CompiledPackage` boundary. There is no special "parent text merge": the Child consumes the Parent's complete effective Rules, Topics, removals, overrides, and materialized Topic Resources as one exact package. The Parent role remains separately visible in human output, machine state, package metadata, and deterministic diff.

The accepted Parent pin is intentionally non-live. Editing or rebuilding the Parent Node elsewhere does not change an ordinary Child build. A Parent update is a later candidate/review/accept operation, not implicit inheritance from current filesystem bytes.

`parent review` is the only explicit single-edge step that consults a live Parent locator. When several Parents exist, name the Parent Node ID; the ID may be omitted for a singleton Parent. `build`, `check`, and `parent accept` continue to use immutable local package bytes; even if the live Parent changes again after review, acceptance means the exact reviewed candidate snapshot.

## Parent chains define scoped context

Semantic Parent paths scope context without loading unrelated siblings. Each accepted Parent package already carries its complete effective Rules, Topics, Resources, and transitive imports.

For example:

```text
Development Workflow Source ──> AI Workstation
                                 ├──> Llama Stack ──> Llama Dispatcher
                                 └──> Unrelated Sibling
```

Starting from `Llama Dispatcher` yields the effective Development Workflow + AI Workstation + Llama Stack + Llama Dispatcher context. It does **not** include `Unrelated Sibling`. This is semantic reachability through accepted package edges, not directory recursion.

Because every direct Parent pin is a self-contained immutable package snapshot, ordinary use at the leaf remains possible even when the upstream Source/Parent authoring trees are unavailable. Updating any ancestor is still an explicit review/accept operation at the next Child edge.

## No implicit precedence

Source or Parent order does not mean priority. ContextCanon must never silently apply "first source wins", "last source wins", or an equivalent Parent-order rule.

Different imports can therefore contribute independent elements without an artificial method-resolution order.

The compiler canonicalizes direct dependency order in normalized semantics. Reordering otherwise identical dependencies cannot accidentally masquerade as semantic precedence.

## Dependency graph

Composition relationships form a directed acyclic graph. The compiler deterministically detects structural problems such as dependency cycles, invalid identities/versions, dangling Changes, and incompatible transitive states of the same stable Rule.

Compiler 0.6 supports multiple immutable semantic Parents plus local and pinned Sources. All become `CompiledPackage` before composition, with no Parent- or Source-order precedence.

## Structural Rule conflicts

A stable Rule identity can reach a consumer through several composition paths. The compiler never uses dependency order to choose between those paths.

Equivalent compiled Rules with the same effective definition and provenance are deduplicated. If the same stable Rule arrives with different effective definitions or override provenance, compilation fails.

Remove is also carried as machine-level provenance rather than being forgotten as mere absence. Therefore a diamond such as this is detectable:

```text
              ┌─ Source A: removes Rule X ─┐
Foundation ───┤                            ├─> Consumer: conflict
              └─ Source B: keeps Rule X ──┘
```

The consumer cannot silently keep or drop Rule X. It must resolve the relationship explicitly.

Two paths may both carry compatible removal provenance; the resulting Rule remains absent while the machine state preserves the removals needed for later composition and diagnostics.

## Semantic conflicts

Two different imported elements may contradict each other even though their IDs are unrelated. A deterministic compiler cannot reliably prove every natural-language conflict. It preserves both unless an explicit local resolution exists.

The human decision may be to improve an upstream Parent/Source, apply an intentional local Override/Remove, or introduce a more precisely scoped local Rule. Import order is never the resolution.

A future optional LLM reviewer may flag likely conflicts, explain them, and suggest where to resolve them. The durable decision remains explicit in source.

## Local changes

A Node can resolve inherited ordinary Rules through explicit **Remove** and **Override** operations.

A Change addresses a Rule by stable identity:

```text
<origin-node-id>#<rule-id>
```

Visible names, titles, wording, and filesystem paths are not identity.

### Remove

Remove makes the inherited Rule no longer part of this Node's official Rule set. Descendants inherit the already-removed result.

The compiler keeps a removal record containing the Rule identity, removing Node, and rationale. This is machine semantics, not an active Rule shown to normal readers.

### Override

Override keeps the inherited Rule identity and origin but replaces its effective statement. The overriding Node and its rationale become provenance on the compiled Rule. If another descendant overrides it again, identity remains stable while the effective meaning and override provenance advance.

### Dangling operations

If the target Rule is not inherited, compilation fails. This matters especially after Source or Parent updates: an upstream change cannot silently leave a Child operation pointing at nothing.

A Node may define only one local Change against the same inherited Rule identity.

Protected Rules and **Use Exception** remain a later semantic layer. Protected Rules will prohibit ordinary Remove/Override and expose only explicitly authorized exceptions.

## Transitive composition

Composition is package meaning, not just direct-parent text.

```text
Foundation ──> Team Standard ──> Project
```

If Team Standard overrides a Foundation Rule, Project inherits that overridden Rule with Foundation identity and Team Standard override provenance. If Team Standard removes the Rule, Project does not expose it as active context but still carries the removal provenance needed for downstream composition.

This is why the compiler renders inherited Rules by their actual origin Node rather than only by the consumer's direct dependency list, and why the machine representation contains more state than the human-facing active Rule list.

An immutable package carries this complete effective state in `.context/package.json`; a descendant does not reconstruct it by parsing generated `CONTEXT.md`.

## Deterministic diff is the update boundary

ContextCanon compares compiled state before any semantic reviewer or consumer code is involved.

For two snapshots of the same consumer Node:

```text
contextcanon diff <before-node-root> <after-node-root>
```

For an accepted external Source and a candidate Source package, `source review` applies the same stable-identity `ContextDiff` model directly to the immutable packages:

```text
accepted Source package
        +
candidate Source package
        ↓
deterministic package diff
        +
consumer structural validation
        ↓
review receipt
```

The diff reports Source package/version changes, effective Rule changes including active/removed transitions and override provenance, local Change differences, Topic changes, and materialized Resource content changes. Human-readable and JSON representations come from the same deterministic change model.

The exact compiled difference exists first; semantic impact analysis is the human-facing layer above it.

## Source updates are change requests

Consumers remain pinned to an accepted immutable Source package. A newly published Source version is an update candidate, not live inheritance. Repository/discovery parameters live centrally in `contextcanon.yaml`; changing a Git ref or switching the same repository to a local/offline checkout changes only where candidates are discovered, never the currently accepted package. Existing inline Git transport metadata remains a compatibility fallback for older projects.

Human operators may address a Source by its unique visible name instead of copying its stable UUID. `contextcanon source list` exposes both. `contextcanon source update <name-or-id>` combines fetch, deterministic review, local-impact explanation, and explicit acceptance. If that changes a Node that has semantic descendants, downstream propagation is a separate reviewed activity rather than an automatic pull through the tree.

Lower-level Source commands remain available when explicit stages are useful:

```text
contextcanon source fetch <source-name-or-id> --node <consumer-node>
        ↓
verified candidate under .context/candidates/<package-digest>/
        ↓
contextcanon source review <source-name-or-id> <candidate-package> --node <consumer-node>
        ↓
exact diff + consumer structural checks + deterministic review receipt
        ↓
contextcanon source accept <source-name-or-id> <candidate-package> --node <consumer-node>
        ↓
accepted immutable package + updated exact Source pin
```

`source fetch` uses declared transport metadata only to discover candidate bytes. It cannot change accepted inheritance. `source review` substitutes the candidate into the actual consumer composition in memory so dangling local Changes and visible Rule collisions are detected before acceptance. `source accept` requires the matching non-stale review receipt.

The accepted Source pin records version, `normalized-digest`, and `package-digest`. Git discovery ref and node path remain update/location metadata rather than accepted identity.

## Accepted versus candidate state

Accepted external packages live under:

```text
<consumer>/.context/sources/<package-digest>/
```

They are reproducible consumer state and allow ordinary builds to remain independent of the Source repository.

Temporary update candidates live separately under:

```text
<consumer>/.context/candidates/<package-digest>/
```

A missing or corrupt accepted package is an error. It is never permission for `build` to fetch from the Source locator.

Package installation is staged and verified before atomic publication. Review receipts and Source-pin replacement are also published atomically. If the final canonical pin swap fails, the old `CONTEXT.src.md` and old accepted build state remain intact; a newly installed but unreferenced package is harmless immutable state.

## Topics and Resources compose transitively

A Source or Parent package carries its complete effective Topic set, not only the Topics authored directly at that dependency boundary. Resource targets are compiled to package-safe paths namespaced by the Topic's stable origin Node identity. Descendants therefore inherit both Topic conditions and the exact materialized Resource closure without consulting the upstream repository.

When the same inherited Topic identity reaches a Node through several composition paths, equivalent Topic definitions are deduplicated. If their effective definitions differ, compilation fails. Origin-qualified Resource paths behave the same way: identical bytes deduplicate, while different bytes at the same stable inherited path are a structural conflict.

`Context Node` Topic targets remain navigation rather than composition. Packages preserve the stable target Node ID/name so an inherited Topic can still explain where it points; a consumer does not invent a local link when that target Node is not materialized in the consumer package.

## Navigation is not composition

A Topic may direct an agent to deeper information or even to another Context Node when a task needs it. That is progressive disclosure, not inheritance.

```text
Gateway ──Topic──> Deeper Context Node
                         ▲
                         │ Source
                    Foundation
```

The Gateway does not inherit the deeper Node. It merely sends relevant work there. The deeper Node composes Foundation only when that Source relationship is declared explicitly.

Keeping these relationships distinct prevents navigation choices from silently changing which Rules a Node publishes.

## Node directories do not define composition

Every Context Node is physically rooted in its own directory, but that directory is only its location. A parent directory, nested directory, Git repository, or sibling directory does not become a Parent or Source automatically.

This matters in repositories containing several Nodes: filesystem structure can organize them clearly without creating hidden context relationships. Prefer a Node root that contains the files it chiefly governs; when several semantic Parents apply, choose one clear physical home for navigation.

The same principle applies to Git transport. A node path says where the Node is found inside a retrieved repository snapshot; the stable Node ID says which Node it is.
