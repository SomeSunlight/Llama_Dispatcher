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
