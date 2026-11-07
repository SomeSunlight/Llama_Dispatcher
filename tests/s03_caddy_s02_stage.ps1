#Requires -Version 7.4
# Synthetic local Caddyfile only. Do not touch running Caddy, real keys or users.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$dir=Join-Path $env:TEMP ('s03-caddy-s02-' + [guid]::NewGuid().ToString('N'))
New-Item -Path $dir -ItemType Directory -Force | Out-Null
$file=Join-Path $dir 'Caddyfile'
$dummy=Join-Path $dir 'caddy-fixture.cmd'
$dpapi=Join-Path $dir 'fake-test-only.dpapi'
try {
    $before=@'
example.test {
  @unauthorizedAI {
    path /v1/* /strata/v1/*
    not header Authorization "Bearer {$SPEEDY_API_KEY}"
  }
  respond @unauthorizedAI "Unauthorized" 401
  route {
    handle /strata/v1/* {
      reverse_proxy 127.0.0.1:8080
    }
    handle /v1/* {
      reverse_proxy 127.0.0.1:8001 {
        header_up -Authorization
      }
    }
  }
}
'@
    [IO.File]::WriteAllText($file,$before)
    [IO.File]::WriteAllText($dummy,"@echo off`r`nexit /b 0`r`n")
    'synthetic-token-not-real' | ConvertTo-SecureString -AsPlainText -Force |
        ConvertFrom-SecureString | Set-Content -LiteralPath $dpapi
    & (Join-Path $PSScriptRoot '../scripts/s03_caddy_s02_stage.ps1') -Caddyfile $file
    if([IO.File]::ReadAllText($file) -cne $before){throw 'S02 Caddy preview mutated file.'}
    & (Join-Path $PSScriptRoot '../scripts/s03_caddy_s02_stage.ps1') -Caddyfile $file `
        -CaddyExe $dummy -DpapiKeyFile $dpapi -Stage
    $after=[IO.File]::ReadAllText($file)
    if($after -cnotmatch 'path /strata/v1/\*' -or
       $after -cmatch 'path /v1/\* /strata/v1/\*' -or
       $after -cnotmatch 'header_up Authorization \{http.request.header.Authorization\}' -or
       $after -cnotmatch 'not header Authorization "Bearer \{\$SPEEDY_API_KEY\}"' -or
       $after -cnotmatch 'reverse_proxy 127.0.0.1:8080' -or
       $after -cnotmatch 'reverse_proxy 127.0.0.1:8001'){
        throw 'Multi-client Caddy changes lost mandatory gateway/fallback topology.'
    }
    $backup=$file+'.s02-before-multiclient'
    if([IO.File]::ReadAllText($backup) -cne $before){throw 'Missing exact original backup.'}
    & (Join-Path $PSScriptRoot '../scripts/s03_caddy_s02_stage.ps1') -Caddyfile $file `
        -CaddyExe $dummy -DpapiKeyFile $dpapi -Stage
    if([IO.File]::ReadAllText($file) -cne $after){throw 'Idempotent stage modified Caddyfile.'}
    $tampered=$after+"`n# User edit to preserve`n"
    [IO.File]::WriteAllText($file,$tampered)
    $failed=$false
    try{
        & (Join-Path $PSScriptRoot '../scripts/s03_caddy_s02_stage.ps1') -Caddyfile $file `
            -CaddyExe $dummy -DpapiKeyFile $dpapi -Revert -Stage
    }
    catch{$failed=$true}
    if(-not $failed -or [IO.File]::ReadAllText($file) -cne $tampered){
        throw 'Revert failed to protect unrelated Caddy edits.'
    }
    [IO.File]::WriteAllText($file,$after)
    & (Join-Path $PSScriptRoot '../scripts/s03_caddy_s02_stage.ps1') -Caddyfile $file `
        -CaddyExe $dummy -DpapiKeyFile $dpapi -Revert -Stage
    if([IO.File]::ReadAllText($file) -cne $before){throw 'Caddy rollback did not restore original.'}
    Write-Host '[PASS] Caddy S02 preview/stage/idempotence/protected fallback/user-edit refusal/rollback.'
}
finally {
    Remove-Item -LiteralPath $dir -Force -Recurse -ErrorAction SilentlyContinue
}
