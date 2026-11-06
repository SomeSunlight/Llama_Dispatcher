# S03 — Strata HTTP attach (isolated review candidate)

**Gate:** [#11](https://github.com/SomeSunlight/Llama_Dispatcher/issues/11).
Prerequisites S00–S02 and the [PR #26](https://github.com/SomeSunlight/Llama_Dispatcher/pull/26) baseline are accepted.
This feature is **opt-in** and is **not** a Speedy/Caddy migration.

## Ownership and configuration

Dispatcher proxies an **already running** Strata service over HTTP(S). There is
no `Popen`, native engine launch, model download, restart, explicit autoload request,
calibration, unload, shutdown or child-process ownership in this path. Native Strata may still lazy-load its own model in response to inference, under its own externally managed configuration.
`/stop` and `/switch` return 409 in attached mode. Native Strata remains
configured and supervised elsewhere. Existing managed llama.cpp `serve`,
`bench`, `eval`, and its S00–S02 proxy behavior remain unchanged.

Create a **private** UTF-8 JSON outside every Git repository; for example,
`%LOCALAPPDATA%\Llama_Dispatcher\strata-attach.json` under Windows.
This example is an explicit temporary S03 attach configuration: full
native compilation/ensemble/profile unification is **not** claimed (S07).

```json
{
  "schema_version": 1,
  "endpoint": "http://127.0.0.1:8080",
  "credential_env": "STRATA_NATIVE_KEY",
  "aliases": {
    "agent": {
      "model": "strata",
      "parameters": {"reasoning_effort": "low", "temperature": 0.2}
    },
    "sparringpartner": {
      "model": "strata",
      "parameters": {"reasoning_effort": "high", "temperature": 0.6}
    }
  }
}
```

The native model ID (`strata` here) must match the running endpoint's
`GET /v1/models`; it is **not** a second model/process. The per-alias
`parameters` fields are request-policy intent, not native startup arguments.
Use the accepted S02 `enforce`, `default`, or `passthrough` identity policy.
The native credential is read from the named **environment variable** by
Dispatcher at startup, never from JSON or client-supplied headers.
**Both** the S02 client authentication file (`DISPATCHER_CLIENT_CONFIG`)
and a valid native credential environment variable are mandatory for attach
startup; the two credentials are independent. Do not place raw tokens in
scripts, issue bodies, committed configuration, CLI arguments, or logs.
Secure the private JSON and environment provisioning on the local machine.

Only loopback HTTP endpoints are allowed; remote endpoints require HTTPS.
The upstream does not follow redirects. No untrusted client authentication,
cookie, identity or forwarding headers reach Strata. `reasoning_effort`
and `chat_template_kwargs.enable_thinking` are mutually exclusive after
client/alias policy resolution; conflicting requests receive 400 rather than
being silently modified. Arbitrary native request content (tools, messages,
images, supported extensions) is passed through, but not persisted in SQLite
or diagnostics. Configure only verified native fields.

## Laptop-first smoke (optional native model)

Start Strata **yourself** on a non-production endpoint, with its normal
native launcher and a small supported model if your laptop can safely run it.
Do not start Strata from Dispatcher. On Laptop/Windows PowerShell, after
privately provisioning S02 client tokens and the native key environment variable:

```powershell
$env:DISPATCHER_CLIENT_CONFIG = Join-Path $env:LOCALAPPDATA "Llama_Dispatcher\clients.json"
uv run --frozen python src/dispatcher.py serve --instance Laptop_Win --api-port 8001 --strata-config (Join-Path $env:LOCALAPPDATA "Llama_Dispatcher\strata-attach.json")
```

In WSL, use its own **independent instance**, environment variables, paths,
runtime setup and running Strata endpoint; do not pretend that a Windows-host
service or credentials are automatically available in WSL. Test *simulated*
Goose/Open WebUI identities first: real Goose/Open WebUI are not present on
Laptop/Windows in this development window.

- `GET /v1/models` reports **public aliases** from Dispatcher.
- `GET /debug/strata` performs **read-only** `/health`, `/v1/status`,
  `/v1/models` probes of the already-running endpoint. Unverified
  capabilities remain unknown, not fabricated. All `/debug/*` routes
  require S02 client authentication.
- `POST /debug/preview` redacts prompt/tool/image content and shows
  effective native model, injection and the selected client policy.
- Test one nonstream and one stream chat/completions request with a distinct
  S02 client token; inspect actual status, SSE framing, tool calls, reasoning,
  vision payloads and audit records. Inspect SQLite with
  `run_id = NULL`: **not** Dispatcher-launched.
- Stop the externally managed **test** Strata yourself and verify Dispatcher
  returns a coherent 503 without spawning it. The external owner alone
  restarts it. A stopped/unloaded Strata might advertise auto-load; do not
  conflate endpoint discovery with native model readiness.

## Speedy real-HTTP acceptance (owner gate, 2026-11-01)

Run this **locally in PowerShell 7 on Speedy/Windows**. Keep its existing
native Strata (127.0.0.1:8080) and direct Caddy route exactly as they are.
Use a **separate clone/check-out of PR #27** and a **new private instance
`Speedy_S03_Test`**, so the test does not touch existing Dispatcher instances
or their SQLite databases. Only the test Dispatcher listens on 127.0.0.1:18001;
neither it nor the smoke runner owns the already-running Strata process.

The smoke runner refuses remote/non-loopback Dispatcher URLs. For tests from
the laptop, use an SSH tunnel or the existing authenticated Caddy route only
after the local gate passes. Do **not** repoint production clients yet.

### One-command smoke (recommended)

In PowerShell 7 on Speedy, work from a **separate checkout** of PR #27:

```powershell
git clone --branch feature/s03-strata-attach-issue11 `
    https://github.com/SomeSunlight/Llama_Dispatcher.git Llama_Dispatcher_S03
cd Llama_Dispatcher_S03
uv sync --frozen
./scripts/s03_speedy_smoke.ps1
```

The command securely asks for the **existing native Strata API key** if
`STRATA_NATIVE_KEY` is not already set, discovers Strata's real model ID,
generates an isolated, disposable S02 client token, starts its own loopback
test Dispatcher, performs *read-only* HTTP discovery/auth/policy checks and
stops **only the test Dispatcher**. It leaves native Strata and Caddy alone.

When that passes, explicitly opt into two small **real** Strata requests and
SQLite verification:

```powershell
./scripts/s03_speedy_smoke.ps1 -Inference
```

A sanitized report is kept at `%LOCALAPPDATA%\Llama_Dispatcher\S03\`.
This test may use Strata's existing model/VRAM/CPU, but does not launch,
restart, calibrate or change the native service. If its loopback port 18001 is
already occupied, stop only the *previous disposable test Dispatcher* or choose
another port via `-DispatcherPort 18002`. Do not stop the production Strata
service. Existing Speedy production routes stay unchanged.

**The manual procedure below is optional.** Use it to inspect every stage,
leave a test Dispatcher running for Goose/Open WebUI experiments, or control
the environment more precisely.

### Manual step-by-step setup

In PowerShell, from the separate PR-branch checkout:

```powershell
# Set to your actual separate PR checkout on Speedy.
$repo = (Get-Location).Path
$private = Join-Path $env:LOCALAPPDATA "Llama_Dispatcher\S03"
New-Item -ItemType Directory -Force $private | Out-Null

# Reuse Strata's already-configured native API key, without printing it.
# Only if this shell does not already have STRATA_NATIVE_KEY:
if (-not $env:STRATA_NATIVE_KEY) {
    $secret = Read-Host "Existing native Strata API key" -AsSecureString
    $env:STRATA_NATIVE_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
}

# Discover the *real* Strata model ID; do not assume that it is 'strata'.
$models = Invoke-RestMethod -Uri "http://127.0.0.1:8080/v1/models" `
    -Headers @{ Authorization = "Bearer $env:STRATA_NATIVE_KEY" }
$nativeId = $models.data[0].id
if (-not $nativeId) { throw "No native model advertised by running Strata." }
Write-Host "Native model ID: $nativeId"

# A disposable S02 test identity: keep the token in an environment variable;
# persist only its hash in the private client-auth JSON.
$env:S03_SMOKE_CLIENT_TOKEN = [Convert]::ToHexString(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$bytes = [Text.Encoding]::UTF8.GetBytes($env:S03_SMOKE_CLIENT_TOKEN)
$digest = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
$env:DISPATCHER_CLIENT_CONFIG = Join-Path $private "s03-smoke-clients.json"
@{
    schema_version = 1
    clients = @(@{ id = "s03-smoke"; token_sha256 = $digest; policy = "enforce" })
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $env:DISPATCHER_CLIENT_CONFIG

$attach = Join-Path $private "s03-smoke-attach.json"
@{
    schema_version = 1
    endpoint = "http://127.0.0.1:8080"
    credential_env = "STRATA_NATIVE_KEY"
    aliases = @{
        agent = @{ model = $nativeId; parameters = @{ temperature = 0.2 } }
    }
} | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $attach

# Keep the test server in an isolated background PowerShell process.
# Stopping the Job stops only this test Dispatcher, not native Strata.
$job = Start-Job -ScriptBlock {
    param($root, $attachPath, $clientFile, $nativeKey)
    $env:DISPATCHER_CLIENT_CONFIG = $clientFile
    $env:STRATA_NATIVE_KEY = $nativeKey
    Set-Location $root
    uv run --frozen python src/dispatcher.py serve `
        --instance Speedy_S03_Test --api-port 18001 --strata-config $attachPath
} -ArgumentList $repo, $attach, $env:DISPATCHER_CLIENT_CONFIG, $env:STRATA_NATIVE_KEY
```

Check that the Job remains running before sending requests:

```powershell
Get-Job $job
Receive-Job $job -Keep
```

The test instance directory and SQLite database are created under
`instances/Speedy_S03_Test/data/metrics.db` by the Dispatcher; they do not
belong to the existing Speedy_Win production instance.

**First:** read-only discovery/auth/policy tests and locally denied management
route, **no inference**:

```powershell
$db = Join-Path $repo "instances\Speedy_S03_Test\data\metrics.db"
uv run --frozen python scripts/s03_live_smoke.py `
    --base-url http://127.0.0.1:18001 --alias agent
```

**Then, only when ready:** two tiny *real* Strata calls (nonstream and
streaming), followed by a read-only inspection of SQLite records for exactly
this test client and the selected alias:

```powershell
uv run --frozen python scripts/s03_live_smoke.py `
    --base-url http://127.0.0.1:18001 --alias agent `
    --client-id s03-smoke --db $db --inference `
    --report (Join-Path $private "s03-live-report.json")
```

The report records only codes, alias/model identity, selected policy, bounded
timing/event counts and sanitized SQLite metadata. It saves **no bearer key,
prompt, tools or generated response content**. If a smoke check fails, report
its error and the relevant **redacted** Strata/Dispatcher logs; do not paste
private credentials.

To stop **only** the test Dispatcher:

```powershell
Stop-Job $job
Receive-Job $job -Keep
Remove-Job $job
```

The direct Caddy /strata/v1 route remains untouched. Before a production
cutover, separately test the real Goose/Open WebUI endpoints, client
credentials, long reasoning/tool traces, SSE cancellation, vision and actual
native behavior/response quality. Two tiny chat calls are necessary evidence
for HTTP attach, **not** complete production acceptance.

## Existing Caddy gateway trial for real Goose on Laptop/WSL (2026-11-02)

The owner's working Caddy already has a separate `/v1/*` Dispatcher upstream
on loopback port **8001**, and a **direct** `/strata/v1/*` native Strata route
on **8080**. Goose can use the already established HTTPS address; a new public
route, SSH tunnel or forwarding port is **not** required.

**One necessary adjustment:** Caddy's old Dispatcher block explicitly had
`header_up -Authorization`, removing its validated Bearer header before
Dispatcher. In S02 mode that produces HTTP 401. Caddy must instead forward
the validated Authorization header *only* to the S03 Dispatcher. This is a
temporary **single shared** `home-gateway` client identity: existing Goose,
Open WebUI and other callers using that shared key cannot yet be
distinguished as separate clients. Do not invent identities based on
User-Agent or `X-Client-ID`. A later separate S02/Caddy multi-client
credential migration will be a distinct owner gate.

**Important Caddy security:** `{$SPEEDY_API_KEY}` in the current Caddyfile
is substituted from the **reload command's environment**, not magically
inherited from the already-running Caddy process. Reloading by hand without
provisioning the key can silently change or disable the gateway's Bearer
check. The opt-in script below decrypts the owner's existing DPAPI secret
*in memory*, sets the necessary environment for validate/reload, and
verifies Caddy's exact unauthenticated 401 before considering the
transition successful.

### A. Speedy, PowerShell 7.4 — own console, leave running

Open a **separate S03 PR checkout**; the existing Strata/Caddy must already
be running as before. Confirm the old process is **not** listening on port
8001; the new script explicitly refuses an occupied port and never kills
it:

```powershell
./scripts/s03_speedy_gateway.ps1 -DpapiKeyFile 'C:\Caddy\speedy-api-key.dpapi'
```

This creates private **local** JSON under
`%LOCALAPPDATA%\Llama_Dispatcher\S03\gateway\`, hash-only S02 client
credential configuration, and a separate `Speedy_S03_Stage` instance/
SQLite database under the isolated PR checkout. The native API key is
recovered from the existing DPAPI secret (same Windows account), passed
only via process environment, and not persisted in JSON. The dispatcher
runs on `127.0.0.1:8001`, independently of Strata. The default public
alias is `agent`; it maps to Strata's actual `/v1/models` ID.

The test identity uses `passthrough` and **no extra alias sampling
parameters** so Goose's previously working direct-Strata generation
settings are not silently overridden. In later tests, introduce a separate
policy-controlled alias; do not add low `max_tokens` overrides to a
reasoning model. The S03 one-shot smoke already separately exercises
`enforce` and audit traces.

### B. Speedy, second PowerShell — inspect then explicitly apply Caddy edit

This script changes **one** upstream header directive and preserves the
original upstream 8001, both routes, and the current DuckDNS token
unchanged in content (the file may be re-encoded as UTF-8). It **never commits, prints or
uploads** the user's Caddyfile or API keys. Dry-run first:

```powershell
./scripts/s03_caddy_gateway.ps1 -Caddyfile 'C:\Caddy\Caddyfile'
```

Only when the staged S03 Dispatcher is running on 8001:

```powershell
./scripts/s03_caddy_gateway.ps1 `
  -Caddyfile 'C:\Caddy\Caddyfile' `
  -CaddyExe 'C:\Caddy\caddy_windows_amd64_custom.exe' `
  -DpapiKeyFile 'C:\Caddy\speedy-api-key.dpapi' `
  -ApiBaseUrl 'https://YOUR-EXISTING-DOMAIN' -Apply
```

The script makes a timestamped **LOCAL** Caddyfile backup, validates and
reloads only with the secret available, and checks Caddy's 401 anonymous /
200 authenticated `/v1/models` behavior. If validation/reload or that
verification fails it restores the previous Caddyfile and attempts to
reload the old configuration. The Caddy backup may include an actual DNS
token; keep it out of Git and review external shares carefully.

### C. Laptop/WSL — real Goose acceptance

Continue using the **existing Caddy HTTPS host**; configure Goose's
OpenAI-compatible provider through `aiw goose configure` (native Goose
settings inside the existing container) to use the **existing**
`https://YOUR-EXISTING-DOMAIN/v1` path rather than direct
`/strata/v1`. Select the **public Dispatcher alias `agent`**, not
Strata's internal model ID. Reuse the current **gateway Bearer secret**
that was already used for authorized HTTPS calls; do not paste it into
GitHub or reports.

For a meaningful owner gate, execute a **representative Goose task with
tools**, compare the actual outcome to the known working direct Strata
path, and inspect the *separate staging instance's* `metrics.db` for
client ID `home-gateway`, native target, `run_id=NULL`, request policies,
statuses, tokens and SSE behavior. The shared key **cannot establish**
that each row came specifically from Goose. Real per-client attribution
requires distinct credentials in a later gate.

### Rollback / limits

To retain the working direct route, Goose can immediately be pointed back
to `/strata/v1`; the Caddy routing for that path never changes.
The stage Dispatcher is **foreground-only** in the first console: closing
it or pressing Ctrl+C stops that listener, so `/v1` is then unavailable
until the previous Dispatcher returns.

**Before restarting any legacy unauthenticated Dispatcher on 8001, undo
the S02 Authorization forwarding.** Otherwise Caddy would pass its shared
Bearer secret into the legacy, potentially permissive proxy. The same
Caddy script supports explicit and verified restoration:

```powershell
./scripts/s03_caddy_gateway.ps1 -Caddyfile 'C:\Caddy\Caddyfile' -Revert
./scripts/s03_caddy_gateway.ps1 `
  -Caddyfile 'C:\Caddy\Caddyfile' `
  -CaddyExe 'C:\Caddy\caddy_windows_amd64_custom.exe' `
  -DpapiKeyFile 'C:\Caddy\speedy-api-key.dpapi' `
  -ApiBaseUrl 'https://YOUR-EXISTING-DOMAIN' -Revert -Apply
```

This re-establishes the original `header_up -Authorization` while
checking Caddy's public 401 and the separately authenticated direct
Strata route. It can run with the test Dispatcher stopped; it does not
need an active legacy backend. Only after this reversion, return
to the accepted legacy start path.

This temporary foreground trial is intentionally **not**
the final persistent host supervisor. Do not run it as a Windows
startup task or replace the working Strata/Caddy start script.
Full lifecycle management belongs to the AI Workstation's Process Compose
integration ([#34](https://github.com/SomeSunlight/ai-workstation/issues/34)).

**Open questions for final acceptance:** distinct client identities, native
tool/reasoning/vision behavior on long Goose jobs, Caddy streaming and
disconnect/cancellation, request and response content omission from logs,
and operator recovery after errors. PR #27 should not merge or be treated
as productive cutover before owner sign-off.

## Automated review evidence

No native model is required for the deterministic tests:

```bash
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python scripts/s00_verify.py --unit-only --label S03
```

`tests/test_s03_strata_contract.py` uses `httpx.MockTransport` for
read-only probing, independent upstream credentials, two aliases, request
reasoning collision, tool and image transparency, raw SSE framing/usage,
HTTP status codes, 503 when offline, and control-route no-kill semantics.
Previous S00 tests intentionally pin the **different legacy llama.cpp**
status/SSE behavior.

## Unresolved owner gates, not CI success

The following are **not proven by mocked or small laptop tests**: native
Strata model-specific reasoning semantics, a 131072-token context, long
tool-using sessions, cancellation under load, effective vision behavior,
performance on Speedy, and the real Goose/Open WebUI/Caddy ingress.
A successful S03 PR review cannot be represented as production cutover.
See the per-instance owner gates in PLAN §6.

**Rollback:** stop only the test Dispatcher (not Strata); run the accepted
`main` build with its original llama.cpp serve configuration, or retain the
direct Strata diagnostic Caddy `/strata/v1` route on Speedy. No schema
migration, native Strata settings or instance files are changed by the PR.

## Separate S02 application keys before native host startup (review issue #41)

**Review-only extension**: [multi-client S03 draft PR #30](https://github.com/SomeSunlight/Llama_Dispatcher/pull/30)
allows a separately configured Windows AI Workstation host to start the
S03 attached Dispatcher with a **pre-existing hash-only** S02 registry.
It never generates or transports original application keys.

An existing S03 launch with no additional input still creates a
single `home-gateway` transitional identity. For the multi-client
path, add either an absolute `-ClientConfig '<private-clients.json>'` argument
to `scripts/s03_speedy_gateway.ps1`, or provide the *nonsecret*
`DISPATCHER_CLIENT_CONFIG` environment variable before invoking the
script. If an explicit path is given, the path must exist and contain
an S02 digest file; invalid/missing files **abort startup** rather than
downgrading to the old shared key. Generated S02 original keys and native
Strata's protected key stay separate; the S03 script only **reads**
the external digest file, without rewriting it. Use separate client IDs
for each Goose/Open WebUI application and an optional imported legacy
key for rollback.

### Offline Caddy preparation (no running services)

The previous Caddy gateway checked one old Bearer key for both Dispatcher
`/v1/*` and direct native Strata `/strata/v1/*`, and stripped the
client Authorization header before proxying to Dispatcher. This blocks
independent S02 application identities.

The new private Caddyfile stage helper `scripts/s03_caddy_s02_stage.ps1`
requires the **exact reviewed topology**: an active `@unauthorizedAI`
matcher, two explicitly routed backends, the existing key on the direct
native Strata path, and the legacy stripped Dispatcher header. It changes
the matcher so **only direct `/strata/v1/*`** still requires the existing
gateway key, and forwards the original application Authorization header
on Dispatcher `/v1/*`. Dispatcher itself MUST authenticate every S02
client and reject unknown/missing keys with HTTP 401.

For an operator-local installation, using the actual private absolute paths:

```powershell
# Read-only preview; nothing starts or changes:
./scripts/s03_caddy_s02_stage.ps1 -Caddyfile '<private-Caddyfile>'

# Only while the old Caddy is STOPPED; validates with the installed Caddy:
./scripts/s03_caddy_s02_stage.ps1 -Caddyfile '<private-Caddyfile>' `
  -CaddyExe '<actual-caddy.exe>' -DpapiKeyFile '<existing-gateway.dpapi>' -Stage

# If rollback is required, also while Caddy is STOPPED:
./scripts/s03_caddy_s02_stage.ps1 -Caddyfile '<private-Caddyfile>' `
  -CaddyExe '<actual-caddy.exe>' -DpapiKeyFile '<existing-gateway.dpapi>' `
  -Revert -Stage
```

Staging saves `<private-Caddyfile>.s02-before-multiclient`,
validates the modified file with Caddy, and **does not reload or start Caddy**.
A changed/unknown source, missing rollback file or any unrelated subsequent
edits fail closed. Back up the old private launcher, old Caddyfile,
WebUI persistent data and Dispatcher instance beforehand.

**Do not consider this a live gateway validation.** After the owner's
controlled four-service AIW start, confirm 401 for absent/invalid API
keys, 200 for each new valid S02 client on Dispatcher and HTTPS Caddy,
and preserved old-key authorization on the direct `/strata/v1/*` path.
Verify all three distinct `metrics_proxy_requests.client_id` values
after actual application requests. The source code has no private
domain, model, server account or secret baked in.


## Two role aliases on the same native model (short-term S03 bridge)

S03 can now expose `sparringpartner` and `agent` without starting
another model or implementing S07. The starter option
`-RoleAliasesFile <absolute-private-role-file.json>` reads a
**private, operator-authored** role-policy file. The public example
[examples/s03-role-aliases.json](../examples/s03-role-aliases.json)
has no token, host-specific path or native model identifier.
The starter discovers the native Strata model on every start and
maps **both** aliases to that same model. Existing single-alias
invocations remain unchanged.

The template sets `sparringpartner` to
`reasoning_effort: high` and `agent` to
`reasoning_effort: none` with focused sampling, reflecting the *intention*
of the earlier 3090 ensemble. This is **not** yet engine-neutral S07
ensemble compilation or Gemma/Strata behavior equivalence.

**Important:** AIW's initially generated S02 clients use
`policy: passthrough`; in that mode only alias-name/model remapping
occurs — the Dispatcher deliberately does **not** inject role
parameters. To apply role defaults for Goose, change the
`goose-wsl` entry in the *private* AIW `services.yaml` to
`policy: default` (client-supplied parameters still win).
Do this only during an owner-approved stopped-service window,
then AIW **Manage application access keys → Prepare the
Dispatcher key-verification file** regenerates the same four
SHA-256 credentials with the updated policy. Do **not** rotate or
reissue original API keys. `policy: enforce` can be considered
separately when strict role overrides are needed.

### Owner-controlled staging

1. AIW **Run and monitor AI services → Stop all managed
   services**. Confirm and check port ownership.
2. In the *current Dispatcher review checkout*, pull latest and
   copy `examples/s03-role-aliases.json` into a **new private**
   location (e.g. the private AIW services directory).
3. AIW **Set up or change this computer → Edit service startup
   settings**. Append `"-RoleAliasesFile"` and the **absolute
   private JSON filename** as two array items in
   `dispatcher.arguments` of `native-host.json`. Do not edit the
   generated `strata-attach.json`, which the S03 starter replaces
   every time.
4. Optionally change only Goose's private S02 policy from
   `passthrough` to `default`, then use the existing AIW
   **Manage keys → Prepare Dispatcher key-verification file**.
5. AIW **Setup → Check / Apply edited settings**, check port
   owners, then **Run and monitor → Start all enabled services**.
6. Authenticate to `GET /v1/models` and verify both names.
   Test a small Goose completion with each alias. Check actual
   Dispatcher request-metric `client_model` and effective
   parameters; client-supplied overrides under `default` win.
   Existing client bearer secrets and HTTPS URL are unchanged.

Rollback: owned stop, remove the two `-RoleAliasesFile`
array items, restore Goose's former policy if altered, re-render
S02 registry and process definitions, check, then restart.
**Never copy old Dispatcher program code over this checkout,
overwrite either SQLite database, or launch legacy managed
llama.cpp simultaneously.**
