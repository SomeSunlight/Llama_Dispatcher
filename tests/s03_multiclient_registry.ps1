#Requires -Version 7.4
# No network/process use: validate external S02 S03 registry is never rewritten.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/s03_client_registry.ps1')
$folder=Join-Path $env:TEMP ('s03-multiclient-' + [guid]::NewGuid().ToString('N'))
New-Item -Path $folder -ItemType Directory -Force | Out-Null
$external=Join-Path $folder 'individual-clients.json'
$legacy=Join-Path $folder 'legacy-clients.json'
try {
    $fixture=@{
        schema_version=1
        clients=@(
            @{id='goose-wsl';token_sha256=('a'*64);policy='passthrough'},
            @{id='webui-wsl';token_sha256=('b'*64);policy='default'},
            @{id='webui-host';token_sha256=('c'*64);policy='passthrough'},
            @{id='home-gateway';token_sha256=('d'*64);policy='passthrough'}
        )
    }|ConvertTo-Json -Depth 5
    [IO.File]::WriteAllText($external,$fixture,[Text.UTF8Encoding]::new($false))
    $before=(Get-FileHash -LiteralPath $external -Algorithm SHA256).Hash
    $got=Select-S03ClientRegistry -ExternalPath $external -LegacyOutputPath $legacy -LegacyKey 'unused-legacy-key'
    if($got -cne $external){throw 'Wrong external registry selection.'}
    $after=(Get-FileHash -LiteralPath $external -Algorithm SHA256).Hash
    if($before -cne $after -or (Test-Path -LiteralPath $legacy)){
        throw 'External multi-client registry was overwritten or legacy file created.'
    }
    $invalid=Join-Path $folder 'invalid.json'
    foreach($bad in @(
        $fixture.Replace(('b'*64),('a'*64)),
        $fixture.Replace('webui-host','goose-wsl'),
        $fixture.Replace(('c'*64),'plaintext'),
        '{}'
    )){
        [IO.File]::WriteAllText($invalid,$bad)
        $failed=$false
        try{Select-S03ClientRegistry -ExternalPath $invalid -LegacyOutputPath $legacy -LegacyKey 'unused' | Out-Null}
        catch{$failed=$true}
        if(-not $failed){throw 'Invalid client registry accepted.'}
    }
    $missing=Join-Path $folder 'missing.json'
    $failed=$false
    try{Select-S03ClientRegistry -ExternalPath $missing -LegacyOutputPath $legacy -LegacyKey 'unused' | Out-Null}
    catch{$failed=$true}
    if(-not $failed){throw 'Missing S02 registry silently downgraded to a shared key.'}
    $got=Select-S03ClientRegistry -ExternalPath '' -LegacyOutputPath $legacy -LegacyKey 'migration-only'
    $doc=Get-Content -LiteralPath $got -Raw|ConvertFrom-Json
    if($doc.clients.Count -ne 1 -or $doc.clients[0].id -ne 'home-gateway'){
        throw 'Backwards-compatible default unexpectedly changed.'
    }
    Write-Host '[PASS] S03 multi-client registry is validated, preserved, and never silently downgraded.'
}
finally{
    Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue
}
