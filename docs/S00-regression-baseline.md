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

## IMPORTANT — before a live test, Dispatcher must already be running

**The S00 live test does not launch the Dispatcher.** It connects from a
**second terminal** to the proxy of an **already running llama.cpp Dispatcher**
on the same Windows/WSL environment. It never starts, switches, restarts,
downloads, stops or reconfigures a model. For a useful regression baseline,
**launch the Dispatcher exactly as it is normally used when it works**:
preserve the instance, ensemble/profile, binary/model roots, CLI overrides
and local engine configuration. Do not introduce a special test startup.

The first test on the renamed Windows instance is also a **migration sanity
check**. In particular, the Dispatcher may create a missing instance
directory instead of failing. **Check the instance repository and YAML before
launch**; do not allow a fresh empty folder to masquerade as a successful
Speedy_Win runtime.

### Known Speedy / Windows startup (owner-provided, NOT yet locally verified)

Run from the **Llama_Dispatcher core repository root** (not an independent
instance Git working directory). Before starting, check in PowerShell:

~~~powershell
Test-Path .\instances\Speedy_Win\instance.yaml
Test-Path .\instances\Speedy_Win\ensembles\3090.yaml
~~~

Both commands must return True. The independent repository
https://github.com/SomeSunlight/Llama_Dispatcher_Speedy_Win belongs under
instances/Speedy_Win. Then start **as supplied by the owner**:

~~~powershell
uv run src/dispatcher.py serve --ensemble 3090 --instance Speedy_Win --model-root c:\AI_Models\LLM\GGUF_Raw
~~~

Every supplied argument matters. In particular, do **not** silently change
--ensemble, --instance or --model-root, and do not add --bin-dir just because
an example in the instance README shows it: the actual installed engine
configuration already provides a bin_dir fallback. The renamed Speedy_Win
setup has **not yet been demonstrated to work**; record first-start problems
as first-start/configuration issues, rather than counting them as proven S00
runtime regressions.

On Laptop / WSL and Laptop / Windows, likewise use the **existing known-good
launch command** for that instance. No startup command has yet been confirmed
for those two environments. Do not copy Windows paths into WSL or share a
machine identity across them.

**Only after the Dispatcher reports a successful startup** should you open
another terminal in the same environment, check out PR #20 in the core
repository, and run the S00 smoke command below. Default proxy URL is
http://127.0.0.1:8001 (not the internal llama.cpp port 8081 or Strata).

### Capturing a replayable start/configuration baseline

The live runner now tries to read the **actual running Python Dispatcher
process command line** on Windows (Win32 process metadata) and WSL/Linux
(/proc). It verifies the requested --instance, records the **entire observed
process argv**, including all CLI overrides and paths, and fingerprints the
local instance YAML files and the Git revisions of core + instance. An OS
process command line is evidence of how that Python process was invoked,
but can differ from the original shell's uv run wrapper; it does not
independently prove which process owns the selected HTTP port.

On the **first successful run**, the runner saves the full command and
configuration fingerprint to reports/s00-INSTANCE.baseline.json, a
**Git-ignored, machine-private** manifest. On subsequent runs it compares
the observed command and configuration against this pinned baseline and
fails on drift. This helps ensure the future test is performed with the
same launch/configuration rather than merely receiving HTTP 200.
A changed Git checkout, configuration, Python path or CLI option is
meaningful and requires review.

If local process inspection is blocked, you can explicitly supply
--launch-command "FULL COMMAND HERE" to record the operator-declared
invocation instead. The report says user_declared_unverified: **this is not
proof of how the running process was started**. Inspect the manifest before
sharing it; it contains local paths and could include sensitive CLI flags.
The general PASS/FAIL report contains only the command hash, source and
non-secret summary, not the full argv. No manifests are committed or sent
to GitHub automatically.

To **intentionally** establish a new baseline after a verified change,
pass --rebaseline. The previous manifest is archived locally under a
timestamped name; the new launch/configuration is then pinned. Never
rebaseline simply to hide an unexplained difference. These manifests capture
the configuration files **at test time**; S00 cannot prove that files were
not edited after the server initially started.

The isolated unit tests and GitHub Actions do **not** need a running
Dispatcher. The live smoke is the second, machine-specific stage.

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

## Automated owner smoke — three installations

There are **two independent levels**:

1. The deterministic unittest regression suite runs in GitHub Actions on
   each PR (mock backends, no live model or OS-specific machine).
2. The **local live smoke** uses the HTTP interface of an **already running**
   Dispatcher. It cannot be executed in GitHub Actions because the private
   Speedy/Laptop machines are not connected to GitHub runners.

**Owner runs one command per installation** from the S00 branch in the core
repository. The script first executes the entire unittest suite, then checks
/v1/models, /debug/config, and /debug/preview for **every advertised
alias**. It compares model routing, sampling overrides, whole-object
chat_template_kwargs replacement, unmanaged-field pass-through and preview
output against the live Dispatcher configuration. No real model inference is
executed in the default mode. If --instance is supplied and its
instances/NAME/data/metrics.db exists, it checks schema v8 **read-only**
(without migrations, database copies or content disclosure). If the DB is in
another directory, this optional database check is reported as SKIP.

### One command on each machine

After the existing llama.cpp Dispatcher has started successfully in **one
terminal**, execute from a **second terminal** in the core repository root,
with PR #20 checked out:

| Machine | Required? | Command |
|---|---|---|
| Speedy / Windows | Yes | uv run --frozen python scripts/s00_verify.py --instance Speedy_Win |
| Laptop / WSL | Yes | uv run --frozen python scripts/s00_verify.py --instance Laptop_WSL |
| Laptop / Windows | Recommended if still working | uv run --frozen python scripts/s00_verify.py --instance Laptop_Win |

uv run --frozen uses the repository's lockfile and project environment;
there is no separate manual HTTP/SQL procedure. Each run ends with
[S00] PASS or [S00] FAIL and a readable list of automated checks.
The sanitized report is generated at reports/s00-NAME.json (Git-ignored).
It records test status, platform, alias counts, non-secret command SHA256,
configuration fingerprints and git commit IDs. The **separate local startup
baseline** stores the full observed launch command and should **not be shared
without review**. The general JSON report does **not** record prompts,
model responses, authorization headers, keys, private database contents or
complete request bodies. Reports can be inspected before sharing.

A normal live run **requires** --instance: this is also used to identify
and pin the actual running startup; it does not start that instance.
If the running Dispatcher uses a non-default proxy port, append
--base-url http://127.0.0.1:YOUR_PROXY_PORT. The URL must address the
**Dispatcher proxy**, not the internal llama.cpp server or the Strata/Caddy
route. The runner deliberately accepts loopback HTTP only and never uses
/switch or /stop. It does **not** discover or start a process.

If Laptop / Windows has already been retired, you can still run the isolated
regression suite without a live server:

~~~shell
uv run --frozen python scripts/s00_verify.py --instance Laptop_Win --unit-only
~~~

A live failure because the server is absent/starting is **not** automatically
an engine regression. The report shows the failing check; verify port and
current process, then repeat the **same** command.

### Optional real end-to-end inference

When an already running llama.cpp model is **safe to use** on that machine,
append --inference to the same command. The runner then also sends one
non-streaming and one streaming synthetic, **3-token** chat request through
the Dispatcher proxy. It validates response structure/SSE frames and records
only counts and success, not response text or prompts. This may **load a large
model** and consume GPU/RAM; it is opt-in and not required to exercise all
mocked streaming/cancellation/error cases (those run in the unit suite).
Default inference timeout is 300 seconds; adjust with
--inference-timeout 600 if genuinely needed. Inference can create normal
proxy telemetry rows in the running instance, as any client request does.
It never restarts, stops, downloads, switches or calibrates the backend.

### Acceptance protocol

- [ ] **Speedy_Win:** instance/ensemble directory verified, **renamed-instance
  first startup demonstrated**, normal startup command pinned, automated
  default run PASS, optional inference outcome.
- [ ] **Laptop_WSL:** known-good startup command pinned, automated default
  run PASS, optional inference outcome.
- [ ] **Laptop_Win:** known-good startup pinned if still active; otherwise
  mark not applicable (or unit-only). Do not bring up a retired model merely
  for S00.
- [ ] Owner reviews reported deviations / current known limitations, then
  gives **explicit S00 approval** before merge. The PR stays Draft until then.

CI and local smoke prove different things: unit tests isolate corner cases
(including the fragmented-SSE and HTTP-status limitations), whereas live smoke
verifies the currently running service's public contract. Neither proves a
future Strata adapter, and no S01 engine refactoring is performed here.

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
