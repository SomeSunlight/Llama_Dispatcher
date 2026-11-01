#Requires -Version 7.4
<#
.SYNOPSIS
    Opt-in, rollback-safe forwarding of Caddy's already validated Bearer key to S02.
.DESCRIPTION
    Dry-run unless -Apply is explicitly set. Never publishes the user's Caddyfile
    (which may contain a live DNS token). Never changes the /strata/v1 fallback.
    IMPORTANT: Caddyfile {$SPEEDY_API_KEY} is expanded at config parse time.
    A reload without this secret in the command's process environment is unsafe.
.EXAMPLE
    ./scripts/s03_caddy_gateway.ps1 -Caddyfile 'C:\Caddy\Caddyfile'
.EXAMPLE
    ./scripts/s03_caddy_gateway.ps1 -Caddyfile 'C:\Caddy\Caddyfile' `
      -CaddyExe 'C:\Caddy\caddy_windows_amd64_custom.exe' `
      -DpapiKeyFile 'C:\Caddy\speedy-api-key.dpapi' `
      -ApiBaseUrl 'https://YOUR-DOMAIN' -Apply
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Caddyfile,
    [string]$CaddyExe,
    [string]$DpapiKeyFile,
    [string]$ApiBaseUrl,
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$source = Get-Content -LiteralPath $Caddyfile -Raw -ErrorAction Stop
if (-not $source.Contains('handle /v1/*') -or
    -not $source.Contains('reverse_proxy 127.0.0.1:8001') -or
    -not $source.Contains('handle /strata/v1/*') -or
    -not $source.Contains('not header Authorization "Bearer {$SPEEDY_API_KEY}"')) {
    throw 'Caddyfile does not match the reviewed gateway topology; no changes made.'
}

$removePattern = '(?m)^(?<indent>[ \t]*)header_up[ \t]+-Authorization[ \t]*(?<cr>\r?)$'
$alreadyPattern = '(?m)^[ \t]*header_up[ \t]+Authorization[ \t]+\{http\.request\.header\.Authorization\}[ \t]*\r?$'
$oldCount = [regex]::Matches($source, $removePattern).Count
$newCount = [regex]::Matches($source, $alreadyPattern).Count
if ($oldCount -eq 1 -and $newCount -eq 0) {
    $patched = [regex]::Replace($source, $removePattern,
        '${indent}header_up Authorization {http.request.header.Authorization}${cr}')
}
elseif ($oldCount -eq 0 -and $newCount -eq 1) {
    $patched = $source
}
else {
    throw 'Unexpected Authorization forwarding configuration; no changes made.'
}

Write-Host '[S03] Existing public /v1/ -> 127.0.0.1:8001 preserved.'
Write-Host '[S03] Existing direct /strata/v1/ -> Strata preserved.'
if (-not $Apply) {
    Write-Host '[S03] Dry run only. With -Apply, Caddy will forward its validated Bearer token to S02.'
    return
}
if (-not $CaddyExe -or -not $DpapiKeyFile -or -not $ApiBaseUrl) {
    throw 'Applying requires -CaddyExe, -DpapiKeyFile and -ApiBaseUrl.'
}
$api = [Uri]$ApiBaseUrl
if ($api.Scheme -ne 'https' -or $api.AbsolutePath -ne '/' -or
    $api.Query -or $api.Fragment -or $api.UserInfo) {
    throw 'The existing Caddy endpoint must be an HTTPS root URL without credentials.'
}
if (-not (Test-Path -LiteralPath $CaddyExe -PathType Leaf) -or
    -not (Test-Path -LiteralPath $DpapiKeyFile -PathType Leaf)) {
    throw 'Caddy executable or protected API key file is missing.'
}
$key = [System.Net.NetworkCredential]::new(
    'unused', (ConvertTo-SecureString (Get-Content -LiteralPath $DpapiKeyFile -Raw).Trim())
).Password
if ([string]::IsNullOrWhiteSpace($key)) { throw 'Cannot decrypt current Caddy API key.' }

$previous = [Environment]::GetEnvironmentVariable('SPEEDY_API_KEY', 'Process')
$headers = @{ Authorization = "Bearer $key" }
$encoding = [System.Text.UTF8Encoding]::new($false)
$changed = $false
$backup = "$Caddyfile.s03-backup-$(Get-Date -Format yyyyMMddHHmmss)"
try {
    $env:SPEEDY_API_KEY = $key

    # Do not reload Caddy until the intended local authenticated Dispatcher
    # actually answers (old and new instances must not compete for the port).
    $local = Invoke-WebRequest -Uri 'http://127.0.0.1:8001/v1/models' `
        -Headers $headers -NoProxy -TimeoutSec 10 -SkipHttpErrorCheck
    if ([int]$local.StatusCode -ne 200) {
        throw 'Dispatcher S02 did not accept the existing key on loopback port 8001.'
    }

    if ($patched -ne $source) {
        Copy-Item -LiteralPath $Caddyfile -Destination $backup -ErrorAction Stop
        [System.IO.File]::WriteAllText((Resolve-Path -LiteralPath $Caddyfile).Path, $patched, $encoding)
        $changed = $true
        & $CaddyExe validate --config $Caddyfile *> $null
        if ($LASTEXITCODE -ne 0) {
            throw 'Caddy validation failed (source restored below).'
        }
        & $CaddyExe reload --config $Caddyfile *> $null
        if ($LASTEXITCODE -ne 0) {
            throw 'Caddy reload failed (source restored below).'
        }
    }

    # Verify the *public* gate and actual alias forwarding, not merely Caddy's process.
    $anon = Invoke-WebRequest -Uri ($ApiBaseUrl.TrimEnd('/') + '/v1/models') `
        -NoProxy -TimeoutSec 10 -SkipHttpErrorCheck
    if ([int]$anon.StatusCode -ne 401 -or
        ([string]$anon.Content).Trim() -ne 'Unauthorized') {
        throw 'Public Caddy unauthorized gate did not return its exact 401 response.'
    }
    $authorized = Invoke-WebRequest -Uri ($ApiBaseUrl.TrimEnd('/') + '/v1/models') `
        -Headers $headers -NoProxy -TimeoutSec 10 -SkipHttpErrorCheck
    if ([int]$authorized.StatusCode -ne 200) {
        throw 'Caddy /v1/models did not reach authenticated Dispatcher.'
    }
    $models = ConvertFrom-Json -InputObject ([string]$authorized.Content)
    if (-not @($models.data | Where-Object { $_.id -eq 'agent' }).Count) {
        throw 'Public /v1/models does not advertise the expected agent alias.'
    }
    Write-Host '[S03] Public gate 401 and authorized Dispatcher alias 200 verified.'
    Write-Host '[S03] Direct /strata/v1/ fallback left unchanged.'
}
catch {
    $reason = $_.Exception.Message
    if ($changed) {
        # The backup remains LOCAL; it may include a DNS credential.
        Copy-Item -LiteralPath $backup -Destination $Caddyfile -Force
        & $CaddyExe validate --config $Caddyfile *> $null
        if ($LASTEXITCODE -eq 0) {
            & $CaddyExe reload --config $Caddyfile *> $null
        }
        Write-Warning 'Original Caddyfile restored. Inspect the gateway before trying again.'
    }
    throw "S03 Caddy activation was not verified: $reason"
}
finally {
    [Environment]::SetEnvironmentVariable('SPEEDY_API_KEY', $previous, 'Process')
}
