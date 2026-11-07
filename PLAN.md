## S03 role-routing integration checkpoint — live use, 2026-11-07

**Current merge candidate:** [PR #30](https://github.com/SomeSunlight/Llama_Dispatcher/pull/30), with matching [AI Workstation PR #45](https://github.com/SomeSunlight/ai-workstation/pull/45). Both have passed exact-head Windows/Ubuntu CI before this checkpoint and are now being prepared for separate owner-reviewed squash merges to `main`. Earlier pending-S03 or pending-first-Strata-smoke notes below are historical.

**Operator-verified real usage:**
- Native Strata remains one externally owned backend. Attached Dispatcher advertises `sparringpartner` and `agent` as independent public model aliases targeting the same physical model. The authenticated Caddy HTTPS path and independent S02 identities work from native Windows Open WebUI and remote WSL Open WebUI/Goose.
- `default` S02 policy injects the configured role parameters. Real `metrics_proxy_requests` evidence includes `client_model=agent`, `policy_mode=default`, `reasoning_effort=none`, sampling defaults, and `source=dispatcher_policy`; the operator observed non-reasoning agent behavior. Real Goose calls have `client_model=sparringpartner`, `reasoning_effort=high`, HTTP 200 and `finish_reason=tool_calls`. Requests preserve the same `target_model`; no second inference process or metrics migration was required.
- **Goose planner/subagent orchestration is separate:** `GOOSE_SUBAGENT_*` selection does not make every root request a subagent call. Evidence so far proves the root Goose/provider request path, **not** a successfully invoked separate `agent` subagent. Treat this as an external Goose setup/test gate, not an incomplete alias-routing contract.

**Remaining work stays independent:** S04/S05/S06 telemetry/history, S07 deterministic engine launch plans and the old 3090 ensemble remain separately gated. [PR #32](https://github.com/SomeSunlight/Llama_Dispatcher/pull/32) is stacked on #30 and must be rebased/re-reviewed when #30 is squash-merged; do not merge legacy history staging as part of the two-role milestone. AIW's native Strata/Kaspersky-integrity hardening [issue #53](https://github.com/SomeSunlight/ai-workstation/issues/53) is the next urgent native-host focus after the baseline merges. Preserve direct-Strata rollback, client credentials, old instance data and running service ownership.

---

## Review gate — resilient owned-directory cleanup (#28 / PR #29)

**Status:** Implementation, accepted ContextCanon updates and owner Windows regression tests complete; final squash merge remains the owner's decision.

Purpose: apply the shared [Development Workflow filesystem-cleanup contract](https://github.com/SomeSunlight/context-canon/blob/main/nodes/library/development-workflow/docs/filesystem-cleanup.md) to isolated S02/S03 test fixtures. Do not change inference-engine/process ownership, Strata, Caddy, SQLite or production gateway operation.

- [x] Replace S02 disposable private-client TemporaryDirectory cleanup with bounded retry, safe link refusal and non-masking warnings for persistent locks.
- [x] Replace S03 silent Windows recursive deletion with scoped, repeatable cleanup and later pruning of stale, recursively fileless owned session skeletons only.
- [x] Add offline Python and Windows PowerShell regressions; owner ran and passed the isolated tests locally on Windows.
- [x] Accept GitHub Parent `0.1.9-draft` with inherited Development Workflow `0.3.8-draft`, regenerate/verify the root and local Child ContextCanon packages; no hand-written pins.
- [x] Confirm exact-head Ubuntu/native Windows CI for code plus ContextCanon acceptance ([run #41675465667](https://github.com/SomeSunlight/Llama_Dispatcher/actions/runs/41675465667)).
- [ ] Owner reviews and squash-merges [PR #29](https://github.com/SomeSunlight/Llama_Dispatcher/pull/29); [Issue #28](https://github.com/SomeSunlight/Llama_Dispatcher/issues/28) closes only after merge.

---

# PLAN — Multi-engine Dispatcher: attach-first, external process supervision

**Planning revision:** 2026-10-25 (S02 and PR #25 accepted baselines recorded; runtime design unchanged).
**Epic:** [#8](https://github.com/SomeSunlight/Llama_Dispatcher/issues/8).
**Baseline:** S00 [#19](https://github.com/SomeSunlight/Llama_Dispatcher/issues/19) was owner-tested across three Windows/WSL installations and [PR #20](https://github.com/SomeSunlight/Llama_Dispatcher/pull/20) merged into `main` on 2026-10-19.
**Accepted S01:** [PR #22](https://github.com/SomeSunlight/Llama_Dispatcher/pull/22) owner-tested (unit, live, SQLite and tiny streaming/nonstreaming inference) and squash-merged 2026-10-20. **Accepted S02:** [PR #23](https://github.com/SomeSunlight/Llama_Dispatcher/pull/23) squash-merged 2026-10-24. **Next implementation gate:** S03 [#11](https://github.com/SomeSunlight/Llama_Dispatcher/issues/11), pending its own scoped approval.

> This document defines the **intended future boundary**, not a claim that the current Dispatcher is already attach-only. The currently accepted llama.cpp managed-start path remains functional until a separately approved transition explicitly retires it.

## 1. Goal and observed operating reality

- **Speedy_Win + Strata / Qwen3.8 Flash Next IQ3_S** is the primary local inference platform. The existing Strata `127.0.0.1:8080`, Caddy HTTPS `/strata/v1`, Goose and Open WebUI usage are the working reference, not a platform to rebuild.
- The laptop's local large-model inference is experimentally useful but not production-viable at acceptable reliability/resources; it is **not** a performance or migration acceptance blocker. The laptop primarily consumes Speedy's service over the home network; remote clients must retain authentication and secure transport.
- Useful Logseq MCP integration with Strata/Open WebUI is already observed. Semantic indexing and other MCP/CLI services are planned in a **separate services-management workstream**, not in the Dispatcher backend abstraction.
- The immediate value is **Dispatcher features for the existing Strata process**: aliases and per-client policy, robust tools/vision/streaming/reasoning semantics, request provenance, and subsequently metrics. Do not require a new supervisor before enabling this.

## 2. Architecture decision — who owns what

| Domain | Owner | Boundary |
| --- | --- | --- |
| Ensemble/profile/model defaults, precedence, engine-specific semantic compilation, alias mapping | **Dispatcher** | Single source of model policy and generation settings |
| OpenAI-compatible proxy, client identity, request policy, routing, inference/proxy metrics | **Dispatcher** | Attach to external engine endpoints; preserve declared / forwarded / observed provenance |
| Deterministic **launch-plan compilation** from a selected ensemble and machine-local runtime roots | **Dispatcher** | Outputs structured, versioned, secret-free plan; **does not execute it** |
| OS process start/stop/restart, child trees, resource admission, RAM/commit/VRAM safety, service dependencies, OS health, lifecycle events | **External service manager** | **Only authoritative supervisor** of managed processes, including Dispatcher, Strata, llama.cpp, Caddy and MCP services |
| Native model packaging, setup, calibration, low-level options and execution | **Strata or llama.cpp** | Do not reimplement engine-native procedures |
| Application-level tool providers (Logseq, transport, web and future MCP/CLI) | **Their own services** | Manager supervises when needed; Dispatcher is not an MCP registry |

**One supervisor** means no second restart loop, kill authority, process discovery-based takeover, or resource scheduling inside Dispatcher. Lightweight backend HTTP health/capability checks remain essential for proxy routing and are **not** OS process supervision. The Dispatcher must never kill an attached service.

**Transition:** Existing managed llama.cpp modes, benchmarks and evals remain backward compatible until replacement is explicitly accepted per instance. They are *legacy behavior*, not the desired long-term architecture. First Strata integration runs attach-only; no process migration is needed.

**Supervisor technology is not yet selected.** Evaluate native-host [Process Compose](https://github.com/F1bonacc1/process-compose) against the current Windows startup baseline, with Python for machine-specific planning, command UX and resource policy. Windows Task Scheduler and Linux systemd can bootstrap the supervisor. Do not promise Windows/WSL parity until tested; avoid making Docker a prerequisite for native Strata.

See [docs/runtime-ownership-contract.md](docs/runtime-ownership-contract.md) for the target handoff/LaunchPlan contract and transition safety conditions.

## 3. Invariants / acceptance policy

- **Owner-gated development**: one scoped issue → tests and PR → owner's local smoke testing and explicit approval → merge → next dependent gate. Keep a working `main`, rollback path, and independent instance migrations.
- **Readable commit history**: PR titles describe a user-visible outcome in clear, short language. Keep technical implementation details in PR bodies and commit details. Repository setting **Settings → General → Pull Requests → Allow squash merging → Default commit message → Pull request title** makes the squash title equal the reviewed PR title.
- **Do not break Speedy**: leave direct Caddy `/strata/v1` diagnostic route operational until Dispatcher `/v1` is authenticated and validated from Goose and Open WebUI; preserve current 131072 context, image/vision, runtime options and calibration.
- **Client identity before cutover**: distinct revocable credentials for Goose and Open WebUI; verify Caddy trust boundary, no attribution based solely on User-Agent or untrusted headers. No secrets/prompts/responses in Git, JSON plans, metrics or ordinary logs.
- **Observed vs declared**: maintain four facts separately: client request, Dispatcher policy, exact forwarded request, engine-observed behavior. Unknown remains unknown. Attached runs must never be recorded as Dispatcher-launched.
- **Portable configuration**: canonical precedence is model defaults → instance engine defaults → profile → ensemble entry → explicit runtime overrides. Avoid absolute OS roots in shared profiles; preserve independent `Speedy_Win`, `Speedy_WSL`, `Laptop_Win`, `Laptop_WSL` identities/data.
- **Safety**: no unexpected model download, relocation, calibration, Caddy cutover or automated restarts. External resource manager enforces co-residence and host memory headroom; Dispatcher provides only declared requirements and engine observations.
- **Resource realism**: severe RAM/VRAM/Windows commit pressure must fail explicitly or defer work rather than silently swap/overcommit and destabilize Strata. Do not treat CPU-only embedding as zero RAM consumption.
- **No speculative adapters**: begin with existing llama.cpp and Strata. No generalized plugin marketplace or new engine until a concrete need.

## 4. Ordered Dispatcher gates (individually owner-reviewed)

Checked boxes denote **merged and owner-accepted**, not merely coded. Preserve existing issue IDs so historical discussion stays navigable.

- [x] **S00 — [#19](https://github.com/SomeSunlight/Llama_Dispatcher/issues/19)**: Baseline characterization only. [PR #20](https://github.com/SomeSunlight/Llama_Dispatcher/pull/20) accepted and squash-merged on 2026-10-19; owner reports successful runs across three Windows/WSL installations. No production refactor.
- [x] **S01 — [#9](https://github.com/SomeSunlight/Llama_Dispatcher/issues/9)**: Extract small, capability-aware llama.cpp backend / compile vs proxy / attachment seams **without changing current managed llama.cpp behavior**. Tests from S00 are mandatory. Define endpoint-attachment contract. Requires S00 and this plan's approval. Owner accepted and squash-merged [PR #22](https://github.com/SomeSunlight/Llama_Dispatcher/pull/22) on 2026-10-20, including live inference regression.
- [x] **S02 — [#10](https://github.com/SomeSunlight/Llama_Dispatcher/issues/10)**: Per-client authentication/identity and explicit `default/enforce/passthrough` policy, preserving current clients until a tested migration. Requires S01; **required before any Strata production cutover**. Owner accepted and squash-merged [PR #23](https://github.com/SomeSunlight/Llama_Dispatcher/pull/23) on 2026-10-24; this does not authorize the later S03 cutover.
- [ ] **S03 — [#11](https://github.com/SomeSunlight/Llama_Dispatcher/issues/11)**: **First deliverable with real user value:** Strata HTTP attach-only adapter and proxy aliases; test long streaming/tool calling, vision, reasoning semantics, cancellation, large context and authentication against the currently running Speedy Strata. Do not start/stop Strata; preserve direct Caddy route as fallback. Requires S01 + S02; **external supervisor is NOT a prerequisite**.
- [ ] **S04 — [#12](https://github.com/SomeSunlight/Llama_Dispatcher/issues/12)**: Additive engine-neutral SQLite/run/config/provenance schema. Attached process is observed, not owned; external supervisor is process-lifecycle authority. Can be designed with S02/S03 but implementation is a separately accepted PR.
- [ ] **S05 — [#13](https://github.com/SomeSunlight/Llama_Dispatcher/issues/13)**: Strata native `/metrics` / `/status` ingest, lossless missingness and safe correlation with proxy requests. Requires S03 + S04.
- [ ] **S06 — [#14](https://github.com/SomeSunlight/Llama_Dispatcher/issues/14)**: Verified SQLite online backup/restore with local retention and opt-in sanitized Git snapshots. Requires stable S04; may be independently prioritized for data-protection reasons.
- [ ] **S07 — [#15](https://github.com/SomeSunlight/Llama_Dispatcher/issues/15)**: Portable native Strata config handoff, **deterministic machine-readable LaunchPlan v1 compiler** and drift-safe previews/snapshots; preserve Strata-native setup/calibration. No engine process start by Dispatcher. Requires S03 and relevant S04 provenance design.
- [ ] **S08 — [#16](https://github.com/SomeSunlight/Llama_Dispatcher/issues/16)**: **Redefined:** external supervisor handshake, ownership/attach/detach state reporting, readiness and launch-plan/run correlation, compatibility migration from legacy managed startup. **Do not implement** a second start/stop/restart supervisor inside Dispatcher. Requires S07, S04 and a separately proven external-manager contract.
- [ ] **S09 — [#17](https://github.com/SomeSunlight/Llama_Dispatcher/issues/17)**: Import native Strata calibration/history and offer explicit handoff for opt-in native calibration with operator/manager approval; no Dispatcher process scheduling. Requires S07, S04 and manager handoff for active calibration.
- [ ] **S10 — [#18](https://github.com/SomeSunlight/Llama_Dispatcher/issues/18)**: Heterogeneous aliases/HTTP routing to multiple *attached* engines and consistent telemetry. No engine process ownership; process admission, OS memory and restart remain external. Requires accepted multi-engine routing/config contracts and tested supervisor safety where co-resident processes are used.

S03 is the earliest meaningful Speedy/Strata integration gate. S04–S10 are **not** authorization to implement everything after S01. Dependency changes require an explicit PLAN review.

## 5. Parallel external-service-manager workstream (different repository)

This is the **target design**, not a claim that a repo or process manager already exists:

- **M00 / discovery:** inventory the accepted Speedy Windows PowerShell start of Strata, Caddy and Open WebUI; reproduce non-destructive health/ownership checks and reliable graceful shutdown. Compare Process Compose with native OS supervisor facilities. Select tooling only after Windows proof.
- **M01 / viable service manager:** Python configuration/CLI + chosen supervisor, idempotent start, health, logs, stop, identity ownership, rollback, no double-start. Test Windows first, then WSL, then native Linux when available. Do not require Dispatcher changes for initial service management.
- **M02 / background services:** manage existing Logseq MCP, incremental LanceDB indexer and CPU-only llama.cpp embedding service with bounded RAM/CPU use; verify sleep/load behavior and embedding API timeout before promising on-demand availability. Keep private Logseq graph and vectors outside Git.
- **M03 / Dispatcher handoff:** consume LaunchPlan v1 from S07, launch engines according to policy, publish **observed** receipt (PID/start time/config hash/endpoints) and run health; Dispatcher attaches independently. No parallel process owner.
- **M04 / extensibility:** add explicitly approved MCP/CLI services (e.g. web and SBB lookup) via appropriate stdio/HTTP mechanisms, not a permanent daemon per tool. Tool permissions restricted; no unconstrained LLM process-management access.

The external workstream can advance **in parallel** with S01–S03. It is not a new blocker for getting Strata behind Dispatcher.

## 6. Instance migrations and operational rollout

Independent instance repositories remain separately owned; each migration gets a dry-run diff, rollback and an owner approval:

- [ ] [Speedy_Win #3](https://github.com/SomeSunlight/Llama_Dispatcher_Speedy_Win/issues/3) — **first production Strata attach/cutover** after S03; keep direct Caddy Strata route until verified.
- [ ] [Speedy_WSL #2](https://github.com/SomeSunlight/Llama_Dispatcher_Speedy_WSL/issues/2) — defer until a real local use case; preserve WSL identity/data.
- [ ] [Laptop_Win #3](https://github.com/SomeSunlight/Llama_Dispatcher_Laptop_Win/issues/3) — optional/experimental local inference, not a production-performance target.
- [ ] [Laptop_WSL #3](https://github.com/SomeSunlight/Llama_Dispatcher_Laptop_WSL/issues/3) — WSL local inference is optional; remote access to Speedy does **not** require a laptop backend migration.

Do not copy metrics DBs or host-specific roots across machines. Client-side use of Speedy from laptop should be secure and should not start another Strata process.

## 7. Existing issues whose scope must be reconciled

- [#16](https://github.com/SomeSunlight/Llama_Dispatcher/issues/16) currently describes an in-Dispatcher lifecycle supervisor. **Supersede that implementation scope**, preserve its history, and redirect process management to the new services workstream.
- [#18](https://github.com/SomeSunlight/Llama_Dispatcher/issues/18) has process admission/start/stop in Dispatcher. Move those to the manager; retain heterogeneous model routing and metric semantics.
- [#15](https://github.com/SomeSunlight/Llama_Dispatcher/issues/15) owns native Strata config handling and a versioned, side-effect-free launch-plan compiler.
- [#17](https://github.com/SomeSunlight/Llama_Dispatcher/issues/17) must hand native calibration execution to the engine/manager, not become an engine launcher.
- [#4](https://github.com/SomeSunlight/Llama_Dispatcher/issues/4) concerns host-memory monitoring during startup, now primarily external-manager scope. Preserve Dispatcher engine-observed diagnostics.
- [#7](https://github.com/SomeSunlight/Llama_Dispatcher/issues/7) configuration ownership remains relevant; adjust documentation to make launch-plan ownership explicit.

The issue bodies from the 2026-10-16 roadmap may still describe the **old** process-manager design until the owner approves this planning PR. Do not implement their conflicting portions.

## 8. How to resume safely

1. The accepted S00, S01 and S02 baselines are recorded above; do not reopen them without a separately scoped issue.
2. With the ContextCanon-only [PR #25](https://github.com/SomeSunlight/Llama_Dispatcher/pull/25) merged and its baseline recorded, take up **S03 #11** in a separate owner-reviewed implementation PR. Keep the existing Speedy Strata process and direct Caddy route as reference/fallback.
3. Advance telemetry, compilation and external supervisor integration in their separately approved gates, then selectively migrate instances. No forced move to an external supervisor for S03.

**Next implementation gate:** S03 #11, Strata attach and authenticated proxy aliases.

## 9. ContextCanon parent migration — [#24](https://github.com/SomeSunlight/Llama_Dispatcher/issues/24)

This isolated context-maintenance block is tracked by [PR #25](https://github.com/SomeSunlight/Llama_Dispatcher/pull/25). It changes ContextCanon authoring, accepted packages and their deterministic outputs, plus the relevant CI verification step; it does not change Dispatcher runtime behavior.

- [x] Remove the outdated ContextCanon Foundation import and use the GitHub Parent, inheriting Development Workflow.
- [x] Adopt the exact GitHub package using ContextCanon, propagate to local Children, and regenerate/verify the context packages. Owner performed the ContextCanon-managed migration.
- [x] Replace machine-specific Source discovery configuration with the portable Git repository and eliminate stale Foundation discovery mappings.
- [x] Update CI to pin the compiler supporting the accepted packages and verify all local Context Nodes.
- [x] Confirm the review candidate passes required Windows/Linux CI, including generated ContextCanon output and zero drift; reverify the exact final head after the final checkpoint commit.
- [x] Owner approved and squash-merged PR #25 on 2026-10-25 (accepted `main` commit `c6a1a9bf4f3b1a7c5e20fdf965fc4c4a4fe5e43e`).
- [x] Reconcile the post-merge accepted baseline in `PLAN.md`; S03 #11 is the next independently reviewed implementation block.

Future ContextCanon authoring/discovery improvements and the generated project map are tracked separately in [context-canon #123](https://github.com/SomeSunlight/context-canon/issues/123) and [#124](https://github.com/SomeSunlight/context-canon/issues/124), and are not prerequisites for this PR.

## 10. S03 implementation checkpoint — [#11](https://github.com/SomeSunlight/Llama_Dispatcher/issues/11)

**Status (2026-11-01):** draft review [PR #27](https://github.com/SomeSunlight/Llama_Dispatcher/pull/27), mock/CI verified; **real Speedy Strata connection is still awaiting owner testing**. The travel-laptop attempted Qwen3.6 UD-Q4_K_XL native Strata boot but failed on RTX 500 Ada 4-GiB VRAM before engine readiness (missing 1159 MiB for hybrid expert buffers); this is hardware capacity, not an S03 HTTP result. Speedy/Windows already operates native Strata successfully. Scope is opt-in, attached HTTP, no instance migration or Caddy cutover.

- [x] Verify accepted S02/PR #25/#26 baseline and establish a separate S03 review branch.
- [x] Define strict attach configuration, credential isolation, request reasoning resolution and unavailable behavior in deterministic contract tests.
- [x] Implement Strata HTTP attachment and probe/alias/proxy with no engine subprocess or lifecycle control; keep llama.cpp serve, bench, eval and legacy proxy unchanged.
- [x] Verify HTTP status, SSE/cancellation, tool/vision content forwarding, authentication separation, redacted debug previews and existing S00–S02 regressions in 87 mock/unit tests on Windows and Ubuntu CI. This is not native Strata validation.
- [x] Document laptop-first smoke/rollback, automated observations and deferred Speedy owner gates; open draft review PR #27.
- [x] Record the failed native **laptop** model initialization as an unrelated host-memory limit; do not require further laptop model downloads to advance S03.
- [x] Prepare a **real Speedy/Windows owner smoke**: one-command disposable PowerShell launch, native model-ID discovery, independent S02 test identity, strict loopback-only Dispatcher bind, explicit no-inference discovery first, opt-in tiny real nonstream+SSE, read-only SQLite audit inspection, sanitized report and cleanup. Add isolated tests and Windows PowerShell syntax CI; keep native Strata and Caddy intact.
- [ ] Owner runs `scripts/s03_speedy_smoke.ps1` on Speedy with its already-running Strata; then opts into `-Inference`. Record actual API compatibility, model ID, policy outcome, streaming, SQLite evidence, exceptions and engine version, without sharing keys or prompt content.
- [x] After the first Speedy native smoke, add an owner-controlled existing-gateway trial: a foreground-only S03 Dispatcher on the existing port 8001 in a separate instance, one transitional hashed S02 `home-gateway` identity derived from Speedy's DPAPI secret, explicit Caddy Authorization forwarding (dry-run by default, opt-in apply/rollback), and a Goose/WSL checklist without adding an HTTPS route. Keep Strata/Caddy native process ownership unchanged.
- [x] Extend Windows CI to syntax-check both scripts and exercise a synthetic CRLF Caddyfile dry run without altering it; verify Linux regressions on code head `85498aee37deb1001683ad3e63f5647ae2f4048a` ([run #41362797438](https://github.com/SomeSunlight/Llama_Dispatcher/actions/runs/41362797438)). **No real Caddy reload has been performed by this PR.**
- [ ] Owner runs the long-lived S03 foreground trial on Speedy (checking that 8001 is free), applies the gateway change only after the local S02 auth checks, and verifies Goose from Laptop/WSL uses the existing Caddy `/v1` route.
- [ ] Owner separately verifies representative complex Goose/Open WebUI traffic, reasoning/tools/vision/cancellation on Speedy; keep the direct Caddy `/strata/v1` path available. This is the meaningful functional acceptance; no automatic production cutover.
- [ ] Owner reviews actual evidence and explicitly approves; perform exact-head checks before a separately authorized merge. Speedy/Caddy/Goose/Open WebUI production cutover is a different owner gate.

