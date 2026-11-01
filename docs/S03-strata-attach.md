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
