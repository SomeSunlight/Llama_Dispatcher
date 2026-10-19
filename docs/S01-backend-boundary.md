# S01 — Backend boundary (llama.cpp compatibility gate)

**Status:** implementation proposed in the S01 PR; **not yet owner-accepted**. Canonical target architecture: [PLAN.md](../PLAN.md) and [runtime ownership contract](runtime-ownership-contract.md).

## What changes in S01

- `src/inference_backend.py` defines a minimal, typed `BackendCapabilities`, `InferenceBackend` protocol, `BackendEndpoint` descriptor, and the sole concrete `LlamaCppBackend`. The contract explicitly distinguishes known-supported, unsupported and unverified capabilities.
- Existing compiler calls (serve ensemble, direct profile, bench/eval) now enter through the concrete backend facade. Internally, the **same** `LlamaOrchestrator.compile_*` methods and native llama.cpp flags/INI remain authoritative. The indirection calls them dynamically, preserving `dispatcher.py`'s process-local Windows/WSL runtime-path/environment wrappers.
- The proxy constructs its legacy loopback `/v1/` destination through a backend-provided HTTP endpoint descriptor. All request policy, header behavior, streaming, response parsing and SQLite telemetry remain in the existing proxy path. The S00 proxy mocks without a `backend` attribute remain supported.
- The external **attach** contract exists only as a credential-free immutable HTTP endpoint *description* with `ownership=attached` and `may_control_process=False`. S01 does **not** probe, connect to, launch, stop or supervise external engines. `LlamaCppBackend.attach()` fails explicitly until a later gate defines the real implementation.
- Legacy llama.cpp subprocess launch, restart, termination, API switch/stop and database lifecycle **remain untouched** in `dispatcher_core.py`. That old behavior is a temporary compatibility bridge, not a second new supervisor.

## Boundaries deliberately not crossed

No Strata adapter or changes to Strata, Caddy, Open WebUI, engine-native model configuration, `uv.lock`, profiles, instance repos, databases/schema, generated ContextCanon output, authentication or client-policy semantics. No LaunchPlan v1 compiler in this gate (S07). No premature generic plugin registry or OS process manager (S08 belongs to an external project).

S00's characterized behavior and limitations (including fragmented SSE usage extraction and the current upstream-status response behavior) remain unchanged; correcting those requires a separately scoped, tested gate.

## Automated tests

```bash
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m py_compile src/dispatcher.py src/dispatcher_core.py src/inference_backend.py
uv run --frozen python scripts/s00_verify.py --unit-only --label S01
```

The new `tests/test_s01_backend_contract.py` exercises capabilities, dynamic compiler delegation, the existing managed HTTP URL, immutable no-kill attached endpoints, and invalid/credential-bearing URLs without launching processes.

## Owner local smoke tests — separate from productive Strata

On an existing **running** llama.cpp Dispatcher with your instance-specific startup command unchanged:

```bash
uv run --frozen python scripts/s00_verify.py --instance Laptop_WSL
```

Replace `Laptop_WSL` with each actual live Windows/WSL instance name, and run the corresponding shell on that host. S00 checks unit tests, live `/v1/models`, `/debug/config`, alias previews and pinned process command. Optional **tiny** inference only on a suitable llama.cpp test host:

```bash
uv run --frozen python scripts/s00_verify.py --instance Laptop_WSL --inference
```

Also compare the unchanged `serve --compile-only` output for a real ensemble/profile before/after the branch on the same instance, using your normal explicit `--bin-dir` and `--model-root` options; check INI, argv, aliases, defaults and process environment. Verify graceful existing stop and restart if feasible. Do **not** run inference on Speedy's productive Strata or change its Caddy route as part of S01.

**Rollback:** leave productive processes on the accepted `main` revision; reject/close the PR to abandon S01. If testing a checkout of the feature branch, restore `main` with your usual instance-safe procedure. No migration or SQLite schema rollback is needed.
