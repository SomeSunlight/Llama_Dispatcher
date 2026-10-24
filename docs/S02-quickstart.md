# S02 — Quickstart: verify client identities and request policies

The S02 verification script works on Windows, WSL and Linux. It tests two **simulated API clients** (Goose and Open WebUI), each with its own disposable credential and request policy. Neither application needs to be installed for this check. No Strata service is required.

## Recommended: use the normal PowerShell startup on Laptop/Windows

On the owner's Windows/SYCL laptop, `llama-server.exe` runs normally from PowerShell, but the optional test-managed launch exits immediately with Windows status `0xC0000135` (missing runtime DLL). The difference in launch environments is **not resolved**. The following procedure uses the existing, known-good manual startup without altering SYCL, DLL paths, or model configuration.

**1. Stop the non-production Dispatcher, then prepare two temporary test clients:**

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --prepare-manual
```

The program prints the full next-test command and a PowerShell environment assignment similar to:

```powershell
$env:DISPATCHER_CLIENT_CONFIG = 'C:\llama.cpp\Llama_Dispatcher\reports\s02-Laptop_Win.manual-clients.json'
```

**2. In your usual PowerShell terminal, set the printed environment variable and launch the Dispatcher with its already-working command.** For the owner's Laptop/Windows test instance:

```powershell
uv run src/dispatcher.py serve --ensemble thinkpad-sycl-gemma_26B --instance Laptop_Win --model-root c:\AI_Models\LLM\GGUF_Raw
```

Leave that process running. The model can remain your existing small non-production test model; the tests do not require Strata or Speedy.

**3. In a second terminal, verify authentication and run two tiny real inference requests:**

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --verify-manual --inference
```

The runner checks independent client credentials, rejection of unauthenticated/spoofed requests, `enforce` and `default` policies, safe debug preview, two 3-token model responses, and both client identities in SQLite schema v9. **Only `S02 PASS` with `Inference: PASS` and `SQLite: PASS` establishes this full end-to-end test.**

**4. Stop the Dispatcher yourself, and remove disposable test credentials:**

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --cleanup-manual
Remove-Item Env:DISPATCHER_CLIENT_CONFIG -ErrorAction SilentlyContinue
```

The cleanup removes the two temporary credential files, not the running process. The regular `C:\llama.cpp\clients.json` is never changed. Temporary credentials remain private and Git-ignored under `reports/` until cleanup; one of the files contains **raw disposable tokens**, so do not share or commit it. Deletion is not secure erasure.

## Alternative: test-managed startup

For a non-production environment where native engines start reliably under a subprocess, the runner can first capture the current launch parameters:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --save-start
```

Stop that test Dispatcher yourself, then run:

```powershell
uv run --frozen python scripts/s02_verify.py --instance Laptop_Win --start --inference
```

The saved startup arguments stay in a Git-ignored, instance-specific `reports/s02-*.launch.json`; the test uses its project Python environment and temporary client credentials. It never takes over another process if the API port is occupied.

A test-managed launch uses a different console/IO setup and process group from an interactive PowerShell session. **Do not treat that as identical to the normal startup.** On a startup error, the script prints the native process exit code and the last 30 console-log lines. The complete process log remains under `reports/s02-*.dispatcher-*.log`, excluded from Git. Review logs for host paths and private data before sharing.

## Other installations

The same script is used for `Laptop_WSL`, `Speedy_Win`, and other explicitly named instances; change only `--instance`. Each installation keeps its own instance configuration, local test credentials, runtime paths and SQLite data. If the local Dispatcher uses another port, append `--base-url http://127.0.0.1:PORT` consistently to the preparation and verification commands.

**Do not use this S02 test runner to manage production Strata or Caddy.** Strata attachment is a separately reviewed S03 change, and engine lifecycle ownership belongs to the external process manager.

For implementation details, policies, credential rotation and rollback, see [S02 client identities](S02-client-identities.md).
