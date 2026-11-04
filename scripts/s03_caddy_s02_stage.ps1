#Requires -Version 7.4
<#
.SYNOPSIS
    Stage S02 multi-client gateway forwarding in the private Caddyfile.
.DESCRIPTION
    Strictly recognizes the existing S03 Caddy shape. By default only
    previews changes. -Stage changes the file while services are STOPPED,
    with backup and offline Caddy validation; never reloads or starts Caddy.
    -Revert restores only the exact expected staged file. The direct Strata
    fallback remains protected by its existing private gateway key.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Caddyfile,
    [string]$CaddyExe,
    [string]$DpapiKeyFile,
    [switch]$Stage,
    [switch]$Revert
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($Stage -and $Revert) { throw 'Choose either -Stage or -Revert, not both.' }

if (-not (Test-Path -LiteralPath $Caddyfile -PathType Leaf)) {
    throw 'Private Caddyfile not found; no changes made.'
}
$real = (Resolve-Path -LiteralPath $Caddyfile).Path
$source = [IO.File]::ReadAllText($real)
$backup = $real + '.s02-before-multiclient'
$oldAuth = 'path /v1/* /strata/v1/*'
$newAuth = 'path /strata/v1/*'
$oldForward = 'header_up -Authorization'
$newForward = 'header_up Authorization {http.request.header.Authorization}'

# Never infer Caddyfile semantics from one isolated line. Require the
# exact reviewed matcher and both expected upstream routes.
if ([regex]::Matches($source,'(?m)^\s*@unauthorizedAI\s*\{').Count -ne 1 -or
    [regex]::Matches($source,'(?m)^\s*handle /v1/\* \{').Count -ne 1 -or
    [regex]::Matches($source,'(?m)^\s*handle /strata/v1/\* \{').Count -ne 1 -or
    [regex]::Matches($source,'(?m)^\s*reverse_proxy 127\.0\.0\.1:8001\s*\{').Count -ne 1 -or
    -not $source.Contains('reverse_proxy 127.0.0.1:8080') -or
    -not $source.Contains('not header Authorization "Bearer {$SPEEDY_API_KEY}"')) {
    throw 'Caddyfile topology differs from the reviewed S03 gateway; no changes made.'
}
$oldMatch = '(?m)^([ \t]*)path[ \t]+/v1/\*[ \t]+/strata/v1/\*([ \t]*)(\r?)$'
$newMatch = '(?m)^([ \t]*)path[ \t]+/strata/v1/\*([ \t]*)(\r?)$'
$oldCount=[regex]::Matches($source,$oldMatch).Count
$newCount=[regex]::Matches($source,$newMatch).Count
if (($oldCount -eq 1 -and $newCount -eq 0) -ne
    ($source.Contains($oldForward) -and -not $source.Contains($newForward)) -and
    -not ($newCount -eq 1 -and $oldCount -eq 0 -and
          $source.Contains($newForward) -and -not $source.Contains($oldForward))) {
    throw 'Caddy authentication matcher and Authorization header are in inconsistent states.'
}
if ($oldCount -eq 1 -and $newCount -eq 0 -and
    $source.Contains($oldForward) -and -not $source.Contains($newForward)) {
    $state='legacy'
}
elseif ($newCount -eq 1 -and $oldCount -eq 0 -and
        $source.Contains($newForward) -and -not $source.Contains($oldForward)) {
    $state='staged'
}
else {
    throw 'Unsupported or ambiguous Caddy authentication state; no changes made.'
}

if ($state -eq 'legacy') {
    $candidate=[regex]::Replace($source,$oldMatch,'$1' + $newAuth + '$2$3')
    $candidate=$candidate.Replace($oldForward,$newForward)
}
else {
    $candidate=$source
}
if (-not $Revert) {
    Write-Host '[S02] Dispatcher /v1/*: forward client Authorization, enforce per-client S02 in Dispatcher.'
    Write-Host '[S02] Strata /strata/v1/*: keep the original independent Caddy bearer gate.'
    Write-Host "[S02] Current Caddyfile state: $state"
    if (-not $Stage) {
        Write-Host '[S02] PREVIEW ONLY. Use -Stage with stopped Caddy to write and validate privately.'
        return
    }
    if ($state -eq 'staged') {
        Write-Host '[OK] Multi-client Caddyfile already staged; not modified.'
        return
    }
    if (Test-Path -LiteralPath $backup) {
        throw 'Previous S02 Caddy backup already exists. Inspect before staging; not overwritten.'
    }
}
else {
    if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) {
        throw 'Caddy S02 rollback backup missing; no changes made.'
    }
    $original=[IO.File]::ReadAllText($backup)
    if ($state -ne 'staged') {
        throw 'Caddyfile is not in the reviewed staged state; refusing to overwrite.'
    }
    $expected=[regex]::Replace($original,$oldMatch,'$1' + $newAuth + '$2$3')
    $expected=$expected.Replace($oldForward,$newForward)
    if ($source -cne $expected) {
        throw 'Caddyfile was edited since staging. Resolve manually; do not overwrite.'
    }
    if (-not $Stage) {
        Write-Host '[S02] PREVIEW ONLY. Use -Revert -Stage while stopped to restore the private backup.'
        return
    }
    $candidate=$original
}

if (-not (Test-Path -LiteralPath $CaddyExe -PathType Leaf) -or
    -not (Test-Path -LiteralPath $DpapiKeyFile -PathType Leaf)) {
    throw 'Offline Caddy validation requires its actual executable and existing protected secret file.'
}
$key = [System.Net.NetworkCredential]::new(
    'local', (ConvertTo-SecureString -String (
        [IO.File]::ReadAllText($DpapiKeyFile).Trim()))
).Password
if ([string]::IsNullOrWhiteSpace($key)) { throw 'Caddy DPAPI secret unreadable.' }
$prev = [Environment]::GetEnvironmentVariable('SPEEDY_API_KEY','Process')
$bytes=[Text.UTF8Encoding]::new($false)
$wrote=$false
try {
    $env:SPEEDY_API_KEY=$key
    # Preserve the existing backup; no live Caddy reload or process launch.
    if (-not $Revert) {
        [IO.File]::WriteAllText($backup,$source,$bytes)
    }
    [IO.File]::WriteAllText($real,$candidate,$bytes)
    $wrote=$true
    & $CaddyExe validate --config $real *> $null
    if ($LASTEXITCODE -ne 0) {
        throw 'Offline Caddy validation rejected the staged file.'
    }
    if ($Revert) {
        Write-Host '[OK] Original Caddyfile restored. Existing backup retained for audit.'
    }
    else {
        Write-Host '[OK] Multi-client Caddyfile staged and validated. NO live reload/start performed.'
    }
}
catch {
    if ($wrote) {
        [IO.File]::WriteAllText($real,$source,$bytes)
    }
    throw 'Caddy staging failed and original file was retained/restored. Check paths, Caddy validation and backups.'
}
finally {
    [Environment]::SetEnvironmentVariable('SPEEDY_API_KEY',$prev,'Process')
    Remove-Variable key -ErrorAction SilentlyContinue
}
