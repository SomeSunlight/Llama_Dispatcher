#Requires -Version 7.4
# Synthetic role-file test only; does not require a model, DPAPI key or service.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/s03_role_aliases.ps1')
$example=Join-Path $PSScriptRoot '../examples/s03-role-aliases.json'
$dir=Join-Path $env:TEMP ('s03-role-alias-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -Path $dir -ItemType Directory -Force | Out-Null
try {
    $roles=Get-S03RoleAliases -RoleFile (Resolve-Path $example).Path -NativeModel 'native-test-model'
    if($roles.Count -ne 2 -or
       $roles['agent'].model -ne 'native-test-model' -or
       $roles['sparringpartner'].model -ne 'native-test-model' -or
       $roles['agent'].parameters.reasoning_effort -ne 'none' -or
       $roles['sparringpartner'].parameters.reasoning_effort -ne 'high' -or
       $roles['agent'].parameters.temperature -ne 0.3) {
        throw 'Two aliases must target one externally owned native model with independent defaults.'
    }
    $bad=Join-Path $dir 'invalid.json'
    foreach($invalid in @(
        '{"schema_version":1,"aliases":{"agent":{"parameters":{"authorization":"secret"}}}}',
        '{"schema_version":1,"aliases":{"not valid":{"parameters":{}}}}',
        '{"schema_version":1,"aliases":{"agent":{"parameters":{"reasoning_effort":"super"}}}}',
        '{"schema_version":1,"aliases":{}}',
        '{"schema_version":2,"aliases":{"agent":{"parameters":{}}}}'
    )){
        [IO.File]::WriteAllText($bad,$invalid)
        $failed=$false
        try { Get-S03RoleAliases -RoleFile $bad -NativeModel 'native-test-model' | Out-Null }
        catch { $failed=$true }
        if(-not $failed){throw 'Unexpectedly accepted malformed/unsafe S03 role file.'}
    }
    $failed=$false
    try {
        Get-S03RoleAliases -RoleFile (Join-Path $dir 'missing.json') -NativeModel 'model' | Out-Null
    }
    catch { $failed=$true }
    if(-not $failed){throw 'Missing explicit role file must fail closed.'}
    Write-Host '[PASS] S03 role aliases preserve one native model, distinct reasoning defaults and reject bad files.'
}
finally {
    Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
