#Requires -Version 7.4
<#
.SYNOPSIS
    Keep an S03 Dispatcher attached to an already running native Strata on Speedy.
.DESCRIPTION
    No process manager: foreground-only owner trial on loopback port 8001.
    Reuses the DPAPI-protected native Strata secret. With -ClientConfig
    (or inherited DISPATCHER_CLIENT_CONFIG), validates and uses an existing
    multi-client S02 digest registry without overwriting it. Optional
    -RoleAliasesFile loads multiple public aliases and generic OpenAI-style
    request defaults from a private JSON; all map to the same discovered
    externally managed native Strata model, never a second process. Without external
    config, it retains the legacy one-key transitional behavior. Caddy/Strata are
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
    [string]$Alias = 'agent',
    [string]$ClientConfig = '',
    [string]$RoleAliasesFile = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 's03_client_registry.ps1')
. (Join-Path $PSScriptRoot 's03_role_aliases.ps1')
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
    $legacyClientFile = Join-Path $private 'clients.json'
    $attachFile = Join-Path $private 'strata-attach.json'
    # Explicit -ClientConfig takes precedence. The AIW native host can also
    # supply a nonsecret DISPATCHER_CLIENT_CONFIG via its environment mapping.
    # Never regenerate the old one-key registry when an external file is set.
    $requestedClientConfig = if ($ClientConfig) { $ClientConfig } else { $previousClient }
    $clientFile = Select-S03ClientRegistry -ExternalPath $requestedClientConfig `
        -LegacyOutputPath $legacyClientFile -LegacyKey $key

    # Without explicit private role settings the S03 single-alias baseline
    # remains unchanged, including no forced sampling or thinking controls.
    $roleAliases = if ($RoleAliasesFile) {
        Get-S03RoleAliases -RoleFile $RoleAliasesFile -NativeModel $nativeId
    }
    else {
        @{ $Alias = @{ model = $nativeId; parameters = @{} } }
    }
    @{ schema_version = 1; endpoint = $StrataUrl.TrimEnd('/');
       credential_env = 'STRATA_NATIVE_KEY';
       aliases = $roleAliases
    } | ConvertTo-Json -Depth 12 | Set-Content -Encoding utf8 -LiteralPath $attachFile

    $env:STRATA_NATIVE_KEY = $key
    $env:DISPATCHER_CLIENT_CONFIG = $clientFile

    Write-Host "[S03] Native Strata reachable; model: $nativeId"
    if (-not $requestedClientConfig) {
        Write-Warning '[S03] Legacy shared key only; configure S02 multi-client registry before production adoption.'
    }
    if ($RoleAliasesFile) {
        Write-Host "[S03] Public role aliases: $(($roleAliases.Keys | Sort-Object) -join ', ')"
        Write-Host '[S03] Per-alias policy injection depends on S02 client policy (default/enforce).'
    }
    else {
        Write-Host "[S03] Start Dispatcher on 127.0.0.1:$DispatcherPort; public alias: $Alias"
    }
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
