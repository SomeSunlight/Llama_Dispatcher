# Executing a Development Block

Use this when a coherent project change is being designed, implemented, resumed after interruption, prepared for project-owner review, finalized for merge, or closed after merge.

The aim is **recoverability without ceremony for ceremony's sake**: the repository should always say what is being done and what is already complete, while expensive or repetitive verification is performed at the points where it adds confidence.

## 1. Put the block in PLAN before editing

Before changing implementation, context structure, or substantial documentation:

1. ensure an Issue records why the change exists;
2. add a short subsection to `PLAN.md` (or the equivalent) and reference the Issue;
3. list concrete checkboxes that are small enough to show meaningful progress.

The planned scope is the writable scope. Reading inherited or shared Context does not add it; expand the plan explicitly before editing broader areas.

Do not make the checklist a transcript of every command. It is a recovery map for the development intent.

## 2. Check off completed work immediately

When one listed step is actually complete, change its checkbox to `[x]` immediately.

A completed step should not remain unchecked merely because the whole block is unfinished. Conversely, do not check a step merely because editing started; include the verification that makes that step genuinely complete.

This gives a new human or LLM session a simple recovery procedure:

```text
read the project entry context / README
→ read STATE.md or equivalent when current position matters
→ read the active PLAN.md block
→ continue at the first unchecked item
```

Chat history may add useful discussion, but it must not be required to reconstruct the active plan.

### Resuming after a short conversational interruption

In a controlled single-owner workflow, a short interruption in the chat does not by itself make repository state suspect.

When the project owner returns after a short pause, explicitly says to continue, and does not report any intervening repository change, resume from the last established branch/PR state. Do not spend the next work window re-fetching the whole repository, PR, and CI history merely to prove that nothing changed.

Re-check exact mutable state when there is a concrete reason: the project owner reports another edit, the repository rejects a write because the head moved, a tool result contradicts the last checkpoint, or the next operation itself requires an exact current identity.

## 3. Work in coherent edits, not micro-cycles

The project's most expensive full verification cycle should not run after every tiny wording or implementation edit when the result will immediately be superseded.

For one coherent correction block, the normal flow is:

```text
PLAN checkpoint
      ↓
related authoring / implementation edits
      ↓
focused tests / repository checks
      ↓
CI may expose known generated drift or another understood intermediate failure
      ↓
present one coherent review candidate
      ↓
project-owner review
      ↓
if corrections are requested → return to coherent edits
      ↓
if project owner approves the large line
      ↓
final generated-output / packaging / release cleanup as applicable
      ↓
exact-head complete merge-gate verification
      ↓
merge to the accepted branch
      ↓
post-merge accepted-baseline/state checkpoint
      ↓
next coherent development block
```

If a change introduces new deterministic behavior, test that behavior before relying on broader integration or generated-output checks. If several related edits all change the same generated material, allow them to settle before regenerating that material.

The important distinction is that **review-ready and merge-ready are different states**. A successful merge is followed by one small closure step because the merge itself creates facts that a pre-merge candidate cannot truthfully record.

### Owner-approved Fast Track blocks

Sometimes the project owner has already reviewed the product direction and explicitly delegates a coherent implementation phase without wanting to approve every intermediate block. In that case, keep the recovery map and meaningful focused checks, but do not manufacture repeated PR handoffs, full CI cycles, generated-output refreshes, or status-polish commits merely because normal review would have happened between those blocks.

Fast Track changes **cadence, not authority**: the work still stays on a review branch, PLAN remains current enough to resume after interruption, unknown failures are investigated, and the resulting coherent candidate still requires project-owner review followed by the ordinary exact-head merge gate.

Make the boundary visible in PLAN rather than leaving the mode implicit in chat history. A compact form is enough:

```text
Fast Track status — ACTIVE
Scope: <delegated coherent work>
Deferred ceremony: <what is intentionally batched>
Exit: <owner ends it or named coherent review boundary>

... work/checkpoints ...

Fast Track status — CLOSED
Result/checkpoint: <where normal cadence resumes>
```

Do not invent a historical start time after the fact. If a Fast Track is already under way when this convention is adopted, record that it is active now, its current scope, and its exit condition. The important property is recoverable mode state, not timestamp theatre.

## 4. What automated verification proves and what it does not

A green CI or local verification run proves only that the checks configured by the project passed on that exact revision.

It does **not** by itself mean:

- the product decision is good;
- the architecture is appropriate;
- the documentation is pleasant to use;
- semantic LLM output is correct;
- the project owner approved the result.

Those remain human review questions.

During project-owner review, automation may therefore still be red when the remaining failure is understood and explicitly disclosed — for example, intentionally stale generated output after authored source changed. Unknown failures still need investigation; "review can happen before green" is not permission to ignore unexplained breakage.

## 5. Keep obsolete verification work cheap

When the project's CI supports cancellation/concurrency, prefer cancelling obsolete runs after a newer commit arrives on the same review branch. An older run that can no longer become the merge head has little value unless it is needed to diagnose a specific failure.

The strict requirement belongs to the **merge gate**: after project-owner approval, the exact head intended for the accepted branch must complete the project's full required verification.

## 6. Review-ready boundary

A block can be handed to the project owner for review when:

- the intended product/documentation structure is present and understandable;
- completed PLAN items are checkpointed honestly;
- relevant focused tests have run far enough to expose obvious mistakes;
- known CI failures or generated drift are explained rather than hidden;
- the review description tells the owner what changed, what deserves attention, and what remains technical finalization.

The reviewer should be able to judge the **large line** without waiting for repeated expensive finalization cycles that may be invalidated by the next review correction.

## 7. Merge-ready boundary

After the project owner explicitly approves the reviewed result, finish the mechanical publication gate defined by the project:

- apply any final approved corrections;
- regenerate or package only the derived outputs affected by the final authored state;
- run the complete required verification on the exact current head;
- require zero generated drift when generated canonical output is part of the repository contract;
- inspect the final diff for accidental temporary or placeholder files;
- update the review description with the exact merge-ready head and relevant verification evidence when useful.

Only then merge to the accepted branch.

Merge-ready is not the final recovery checkpoint. The merge creates new repository facts — most obviously the actual merged state and sometimes a new squash/merge commit identity — that could not be checkpointed honestly on the pre-merge branch.

## 8. Close the accepted baseline after merge

Immediately after a reviewed change has been merged, and **before starting the next coherent development block**, reconcile durable status surfaces that were necessarily written from the pre-merge point of view.

As applicable:

1. verify the actual merged change/state from repository metadata;
2. mark the completed merge outcome in `PLAN.md` when the preceding block tracked it explicitly;
3. update `STATE.md` or the project's equivalent current-state document to the newly accepted baseline and next real focus;
4. update README/CHANGELOG status text when the merge made it stale or incomplete;
5. correct the merged review description when it still contains live wording such as "open", "not merged", or "current review candidate" while preserving historical review evidence;
6. search the small set of status/navigation documents for old branch, review, or baseline wording so another stale surface is not silently left behind.

Keep this checkpoint narrow. It records facts created by the just-completed merge; it is not a place to start the next feature or to smuggle in a new semantic decision.

If the checkpoint itself discovers that a real product, architecture, or workflow change is necessary, stop treating that part as bookkeeping: record a normal coherent development block in PLAN and review it normally.
