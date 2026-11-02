#Requires -Version 7.4
<#
.SYNOPSIS
    Keep an S03 Dispatcher attached to an already running native Strata on Speedy.
.DESCRIPTION
    No process manager: foreground-only owner trial on loopback port 8001.
    Reuses the DPAPI-protected gateway/Strata secret, never prints or stores
    plaintext, hashes it for one S02 transitional identity. Caddy/Strata are
    never started, stopped, configured or reloaded by this script.
    A shared gateway token cannot distinguish Goose from Open WebUI.
.EXAMPLE
    ./scripts/s03_speedy_gateway.ps1 -DpapiKeyFile 'C:\Caddy\speedy-api-key.dpapi'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$DpapiKeyFile,
    [string]$StrataUrl = 'http://127.0.0.1:8080',
    [ValidateRange(1, 65535)][int]$DispatcherPort = 8001,
    [string]$Instance = 'Speedy_S03_Stage',
    [string]$Alias = 'agent'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$previousNative = [Environment]::GetEnvironmentVariable('STRATA_NATIVE_KEY', 'Process')
$previousClient = [Environment]::GetEnvironmentVariable('DISPATCHER_CLIENT_CONFIG', 'Process')

try {
    if (-not (Test-Path -LiteralPath $DpapiKeyFile -PathType Leaf)) {
        throw 'DPAPI key file missing: verify the file path and the Windows account.'
    }
    $endpoint = [Uri]$StrataUrl
    if ($endpoint.Scheme -ne 'http' -or
        $endpoint.Host -notin @('127.0.0.1', 'localhost', '::1') -or
        $endpoint.AbsolutePath -ne '/' -or $endpoint.UserInfo -or
        $endpoint.Query -or $endpoint.Fragment -or $endpoint.IsDefaultPort) {
        throw 'Native Strata must be an explicit loopback HTTP root URL with a port.'
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'uv is required for the existing locked Dispatcher Python environment.'
    }
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $DispatcherPort -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        throw "Port $DispatcherPort is occupied; inspect the listener. No process was stopped."
    }
    $encryptedKey = (Get-Content -LiteralPath $DpapiKeyFile -Raw).Trim()
    if (-not $encryptedKey) { throw 'DPAPI file is empty.' }
    $secure = ConvertTo-SecureString -String $encryptedKey
    $key = [System.Net.NetworkCredential]::new('unused', $secure).Password
    if ([string]::IsNullOrWhiteSpace($key)) { throw 'DPAPI key could not be decrypted.' }

    # The same OS-user DPAPI key already protects existing native Strata and Caddy.
    # Check the actual native service without changing its running process.
    $headers = @{ Authorization = "Bearer $key" }
    $models = Invoke-RestMethod -Uri ($StrataUrl.TrimEnd('/') + '/v1/models') `
        -Headers $headers -TimeoutSec 10 -NoProxy
    $native = @($models.data | Where-Object { $_.id })
    if ($native.Count -lt 1) {
        throw 'Native Strata advertised no model. Check the already-running service.'
    }
    $nativeId = [string]$native[0].id

    $private = Join-Path $env:LOCALAPPDATA 'Llama_Dispatcher\S03\gateway'
    New-Item -ItemType Directory -Path $private -Force | Out-Null
    $clientFile = Join-Path $private 'clients.json'
    $attachFile = Join-Path $private 'strata-attach.json'
    $digest = [Convert]::ToHexString(
        [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($key))
    ).ToLowerInvariant()

    # Single, honest transitional identity for the previously shared Caddy key.
    # Passthrough preserves the successful direct-Strata request policy initially.
    @{ schema_version = 1; clients = @(@{
        id = 'home-gateway'; token_sha256 = $digest; policy = 'passthrough'
    }) } | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -LiteralPath $clientFile

    # Do not impose an arbitrary reasoning budget or temperature on Goose.
    # Strata continues to use its existing configured defaults.
    @{ schema_version = 1; endpoint = $StrataUrl.TrimEnd('/');
       credential_env = 'STRATA_NATIVE_KEY';
       aliases = @{ $Alias = @{ model = $nativeId; parameters = @{} } }
    } | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 -LiteralPath $attachFile

    $env:STRATA_NATIVE_KEY = $key
    $env:DISPATCHER_CLIENT_CONFIG = $clientFile

    Write-Host "[S03] Native Strata reachable; model: $nativeId"
    Write-Host "[S03] Client identity: home-gateway (shared key, no false per-app attribution)"
    Write-Host "[S03] Start Dispatcher on 127.0.0.1:$DispatcherPort; public alias: $Alias"
    Write-Host '[S03] Keep this PowerShell window open; Ctrl+C stops only this Dispatcher.'
    Push-Location $repo
    try {
        & uv run --frozen python src/dispatcher.py serve `
            --instance $Instance --api-port $DispatcherPort --strata-config $attachFile
        if ($LASTEXITCODE -ne 0) {
            throw "The S03 Dispatcher exited with code $LASTEXITCODE."
        }
    }
    finally { Pop-Location }
}
finally {
    [Environment]::SetEnvironmentVariable('STRATA_NATIVE_KEY', $previousNative, 'Process')
    [Environment]::SetEnvironmentVariable('DISPATCHER_CLIENT_CONFIG', $previousClient, 'Process')
}
