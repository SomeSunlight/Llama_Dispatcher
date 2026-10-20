# S02 — Client identity and explicit request policies

**Für den eigentlichen Test zuerst nur [S02-SCHNELLTEST.md](S02-SCHNELLTEST.md) lesen.**
Der folgende Text ist technische Hintergrunddokumentation, keine Pflichtlektüre.

**Owner-gated review:** [Issue #10](https://github.com/SomeSunlight/Llama_Dispatcher/issues/10).
Prerequisite S01 accepted in [PR #22](https://github.com/SomeSunlight/Llama_Dispatcher/pull/22).
S03/Strata attach is **not implemented**. No change to productive Speedy Strata/Caddy.

## What is new

- **Legacy default is unchanged:** without `DISPATCHER_CLIENT_CONFIG`, Dispatcher accepts
  existing traffic and keeps the S00 `enforce` profile-wins behavior.
  Its request rows have `client_id = NULL`, not a guessed identity.
- **Explicit opt-in authentication** by private per-client bearer tokens. The
  configuration file contains only SHA-256 token digests; a 256-bit or stronger
  randomly generated token is essential because unsalted digests of weak passwords
  are vulnerable to offline guessing. Authentication uses constant-time digest
  comparison. Invalid configuration **aborts startup**, never silently disables auth.
- Identifies Goose and Open WebUI independently; client identity does **not**
  depend on User-Agent, IP, model alias, Origin or forwarded identity headers.
- Auth is enforced on `/v1/*`, `/debug/*`, `/switch` and `/stop`.
  Unknown/revoked/missing tokens receive HTTP 401. Direct HTTP health/discovery
  endpoints not listed here are **not a firewall**: keep the API on a private
  network or behind access-controlled Caddy.
- With auth enabled, strips incoming `Authorization`, cookies, API keys and
  identity/forwarding headers from upstream requests, forwarding a small safe
  allowlist instead. Legacy mode retains its original wire/header behavior.
- Nullable `client_id` and `policy_mode` columns in additive SQLite **v9**
  migration (including `v_proxy_request_summary`); historical client identity
  remains NULL. Request audit snapshots retain only known-safe control values,
  never arbitrary extension fields, prompts, tools or credentials. The **actual
  forwarded JSON** still contains message/tool payloads required for inference.
  Never store full outgoing JSON in diagnostics.
- S00 debug preview remains byte-for-byte compatible **in legacy mode**. With
  auth enabled, request content fields such as messages/tools are redacted in
  `forwarded_body`; control and model transformations remain visible.
- Deliberately retains existing S00 SSE framing/upstream-status limitations.

## Policy semantics

Configured per authenticated client (not per model). The profile/alias remains
the source of configured sampling controls; alias remapping **always occurs**.

| Mode | If a client supplies a sampling parameter | If client omits it |
| --- | --- | --- |
| `enforce` | Dispatcher profile overrides | Dispatcher inserts profile value |
| `default` | Client value preserved | Dispatcher inserts profile value |
| `passthrough` | Client value preserved | Dispatcher does not inject |

Other request fields (tools, messages, max_tokens, native extensions) are
forwarded unchanged. `chat_template_kwargs` remains an atomic profile value
if inserted/overridden, not a deep merge. New per-client mode is logged; never
infer the engine's *actual* behavior from what Dispatcher forwarded.

## Private configuration, example only — NEVER commit

Create **one different random token** per client and its SHA-256 hex digest.
The following PowerShell creates a token in memory and prints its digest; keep
the *token itself* privately in the corresponding client's API-key settings.
Do not paste tokens into a command line, GitHub issue, logs or conversation.

```powershell
$token = python -c "import secrets; print(secrets.token_urlsafe(48))"
$token # Copy privately into the client. Do not commit.
$token | python -c "import hashlib,sys; print(hashlib.sha256(sys.stdin.read().strip().encode()).hexdigest())"
Remove-Variable token
```

Save **digests only** in a private file outside all Git repositories, e.g.
`$env:LOCALAPPDATA\Llama_Dispatcher\clients.json`. Substitute the two
real, different digests; the placeholders below are deliberately invalid.

```json
{
  "schema_version": 1,
  "clients": [
    {"id": "goose", "token_sha256": "<64-hex-digest-goose>", "policy": "enforce"},
    {"id": "open-webui", "token_sha256": "<64-hex-digest-webui>", "policy": "default"}
  ]
}
```

Set the path **in the shell that launches the Dispatcher** (not only in the
shell that calls the tests):

```powershell
$env:DISPATCHER_CLIENT_CONFIG = Join-Path $env:LOCALAPPDATA "Llama_Dispatcher\clients.json"
# Start Dispatcher with your UNCHANGED, instance-specific command here.
```

Tokens are supplied as `Authorization: Bearer <private-token>` over
the existing HTTPS Caddy ingress; do **not** put them into URLs. Use a private
token environment variable for smoke tests, not `--launch-command`, CLI args,
Git remote URLs or report file names. A private file must be permission-restricted
to the Dispatcher operator. The digest file isn't a secure secret store for
*raw* tokens; Goose and Open WebUI must each securely retain their own token.

**Rotation/revocation:** issue new random token and digest; replace the entry,
then **restart the test Dispatcher** to reload configuration. Remove a client
entry to revoke it (at least one client is required). Revocation is not
instantaneous until that controlled restart. Keep direct Caddy Strata access
unchanged during this separate migration; no automatic client cutover.

**Caddy trust boundary:** Dispatcher independently authenticates bearer tokens;
untrusted `X-Client-Id`, `X-Forwarded-User`, User-Agent or Origin values can
never select identity. Protect Caddy TLS and access routes as before, and do
not forward client tokens to a direct Strata backend. Verify each client's
existing URL/base-path behavior before any Speedy cutover in S03.

## Test / manual owner gate

First run the new automated unit tests from your existing project directory:

```powershell
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python scripts/s00_verify.py --unit-only --label S02
```

**Legacy-mode smoke:** Restart the nonproductive laptop llama.cpp Dispatcher
from the PR checkout with its same original startup command. A checkout does not
reload the old running Python process. Use a **separate report directory** to
preserve the original S00 baseline:

```powershell
$report = Join-Path $env:TEMP 'Llama_Dispatcher_S02\legacy-smoke.json'
uv run --frozen python scripts/s00_verify.py --instance Laptop_Win --report $report --inference
```

**Authenticated-mode smoke (only after provisioning private test credentials):**
Restart the same nonproductive Dispatcher with `DISPATCHER_CLIENT_CONFIG`
pointing to the private file, then set one of the newly provisioned test tokens
as `DISPATCHER_SMOKE_TOKEN` **in the test shell**, and run:

```powershell
$report = Join-Path $env:TEMP 'Llama_Dispatcher_S02\auth-smoke.json'
uv run --frozen python scripts/s00_verify.py --instance Laptop_Win --report $report --bearer-token-env DISPATCHER_SMOKE_TOKEN --inference
```

Repeat once with each token to verify both clients separately. Confirm an
unrecognized token gives 401 and the configured policies differ in
`/debug/preview`. In the **test** SQLite database inspect
`metrics_proxy_requests.client_id, policy_mode` for the two request records.
Never publish or send the private `*.baseline.json` file without reviewing
its host command paths. An S02 smoke report cannot prove the API process was
restarted; manually confirm that first. S00 checks command/git/config fingerprints
at test time, not code loaded inside the Python process.

**Acceptance for real Goose/Open WebUI:** Owner verifies actual requests from
both clients with independent credentials and different SQLite `client_id`s
before enabling auth on any shared/private-service ingress. Do not migrate the
existing `SPEEDY_API_KEY` simultaneously with Caddy or Strata.

## Rollback

Clear `DISPATCHER_CLIENT_CONFIG` and restart on the previously accepted main
version (or stay in legacy mode). The v9 SQLite changes are additive and may
remain on disk; **do not downgrade/drop columns**, restore/copy active WAL files
or delete historic measurements. Existing S00 request semantics remain the
fallback. No Strata/Caddy/model process modifications in this PR.
