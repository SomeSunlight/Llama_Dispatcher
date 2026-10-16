# S00 / #19 — llama.cpp regression baseline

**Status:** Characterization only; awaiting local smoke tests and explicit owner
acceptance. **Do not merge or start S01 without approval.**

- **Epic:** https://github.com/SomeSunlight/Llama_Dispatcher/issues/8
- **Scope:** https://github.com/SomeSunlight/Llama_Dispatcher/issues/19
- **Baseline:** main commit f0fa2e5b2d281f205b64da136ac5d810b396697a
  (2026-10-16, planning commit).
- **Authority:** root CONTEXT.md, src/CONTEXT.md, its required Dispatcher
  operating reference, and actual source at the baseline commit. PLAN.md
  remains unchecked until approved and merged.

## Run deterministic regression tests

No GPU, GGUF model, Strata, Caddy, network access, secrets, or real instance
repository is required. Synthetic configuration directories, an in-memory
HTTP fake and temporary SQLite databases are used. Existing tests still run.

At the Dispatcher repository root (Windows PowerShell or WSL):

~~~shell
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -v
~~~

To run only S00 tests:

~~~shell
uv run --frozen python -m unittest discover -s tests -p "test_s00*.py" -v
~~~

The existing GitHub PR workflow runs the complete suite on Ubuntu and checks
the Python entry points; it does not replace local Windows/WSL acceptance.

## Observed llama.cpp contract

| Boundary | Behavior characterized |
|---|---|
| Configuration | Deep merge model defaults → instance engine defaults → profile; ensemble entry overrides; CLI ad-hoc override has highest priority. |
| Paths | Instance engine settings beat fallback templates; launcher --bin-dir beats engine bin_dir; --model-root expands the model placeholder (environment is fallback). Executable suffix depends on OS. |
| Compile-only | Ensemble generates real-model INI sections, router CLI --models-preset and INI hash; proxy-only aliases do not add model sections. Single profile compiles direct CLI args, without router INI. |
| Public API | /v1/models exposes real plus proxy-only aliases. /debug/preview simulates without forwarding. |
| Policy | For configured alias, sampling and chat_template_kwargs replace client values; chat_template_kwargs is one whole object, not a recursive merge. Unmanaged fields pass through. |
| Telemetry | Client intent, resolved profile, target alias, forwarded control snapshot and diff remain distinct. Message/prompt/input content is excluded from the parameter snapshots. Forwarded != engine-observed. |
| SQLite | PRAGMA user_version=8; table metrics_proxy_requests; view v_proxy_request_summary and runtime performance views. Execution runs record effective binary/version/CLI; loaded models get separate runtime IDs. |
| Migration | Certain historical req_* fields were already effective values and may be copied to effective_*; unknown historical client aliases, client snapshots, policy origins and unrecoverable binary paths remain NULL. |
| Lifecycle | Child logs can supply spawned alias/port/effective args. Single-profile mode records one model instance. /stop terminates an active managed child and waits. Reader cancellation propagates. |
| Crash | An unexpectedly ended single-profile process within 45 seconds uses fatal process exit; ensemble threshold is 15 seconds. Tests stub process exit. |

### Known limitations / bugs (document only in S00)

1. **Fragmented SSE:** proxy parses data lines independently per received byte
   chunk. Split JSON SSE events still forward byte-for-byte, but usage and
   finish_reason may be missed. The regression test deliberately captures this.
2. **Upstream status:** proxy StreamingResponse is initially HTTP 200 even if
   llama.cpp returned e.g. HTTP 502. SQLite may accurately log 502 while the
   client sees HTTP 200. Errors in streamed forwarding are logged in finally;
   if no upstream response was seen, the initial audit status is 200.
3. **TTFT:** first *network chunk* is measured, not necessarily first token.
4. **Provenance:** compiled alias/profile policy does not carry the exact YAML
   layer responsible for each setting. Unknown and observed facts must remain
   distinct (particularly if S01 introduces additional backends).
5. **Compile-only side effects:** does not start llama.cpp but writes a
   generated INI and initializes the local MetricsDatabase. Do not regard it
   as a read-only operation on an existing instance.
6. **Ownership:** current lifecycle assumes Dispatcher-managed llama.cpp.
   Attaching/detaching externally managed engines is outside S00.
7. **Older docs drift:** historical prose mentions proxy_requests or fresh
   schema only; the implemented table is metrics_proxy_requests and there are
   additive migrations. This document does not edit generated context or
   reinterpret historical data.

## Owner smoke test — Speedy_Win and Laptop_WSL

Test on each machine using its **existing working** llama.cpp Dispatcher
launch configuration. No model download, Strata restart, direct Caddy change,
engine switch or instance migration. The probes below assume the Dispatcher
proxy is already running, not the internal llama.cpp server.

- [ ] Checkout the PR branch in the **core** repository only. Run the full
  unittest command above and record pass/fail and OS. Do not modify the four
  independent instance repositories.
- [ ] Compare existing runtime invocation (--instance, ensemble/profile,
  --bin-dir, --model-root as applicable). Do not post machine-private paths,
  keys, or Authorization headers to GitHub.
- [ ] GET /v1/models from the existing Dispatcher proxy port: verify real and
  proxy-only aliases, without exposing internal model paths.
- [ ] POST /debug/preview with a synthetic prompt and one alias observed
  in /v1/models. Verify original_model, forwarded_model, injected_params,
  overridden_by_client and forwarded_body. No inference is executed.
- [ ] Optional, only if inference is already safe: send one tiny synthetic
  chat request to the running Dispatcher proxy, then inspect the newest
  row in v_proxy_request_summary using a DB viewer or a DB copy. Do not
  restart the process or run expensive benchmarks.
- [ ] Report machine, unittest result, inspected alias, and discrepancies in
  PR/#19. Give explicit acceptance (or requested changes); no merge before it.

PowerShell example (replace port and model alias):

~~~powershell
$base = "http://127.0.0.1:8001"
Invoke-RestMethod "$base/v1/models"
$body = @{model="YOUR_ALIAS"; messages=@(@{role="user";content="S00 test"}); temperature=0.9} | ConvertTo-Json -Depth 6
Invoke-RestMethod "$base/debug/preview" -Method Post -ContentType "application/json" -Body $body
~~~

WSL example (replace port and model alias):

~~~bash
base=http://127.0.0.1:8001
curl -fsS "$base/v1/models"
curl -fsS "$base/debug/preview" -H 'Content-Type: application/json' \
  -d '{"model":"YOUR_ALIAS","messages":[{"role":"user","content":"S00 test"}],"temperature":0.9}'
~~~

Read-only SQL inspection **on a DB copy** (do not commit DB/WAL/SHM):

~~~sql
SELECT machine_id, timestamp, client_model, target_model,
       changed_parameter_count, status_code
FROM v_proxy_request_summary
ORDER BY timestamp DESC LIMIT 5;
~~~

## S01 adapter-boundary proposal (design only, not implementation)

The natural seam is **compiled Dispatcher intent ↔ backend runtime**.
Dispatcher should continue owning public aliases, client policy, provenance,
forwarded-request snapshots and shared persistence. Behind a small
capability-declaring llama.cpp adapter, isolate engine-specific binary/INI/CLI,
environment, subprocess ownership and start/stop, child-log parsing, and
engine-native telemetry. Attached vs managed operation must be explicit; do
not assume termination rights over an externally managed process. Avoid
scattered engine-type conditionals and avoid premature plugin infrastructure.

Hotspots: src/dispatcher.py runtime monkeypatch installation;
src/dispatcher_core.py compile_serve_ensemble, compile_serve_profile,
_router_cli_args, _read_server_json_stream, run_server_loop,
run_profile_server_loop, proxy_to_llama, debug_preview;
src/database_manager.py _init_db, _upgrade_schema, insert_proxy_request.

**This S00 PR changes no production Python, generated CONTEXT, instance
configuration, model setup, or database stored in Git.**
