# PLAN — Multi-engine Dispatcher (owner-gated program)

**Status:** Planning recorded 2026-10-16. **No implementation phase started or approved.**  
**Epic:** [#8](https://github.com/SomeSunlight/Llama_Dispatcher/issues/8) — multi-engine orchestration and metrics.  
**First implementation issue:** [S00 #19](https://github.com/SomeSunlight/Llama_Dispatcher/issues/19) — tests/characterization only.

## Why
Llama Dispatcher is currently a llama.cpp-specific orchestrator/proxy. Speedy_Win now runs Qwen3.8 Flash Next IQ3_S through Strata on RTX 3090, exposed via local Strata `127.0.0.1:8080`, protected Caddy HTTPS and authenticated external `/strata/v1`; Goose and Open WebUI have been validated directly against it. Preserve that working baseline while developing an engine-neutral Dispatcher. Future engine candidates include EXL3 and other formats, but no third-engine driver is in scope.

## Decisions / invariants
- Every phase is an **owner gate**: open scoped PR, tests and local owner-run smoke test, explicit owner's acceptance, then merge; do not advance to a dependent phase or silently migrate another machine. At all times retain a usable accepted main and rollback route.
- Refactor behind **small backend adapters with declared capabilities**, not scattered `if strata` branches and not a full plugin marketplace. First protect and extract existing llama.cpp behavior.
- Maintain independent **logical alias**, **physical model/backend**, **config ownership**, **client policy**, **request context**, **process lifecycle**, and **telemetry source**. Preserve existing profile/default/instance/ensemble configuration precedence unless a migration explicitly changes it.
- Operational actions: **managed start**, **attach existing** (no kill rights), **graceful shutdown of owned backend**, **detach without shutdown**. Explicit process ownership; no mistaken launcher claims on attached runs.
- Permit heterogeneous engines **in parallel** (e.g. Strata + small llama.cpp) with explicit resource-admission policy to prevent GPU/VRAM/host RAM and Windows commit contention. Capability-specific native features remain available; absence must be explicit.
- Do **not** replace Strata's model download/packaging, `--data-dir`/`--models-dir`, optimizer/calibration, JSON native features, /metrics or Prometheus exporters. Prefer native integration; no automatic setup/download/calibration on normal serve. Preserve existing speed projection/vision and recent 131072/int8/kv-resident/2048 MiB configuration.
- Model/engine/data directories resolve through machine-specific runtime input; shared YAML must not contain absolute C:/... or /mnt/c/... roots. Separate Windows and WSL machine identities/history.
- **Client identity early:** distinct credentials for Goose, Open WebUI and future clients, tracked as client_id with safe key rotation, strict Caddy/Dispatcher trust boundary, no raw keys in Git/SQLite; no unverified attribution through User-Agent.
- Telemetry has four separate stages: client request, Dispatcher policy resolution, exact HTTP request forwarded, **engine-observed** facts. Existing `effective_params_json` historically means *forwarded* not necessarily internally applied; preserve provenance and unknown/null. No prompts/messages/outputs/Authorization in metrics.
- SQLite is the durable private telemetry store. Strata native JSON /metrics and /v1/status are primary for performance; log parsing only extra diagnostics. Consistent online backups and opt-in checked/sanitized snapshot publication to Git. No WAL/SHM or live DB tracking; Grafana postponed.
- Keep direct Strata Caddy route as diagnostic until the Dispatcher /v1 route and per-client auth tests pass. Security and performance must not regress.

## Ordered gates and dependencies
**Unchecked means not implemented or owner-approved**, NOT a request to start all items.

- [ ] **S00 — #19:** Characterization tests and owner-verified baseline for today's llama.cpp contract. First task; no production behavior changes.
**S00 in review, not accepted:** Draft [PR #20](https://github.com/SomeSunlight/Llama_Dispatcher/pull/20) characterizes baseline main commit `f0fa2e5b2d281f205b64da136ac5d810b396697a` (2026-10-16). Automated Ubuntu checks passed; owner smoke tests on Speedy_Win and Laptop_WSL and explicit approval are pending. No subsequent gate is authorized.

- [ ] **S01 — #9:** Engine interface and first LlamaCppBackend extraction. Requires S00 approval.
- [ ] **S02 — #10:** Independent client credentials/identities and explicit `default/enforce/passthrough` request policy. Requires S01. **Before Strata traffic is routed through Dispatcher.**
- [ ] **S03 — #11:** Strata adapter in `attached` mode with auth, proxy, reasoning semantics, streaming/tools/vision, no lifecycle takeover. Requires S01 + S02.
- [ ] **S04 — #12:** Generic run/config/provenance/metrics schema and additive migration. Can follow/partially overlap design of S02/S03, but implementation independently gated. Define recorded vs declared vs unknown.
- [ ] **S05 — #13:** Strata native /metrics and /status collection + SQLite history/deduplication. Requires S03 + S04.
- [ ] **S06 — #14:** SQLite online snapshot backup, retention and optional safe Git publication. Requires stable S04 migrations. Can be prioritized earlier if data-loss risk warrants it; independent approval.
- [ ] **S07 — #15:** Native Strata setup handoff, portable path roles, validated runtime config compilation/snapshots and drift preservation. Requires S03 + S04.
- [ ] **S08 — #16:** Managed lifecycle start/attach/detach/graceful shutdown + crash recovery and memory/resource guard. Requires S07 and S04, maintaining attached reference behavior.
- [ ] **S09 — #17:** Explicit native Strata calibration management and reporting; import existing results, production vs benchmark provenance. Requires S07 + S08 + S04.
- [ ] **S10 — #18:** Heterogeneous simultaneously active backend instances and resource-safe ensembles, e.g. Strata + small llama.cpp. Requires preceding shared interface/routing, lifecycle and data contracts.

Steps S04/S06 and S07/S09 may be reordered based on owner feedback **only by revising this plan and dependencies explicitly**. No two implementation gates are considered approved by one blanket acceptance.

## Separate instance-repository migrations (one owner approval each)
Migrate only after the relevant Dispatcher input schema and mixed-engine behavior have been owner-accepted; produce dry-run diffs and reversible commits. No migrations in this planning operation.

- [ ] [Speedy_Win #3](https://github.com/SomeSunlight/Llama_Dispatcher_Speedy_Win/issues/3) — preserve current 3090 llama.cpp model aliases and working Strata/Caddy setup; first integration trial.
- [ ] [Speedy_WSL #2](https://github.com/SomeSunlight/Llama_Dispatcher_Speedy_WSL/issues/2) — independent WSL/Linux paths, machine identity and model choices.
- [ ] [Laptop_Win #3](https://github.com/SomeSunlight/Llama_Dispatcher_Laptop_Win/issues/3) — constrained laptop and existing Windows engines/profiles.
- [ ] [Laptop_WSL #3](https://github.com/SomeSunlight/Llama_Dispatcher_Laptop_WSL/issues/3) — AI Workstation/aiw integration, Linux path semantics and separate metrics.

No central bulk migration or copying DBs across instances. Each issue owns review/rollback for that instance.

## Related, not part of this implementation
- Existing [#4](https://github.com/SomeSunlight/Llama_Dispatcher/issues/4) — host-memory startup diagnosis; coordinate rather than duplicate.
- Existing [#7](https://github.com/SomeSunlight/Llama_Dispatcher/issues/7) — engine vs profile ownership documentation; revisit during config generalization.
- [SomeSunlight/github-local #22](https://github.com/SomeSunlight/github-local/issues/22) — design native parent/sub-issue relationships in local Git-tracked issues. **Not to be implemented now.**

## Tracking hierarchy
GitHub supports native parent/sub-issues, but the currently connected GitHub issue tool does not expose the sub-issue linking operation. For now, epic #8 contains a readable Markdown issue checklist linking each task; this PLAN is the durable ordered dependency/acceptance map. A `1/2` title alone is not a reliable hierarchy.

## How to resume
Open epic #8 and the next unchecked issue. Read repository CONTEXT.md (generated; edit CONTEXT.src.md if context changes), supporting required Topic documents, README and current code. Implement **only that issue** on a feature branch with unit/integration tests and appropriate documentation. Provide a PR and succinct manual smoke instructions; await local owner feedback and explicit merge permission. After acceptance update this PLAN checkbox and record tested machines/commit/PR, then start the next approved gate.

**Next:** S00 #19, baseline tests, no production code refactor.