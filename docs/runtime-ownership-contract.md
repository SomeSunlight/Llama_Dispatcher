# Runtime ownership and LaunchPlan handoff (proposed architecture)

**Status:** design proposal accompanying [PLAN.md](../PLAN.md), 2026-10-19. **Not implemented.** Existing behavior and owner-approved S00 baseline remain authoritative until each implementation gate is accepted.

## 1. Responsibilities and transition

The Dispatcher is a **compiler of model/ensemble intent** and an **HTTP proxy/observer**, not the final OS process supervisor.

- **Dispatcher owns:** existing model/engine/profile/ensemble resolution, native engine parameter mapping, logical aliases, per-client request policy, HTTP routing and inference-side telemetry.
- **External manager owns:** whether and when a service is running; process PID/identity, child tree, restart/stop rights, readiness and OS resources. May use Process Compose or native OS facilities; tooling selection requires a Windows experiment.
- **Native engine owns:** model packaging, runtime interpretation, calibration/optimizer decisions, supported endpoint behavior.
- **Client owns:** requests to the Dispatcher (or, during phased rollout, existing direct Strata endpoint). No implicit lifecycle rights from an inference request.

The long-term Dispatcher operates **attach-only** to engine endpoints, with explicit no-kill semantics. The current llama.cpp managed-start paths are a *compatibility bridge* and remain untouched in S01; never remove them before a verified substitute and an explicit owner sign-off. The already running Speedy Strata must be attach-only from the first integration and keep its currently working Caddy access as a rollback path.

### Health is not supervision

A Dispatcher `/health` probe may answer whether an attached backend is usable for routing. It **must not** restart, schedule or kill that backend. If the backend vanishes, the Dispatcher records unavailable and reports an explicit proxy error; the external manager independently decides on restart according to its own policy.

## 2. Candidate contract: LaunchPlan v1

The Dispatcher accepts an instance, ensemble, and machine-local roots, applies the **existing precedence rules**, validates native capabilities, and produces a deterministic, **secret-free** JSON plan. This is not the same as putting launcher settings into shared profiles.

Illustrative proposed command (not implemented):

```text
dispatcher plan --instance Speedy_Win --ensemble <selected> --format json --model-root <local-root> --bin-dir <local-bin>
```

Minimal *illustrative* response (placeholders are not actual Speedy paths/flags):

```json
{
  "schema_version": 1,
  "instance": "Speedy_Win",
  "ensemble": "<selected>",
  "plan_digest": "<sha256-of-normalized-plan>",
  "services": [
    {
      "id": "engine-strata-primary",
      "backend": "strata",
      "argv": ["<absolute-strata-executable>", "--data-dir", "<local-strata-data-dir>"],
      "cwd": "<local-working-directory>",
      "env_refs": ["STRATA_PRIVATE_KEY"],
      "endpoint": "http://127.0.0.1:8080",
      "readiness": {"method": "GET", "path": "/v1/models"},
      "generated_artifacts": [],
      "desired": {"role": "inference-engine"}
    }
  ],
  "aliases": [
    {"public_alias": "agent", "service_id": "engine-strata-primary"}
  ]
}
```

**Not final schema:** fields, versioning and engine-specific execution details require S07 tests. For Strata preserve its native `--data-dir`, model directories and valid JSON/config files instead of fabricating llama.cpp-compatible flags. For llama.cpp preserve existing router INI and engine flags and the exact chosen executable. `argv` is an **array** and must never be shell-interpolated.

Plan includes:
- executable + argv (ordered), working directory, **credential references** (not secret values), environment policy and resolved platform-specific paths;
- expected endpoints, readiness/capability probes, generated non-secret artifact path + digest and stable plan identity;
- a representation of aliases/routing distinct from real physical processes (proxy-only aliases **do not** start extra engines);
- explicitly declared resource hints where known; **unknown** values must not become invented RAM/VRAM guarantees.

Plan excludes:
- tokens, API keys, client prompts/results and private model content;
- OS-specific process ownership decisions, restart-policy defaults, background supervision logic;
- side effects (no process start, engine model download, calibration, Caddy reload or DB migration during compilation).

## 3. Execution report: independent, observed facts

After executing a plan, the supervisor can publish a **run receipt**, again without secrets. Candidate fields:

```json
{
  "schema_version": 1,
  "plan_digest": "<sha256-of-normalized-plan>",
  "service_id": "engine-strata-primary",
  "owner": "local-ai-services",
  "process_id": 12345,
  "process_start_time_utc": "<observed-timestamp>",
  "endpoint": "http://127.0.0.1:8080",
  "readiness": "ready",
  "observed_executable": "<absolute-executable>",
  "observed_command_digest": "<hash>",
  "observed_engine_version": null
}
```

**An attached run is never recorded as launched by Dispatcher**. Attach can work even without this receipt (as it does for today's direct Strata setup); provenance should show `source=attached-observed` and unknown lifecycle details where necessary. Do not trust a PID alone for ownership: verify creation time and executable/config identity. Windows and WSL are separate operating contexts; PID and system path values are not portable identifiers.

## 4. Configuration ownership and precedence

Preserve current `defaults → engine → profile → ensemble → explicit CLI overrides` rule. Machine-local executable/model/data roots arrive as runtime inputs to plan compilation, without leaking `C:\\` or `/mnt/c/` into shared profiles.

- Profile stores model-specific inference intent.
- Engine layer stores backend/hardware-level intent (including native engine-specific environment settings), but not secrets.
- Ensemble identifies *physical backend instances* and *logical public aliases*. Multiple aliases may refer to one already-running Strata process.
- External manager profile config stores process scheduling, service autostart, monitoring, CPU priority and resource-admission rules. **It must not reproduce model generation/ensemble parameters.**
- Native Strata settings belong to Strata and must survive pass-through and updates without accidental rewriting.

Per-client sampling/reasoning policy is applied to **requests by Dispatcher**, not baked into OS start commands unless an engine-native startup option actually owns that property.

## 5. Testing and release boundaries

### S01–S03 first, without external supervisor dependency

1. Preserve S00 unit and manual-regression behavior, including existing llama.cpp managed-serve.
2. Verify attached Strata capability, streaming/SSE framing, tool call data, long reasoning, cancellation, image payloads, and correct explicit errors.
3. Protect incoming Goose/Open WebUI clients with separately attributable authentication before replacing the direct Caddy route.
4. Confirm non-invasive attachment: no Strata restart, no modified native configuration, no unknown parameter suppression or silent model change.
5. Allow Caddy diagnostic direct-route rollback until accepted production proxy cutover.

### S07–S08 integration later

1. Golden tests for compiler output deterministic across repeated invocations and stable equivalent configs.
2. Negative tests for missing root, invalid config, mismatched capability, altered native file and credential leakage; `plan` compilation never starts a service.
3. Manager starts process; Dispatcher attaches and independently validates backend. Verify attached process cannot be killed by Dispatcher API/CLI.
4. Record declared plan, observed receipt and effective native engine data separately. Mismatches are surfaced without invented equivalence.
5. Verify supervisor recovery and RAM/Windows commit/VRAM admission on Speedy; test path portability under WSL separately.
6. Transition the current llama.cpp managed mode only in a standalone, owner-approved migration; preserve rollback on every machine.

## 6. Explicitly out of scope

- Writing a second cross-platform supervisor inside Dispatcher.
- Forcing slow laptop inference into a production requirement; the laptop is a client of Speedy where appropriate.
- Replacing validated Strata native calibration, packaging or existing Caddy security.
- Launching MCP tools as arbitrary shell commands from an unrestricted LLM request.
- Deploying a particular supervisor before compatibility and graceful-stop tests pass.

Related issues: [#8](https://github.com/SomeSunlight/Llama_Dispatcher/issues/8), [#9](https://github.com/SomeSunlight/Llama_Dispatcher/issues/9), [#11](https://github.com/SomeSunlight/Llama_Dispatcher/issues/11), [#15](https://github.com/SomeSunlight/Llama_Dispatcher/issues/15), [#16](https://github.com/SomeSunlight/Llama_Dispatcher/issues/16), [#18](https://github.com/SomeSunlight/Llama_Dispatcher/issues/18).
