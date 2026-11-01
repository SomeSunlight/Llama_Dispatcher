# S03 one-shot native Speedy/Windows test. Never changes Strata or Caddy.
# Run in PowerShell 7 from a separate PR #27 checkout:
#   ./scripts/s03_speedy_smoke.ps1
#   ./scripts/s03_speedy_smoke.ps1 -Inference
[CmdletBinding()]
param(
    [switch]$Inference,
    [string]$StrataUrl = "http://127.0.0.1:8080",
    [ValidateRange(1, 65535)][int]$DispatcherPort = 18001
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dispatcherUrl = "http://127.0.0.1:$DispatcherPort"
$private = Join-Path $env:LOCALAPPDATA "Llama_Dispatcher\S03"
$sessionDir = Join-Path $private ("session-" + [guid]::NewGuid().ToString("N"))
$report = Join-Path $private ("s03-live-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".json")
$clientFile = Join-Path $sessionDir "clients.json"
$attachFile = Join-Path $sessionDir "strata-attach.json"

# The attach contract accepts only a loopback HTTP native target (or HTTPS for
# remote URLs), but this particular local-only acceptance uses loopback solely.
$nativeUrl = [uri]$StrataUrl
if ($nativeUrl.Scheme -ne "http" -or
    $nativeUrl.Host -notin @("127.0.0.1", "localhost", "::1") -or
    $nativeUrl.AbsolutePath -ne "/" -or $nativeUrl.UserInfo -or
    $nativeUrl.Query -or $nativeUrl.Fragment -or
    $nativeUrl.IsDefaultPort) {
    # Require an explicit port even when host and scheme are otherwise valid.
    throw "This one-shot S03 runner requires a local http://127.0.0.1:PORT Strata root URL."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required on Speedy; run this from the working Dispatcher Python setup."
}

$previousNative = [Environment]::GetEnvironmentVariable("STRATA_NATIVE_KEY", "Process")
$previousClientConfig = [Environment]::GetEnvironmentVariable("DISPATCHER_CLIENT_CONFIG", "Process")
$previousSmokeToken = [Environment]::GetEnvironmentVariable("S03_SMOKE_CLIENT_TOKEN", "Process")
$job = $null
$passed = $false

try {
    if (-not $env:STRATA_NATIVE_KEY) {
        $secret = Read-Host "Existing native Strata API key (not displayed)" -AsSecureString
        $env:STRATA_NATIVE_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
    }
    if (-not $env:STRATA_NATIVE_KEY) {
        throw "Strata native API key is required. No service configuration was changed."
    }
    $headers = @{ Authorization = "Bearer $env:STRATA_NATIVE_KEY" }
    $nativeModels = Invoke-RestMethod -Uri ($StrataUrl.TrimEnd('/') + "/v1/models") -Headers $headers -TimeoutSec 10
    $nativeCandidates = @($nativeModels.data | Where-Object { $_.id })
    if ($nativeCandidates.Count -lt 1) {
        throw "Running native Strata returned no model identifier."
    }
    $nativeId = $nativeCandidates[0].id

    New-Item -ItemType Directory -Path $sessionDir -Force | Out-Null
    $env:S03_SMOKE_CLIENT_TOKEN = [Convert]::ToHexString(
        [Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    $digestBytes = [Text.Encoding]::UTF8.GetBytes($env:S03_SMOKE_CLIENT_TOKEN)
    $hash = [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData($digestBytes)).ToLowerInvariant()
    $env:DISPATCHER_CLIENT_CONFIG = $clientFile

    @{ schema_version = 1; clients = @(@{
        id = "s03-smoke"; token_sha256 = $hash; policy = "enforce"
    }) } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 $clientFile

    @{ schema_version = 1; endpoint = $StrataUrl.TrimEnd('/');
       credential_env = "STRATA_NATIVE_KEY";
       aliases = @{ agent = @{ model = $nativeId; parameters = @{ temperature = 0.2 } } }
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 $attachFile

    $existing = @(Get-NetTCPConnection -State Listen -LocalPort $DispatcherPort -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        throw "Test Dispatcher port $DispatcherPort is already in use. Use -DispatcherPort 18002."
    }

    Write-Host "[S03] Native model: $nativeId"
    Write-Host "[S03] Starting an isolated Dispatcher at $dispatcherUrl (Strata remains running)."
    $job = Start-Job -ScriptBlock {
        param($checkout, $attach, $clients, $key, $port)
        $env:DISPATCHER_CLIENT_CONFIG = $clients
        $env:STRATA_NATIVE_KEY = $key
        Set-Location $checkout
        & uv run --frozen python src/dispatcher.py serve `
            --instance Speedy_S03_Test --api-port $port --strata-config $attach
    } -ArgumentList $repo, $attachFile, $clientFile, $env:STRATA_NATIVE_KEY, $DispatcherPort

    $ready = $false
    for ($i = 0; $i -lt 25; $i++) {
        if ($job.State -in @("Failed", "Stopped", "Completed")) { break }
        try {
            $probe = Invoke-WebRequest -Uri ($dispatcherUrl + "/v1/models") `
                -Headers @{ Authorization = "Bearer $env:S03_SMOKE_CLIENT_TOKEN" } `
                -TimeoutSec 2
            if ($probe.StatusCode -eq 200) { $ready = $true; break }
        }
        catch {
            # Startup may take a few seconds while uv resolves a locked environment.
        }
        Start-Sleep -Milliseconds 750
    }
    if (-not $ready) {
        throw "The isolated Dispatcher did not become ready on $dispatcherUrl."
    }

    $smokeArgs = @("run", "--frozen", "python", "scripts/s03_live_smoke.py",
                   "--base-url", $dispatcherUrl, "--alias", "agent")
    if ($Inference) {
        $db = Join-Path $repo "instances\Speedy_S03_Test\data\metrics.db"
        $smokeArgs += @("--inference", "--client-id", "s03-smoke",
                        "--db", $db, "--report", $report)
    }

    Push-Location $repo
    try {
        & uv @smokeArgs
        if ($LASTEXITCODE -ne 0) {
            throw "S03 smoke runner failed with exit code $LASTEXITCODE."
        }
    }
    finally { Pop-Location }
    $passed = $true
}
finally {
    if ($job) {
        if (-not $passed) {
            Write-Host "[S03] Test Dispatcher job output (check for redaction):"
            Receive-Job -Job $job -Keep -ErrorAction SilentlyContinue
        }
        Stop-Job -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
        # A subprocess may outlive a PowerShell background job on some Windows
        # builds. Never terminate an unknown PID; flag residual test listeners.
        Start-Sleep -Milliseconds 350
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $DispatcherPort -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0) {
            Write-Warning "Port $DispatcherPort still listens after Stop-Job. Inspect the test Dispatcher process manually; do not stop native Strata."
        }
        else {
            Write-Host "[S03] Disposable test Dispatcher listener stopped."
        }
    }
    Remove-Item -LiteralPath $sessionDir -Recurse -Force -ErrorAction SilentlyContinue
    [Environment]::SetEnvironmentVariable("STRATA_NATIVE_KEY", $previousNative, "Process")
    [Environment]::SetEnvironmentVariable("DISPATCHER_CLIENT_CONFIG", $previousClientConfig, "Process")
    [Environment]::SetEnvironmentVariable("S03_SMOKE_CLIENT_TOKEN", $previousSmokeToken, "Process")
}
if ($passed) {
    Write-Host "[S03] One-shot Speedy smoke passed; native Strata and Caddy were not managed."
}
