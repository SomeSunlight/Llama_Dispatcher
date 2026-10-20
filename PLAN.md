# PLAN — Multi-engine Dispatcher: attach-first, external process supervision

**Planning revision:** 2026-10-19 (proposal for owner review; no runtime/code changes in this PR).
**Epic:** [#8](https://github.com/SomeSunlight/Llama_Dispatcher/issues/8).
**Baseline:** S00 [#19](https://github.com/SomeSunlight/Llama_Dispatcher/issues/19) was owner-tested across three Windows/WSL installations and [PR #20](https://github.com/SomeSunlight/Llama_Dispatcher/pull/20) merged into `main` on 2026-10-19.
**Accepted S01:** [PR #22](https://github.com/SomeSunlight/Llama_Dispatcher/pull/22) owner-tested (unit, live, SQLite and tiny streaming/nonstreaming inference) and squash-merged 2026-10-20. **Next gate:** S02 [#10](https://github.com/SomeSunlight/Llama_Dispatcher/issues/10), under independent owner review.

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
- [ ] **S02 — [#10](https://github.com/SomeSunlight/Llama_Dispatcher/issues/10)**: Per-client authentication/identity and explicit `default/enforce/passthrough` policy, preserving current clients until a tested migration. Requires S01; **required before any Strata production cutover**.
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

1. Owner reviews/accepts this architecture plan; then update Epic #8 and conflicting issue bodies, and create/confirm the independent service-manager project's tracking issues.
2. Start **S01 #9 only**, using the accepted merged S00 test suite. Produce one focused PR with actual Windows/WSL-relevant automated tests, manual Speedy smoke/rollback steps and no other gate's code.
3. Continue S02 → S03, retaining current Speedy Strata as reference and Caddy fallback. No forced move to the external supervisor.
4. Advance telemetry, compilation and supervisor integration in separately approved gates, then selectively migrate instances.

**Next after plan approval:** S01 #9. **First production-user milestone:** S03 #11, Strata attach and authenticated proxy aliases.
